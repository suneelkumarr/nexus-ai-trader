"""Persistent virtual Paper Broker with risk gating, P&L ledger, stops, and kill switch.

CRITICAL: Never invokes any private exchange trading endpoint. Reads public quotes only
through the injected MarketDataProvider.
"""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from nexus.application.risk_manager import IndependentRiskManager
from nexus.core.exceptions import (
    LiveTradingForbiddenError,
    MarketDataUnavailableError,
    RiskViolationError,
)
from nexus.core.logging import get_logger
from nexus.domain.enums import OrderSide, OrderStatus, OrderType, SignalDirection
from nexus.domain.interfaces import MarketDataProvider, PaperLedgerRepository
from nexus.domain.models import (
    AssetHolding,
    OpenPaperPosition,
    PaperFill,
    PaperOrderRequest,
    PaperOrderResult,
    PortfolioPnLSummary,
    PortfolioState,
    ReconciliationReport,
    RiskState,
    StrategySignal,
    TickerQuote,
    TradeLedgerEntry,
)

logger = get_logger(__name__)

_INR_QUANT = Decimal("0.01")


class PersistentPaperBroker:
    """Orchestrates simulated spot orders, persistent positions, P&L ledger, and kill switch."""

    def __init__(
        self,
        *,
        repository: PaperLedgerRepository,
        risk_manager: IndependentRiskManager,
        market_data: MarketDataProvider,
        initial_capital_inr: Decimal = Decimal("10000.00"),
        fee_bps: Decimal = Decimal("10.0"),
        slippage_bps: Decimal = Decimal("5.0"),
        trailing_atr_multiplier: Decimal = Decimal("2.5"),
    ) -> None:
        self._repo = repository
        self._risk = risk_manager
        self._market_data = market_data
        self._initial_capital_inr = initial_capital_inr
        self._fee_bps = fee_bps
        self._slippage_bps = slippage_bps
        self._trailing_atr_multiplier = trailing_atr_multiplier

    def _roll_daily_state_if_needed(
        self, risk_state: RiskState, current_equity_inr: Decimal, now_utc: datetime
    ) -> bool:
        """Reset daily counters at UTC day boundary and return True if rolled over."""
        today = now_utc.date()
        rolled = False
        if risk_state.trading_date_utc != today:
            risk_state.trading_date_utc = today
            risk_state.daily_starting_equity_inr = current_equity_inr
            risk_state.daily_entries_count = 0
            risk_state.daily_realized_pnl_inr = Decimal("0")
            rolled = True
        if current_equity_inr > risk_state.peak_equity_inr:
            risk_state.peak_equity_inr = current_equity_inr
        return rolled

    async def _fetch_quotes_for_positions(
        self, positions: list[OpenPaperPosition], extra_symbol: str | None = None
    ) -> tuple[dict[str, TickerQuote], Decimal]:
        """Fetch real public quotes for held symbols plus live INR/USDT conversion."""
        symbols = {p.symbol for p in positions}
        if extra_symbol is not None:
            symbols.add(extra_symbol.strip().upper())

        quotes: dict[str, TickerQuote] = {}
        for sym in symbols:
            quotes[sym] = await self._market_data.fetch_ticker(sym)
        inr_per_usdt = await self._market_data.fetch_inr_per_usdt()
        return quotes, inr_per_usdt

    async def submit_order(
        self,
        request: PaperOrderRequest,
        *,
        now_utc: datetime | None = None,
    ) -> PaperOrderResult:
        """Validate, execute virtually, and persist a paper order with duplicate protection."""
        ref_now = now_utc or datetime.now(UTC)

        # 1. Hard invariant check (never allow live/leverage/futures/withdrawals)
        if request.trading_mode != "paper" or request.market_type != "spot":
            raise LiveTradingForbiddenError("Only paper spot trading is permitted.")
        if request.leverage != Decimal("1") or request.is_withdrawal:
            raise LiveTradingForbiddenError("Leverage and withdrawals are forbidden.")

        # 2. Mandatory idempotency / duplicate order protection
        effective_cid = (
            request.client_order_id.strip()
            if request.client_order_id and request.client_order_id.strip()
            else None
        )
        if effective_cid is not None:
            existing = await self._repo.find_order_by_client_id(
                request.portfolio_id, effective_cid
            )
            if existing is not None:
                logger.warning(
                    "duplicate_paper_order_rejected",
                    portfolio_id=str(request.portfolio_id),
                    client_order_id=effective_cid,
                )
                return PaperOrderResult(
                    portfolio_id=request.portfolio_id,
                    symbol=request.symbol,
                    side=request.side,
                    order_type=request.order_type,
                    status=OrderStatus.REJECTED,
                    requested_qty=request.quantity,
                    rejection_reason=(
                        f"Duplicate client_order_id '{effective_cid}' rejected."
                    ),
                )

        portfolio = await self._repo.get_or_create_portfolio(
            request.portfolio_id, initial_capital_inr=self._initial_capital_inr
        )
        open_positions = await self._repo.get_open_positions(portfolio.id)
        risk_state = await self._repo.get_or_create_risk_state(
            portfolio.id, initial_capital_inr=self._initial_capital_inr
        )

        # 3. Fetch real public market data (never fabricate quotes on API failure)
        try:
            quotes, inr_per_usdt = await self._fetch_quotes_for_positions(
                open_positions, extra_symbol=request.symbol
            )
        except MarketDataUnavailableError as exc:
            logger.error(
                "paper_order_aborted_market_api_failure",
                portfolio_id=str(portfolio.id),
                symbol=request.symbol,
                error=str(exc),
            )
            rejected = PaperOrderResult(
                portfolio_id=portfolio.id,
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                status=OrderStatus.REJECTED,
                requested_qty=request.quantity,
                rejection_reason=f"Market data unavailable: {exc}",
            )
            await self._repo.record_order_and_fill(request, rejected, None)
            return rejected

        quote = quotes[request.symbol.strip().upper()]
        equity_inr, _, _ = self._risk.compute_portfolio_equity_inr(
            portfolio, open_positions, quotes, inr_per_usdt
        )
        self._roll_daily_state_if_needed(risk_state, equity_inr, ref_now)

        # Auto-trip emergency kill switch if max drawdown threshold is breached
        drawdown_pct, _ = self._risk.compute_drawdown_and_daily_loss(equity_inr, risk_state)
        if (
            not risk_state.kill_switch_active
            and drawdown_pct >= self._risk.config.max_drawdown_pct
        ):
            risk_state.kill_switch_active = True
            risk_state.kill_switch_reason = (
                f"Automatic max drawdown halt ({drawdown_pct:.2f}% >= "
                f"{self._risk.config.max_drawdown_pct:.2f}%)."
            )
            risk_state.kill_switch_triggered_at = ref_now
            await self._repo.save_risk_state(risk_state)

        # 4. Validate via IndependentRiskManager
        try:
            self._risk.validate_order(
                request,
                portfolio,
                quote,
                inr_per_usdt,
                open_positions=open_positions,
                risk_state=risk_state,
                quotes=quotes,
            )
        except LiveTradingForbiddenError:
            raise
        except RiskViolationError as exc:
            rejected = PaperOrderResult(
                portfolio_id=portfolio.id,
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                status=OrderStatus.REJECTED,
                requested_qty=request.quantity,
                rejection_reason=str(exc),
            )
            await self._repo.record_order_and_fill(request, rejected, None)
            return rejected

        # 5. Simulate virtual spot execution with slippage & fees
        slippage_ratio = self._slippage_bps / Decimal("10000")
        fee_ratio = self._fee_bps / Decimal("10000")
        norm_symbol = request.symbol.strip().upper()
        base_asset = norm_symbol.split("/", maxsplit=1)[0]

        result = PaperOrderResult(
            portfolio_id=portfolio.id,
            symbol=norm_symbol,
            side=request.side,
            order_type=request.order_type,
            status=OrderStatus.FILLED,
            requested_qty=request.quantity,
            created_at=ref_now,
        )
        effective_req = (
            request
            if effective_cid is not None
            else request.model_copy(update={"client_order_id": f"ord:{result.order_id}"})
        )

        if request.side == OrderSide.BUY:
            fill_price = quote.ask * (Decimal("1") + slippage_ratio)
            gross_usdt = fill_price * request.quantity
            fee_usdt = gross_usdt * fee_ratio
            total_inr = ((gross_usdt + fee_usdt) * inr_per_usdt).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )

            portfolio.cash_balance_inr -= total_inr
            portfolio.holdings[base_asset] = AssetHolding(
                asset=base_asset,
                free_qty=request.quantity,
                avg_entry_price_usdt=fill_price,
            )

            stop_price = request.stop_price_usdt or (fill_price * Decimal("0.98"))
            position = OpenPaperPosition(
                portfolio_id=portfolio.id,
                symbol=norm_symbol,
                asset=base_asset,
                quantity=request.quantity,
                avg_entry_price_usdt=fill_price,
                entry_cost_inr=total_inr,
                entry_fee_usdt=fee_usdt,
                initial_stop_price_usdt=stop_price,
                trailing_stop_price_usdt=stop_price,
                highest_price_usdt=max(fill_price, quote.last),
                trailing_atr_multiplier=(
                    request.trailing_atr_multiplier or self._trailing_atr_multiplier
                ),
                atr_at_entry=request.atr_at_entry or Decimal("0"),
                status="open",
                opened_at=ref_now,
            )
            risk_state.daily_entries_count += 1
            fill = PaperFill(
                order_id=result.order_id,
                symbol=norm_symbol,
                side=OrderSide.BUY,
                executed_qty=request.quantity,
                executed_price_usdt=fill_price,
                fee_usdt=fee_usdt,
                inr_per_usdt_rate=inr_per_usdt,
                total_inr=total_inr,
                slippage_bps=self._slippage_bps,
                executed_at=ref_now,
            )
            await self._repo.commit_order_settlement(
                request=effective_req,
                result=result,
                fill=fill,
                portfolio=portfolio,
                position=position,
                risk_state=risk_state,
            )
        else:
            fill = await self._settle_sell(
                portfolio=portfolio,
                open_positions=open_positions,
                risk_state=risk_state,
                request=effective_req,
                result=result,
                quote=quote,
                inr_per_usdt=inr_per_usdt,
                slippage_ratio=slippage_ratio,
                fee_ratio=fee_ratio,
                ref_now=ref_now,
                exit_reason=request.strategy_name,
            )

        return result.model_copy(update={"fill": fill})

    async def _settle_sell(
        self,
        *,
        portfolio: PortfolioState,
        open_positions: list[OpenPaperPosition],
        risk_state: RiskState,
        request: PaperOrderRequest,
        result: PaperOrderResult,
        quote: TickerQuote,
        inr_per_usdt: Decimal,
        slippage_ratio: Decimal,
        fee_ratio: Decimal,
        ref_now: datetime,
        exit_reason: str,
    ) -> PaperFill:
        norm_symbol = request.symbol.strip().upper()
        base_asset = norm_symbol.split("/", maxsplit=1)[0]
        fill_price = quote.bid * (Decimal("1") - slippage_ratio)
        gross_usdt = fill_price * request.quantity
        fee_usdt = gross_usdt * fee_ratio
        net_inr = ((gross_usdt - fee_usdt) * inr_per_usdt).quantize(
            _INR_QUANT, rounding=ROUND_HALF_UP
        )

        holding = portfolio.holdings[base_asset]
        holding.free_qty -= request.quantity
        if holding.free_qty == Decimal("0"):
            holding.avg_entry_price_usdt = Decimal("0")
        portfolio.cash_balance_inr += net_inr

        fill = PaperFill(
            order_id=result.order_id,
            symbol=norm_symbol,
            side=OrderSide.SELL,
            executed_qty=request.quantity,
            executed_price_usdt=fill_price,
            fee_usdt=fee_usdt,
            inr_per_usdt_rate=inr_per_usdt,
            total_inr=net_inr,
            slippage_bps=self._slippage_bps,
            executed_at=ref_now,
        )

        open_pos = next((p for p in open_positions if p.symbol == norm_symbol), None)
        if open_pos is not None:
            realized_pnl_inr = (net_inr - open_pos.entry_cost_inr).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )
            realized_pnl_pct = (
                (realized_pnl_inr / open_pos.entry_cost_inr) * Decimal("100")
            ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            total_fees_inr = ((open_pos.entry_fee_usdt + fee_usdt) * inr_per_usdt).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )

            open_pos.status = "closed"
            open_pos.closed_at = ref_now

            ledger_entry = TradeLedgerEntry(
                portfolio_id=portfolio.id,
                position_id=open_pos.id,
                symbol=norm_symbol,
                entry_order_id=open_pos.id,
                exit_order_id=result.order_id,
                quantity=request.quantity,
                entry_price_usdt=open_pos.avg_entry_price_usdt,
                exit_price_usdt=fill_price,
                entry_cost_inr=open_pos.entry_cost_inr,
                exit_proceeds_inr=net_inr,
                total_fees_inr=total_fees_inr,
                realized_pnl_inr=realized_pnl_inr,
                realized_pnl_pct=realized_pnl_pct,
                exit_reason=exit_reason,
                opened_at=open_pos.opened_at,
                closed_at=ref_now,
            )
            risk_state.daily_realized_pnl_inr += realized_pnl_inr
            risk_state.total_realized_pnl_inr += realized_pnl_inr
            await self._repo.commit_order_settlement(
                request=request,
                result=result,
                fill=fill,
                portfolio=portfolio,
                position=open_pos,
                risk_state=risk_state,
                ledger_entry=ledger_entry,
            )
        else:
            await self._repo.record_order_and_fill(request, result, fill)
            await self._repo.save_portfolio(portfolio)
            await self._repo.save_risk_state(risk_state)
        return fill

    async def execute_strategy_signal(
        self,
        portfolio_id: UUID,
        signal: StrategySignal,
        *,
        atr_value: Decimal | None = None,
        now_utc: datetime | None = None,
    ) -> PaperOrderResult:
        """Size from stop distance and execute a Strategy V1 LONG or EXIT_LONG signal."""
        ref_now = now_utc or datetime.now(UTC)
        portfolio = await self._repo.get_or_create_portfolio(
            portfolio_id, initial_capital_inr=self._initial_capital_inr
        )
        open_positions = await self._repo.get_open_positions(portfolio.id)
        risk_state = await self._repo.get_or_create_risk_state(
            portfolio.id, initial_capital_inr=self._initial_capital_inr
        )

        if signal.direction == SignalDirection.LONG:
            client_order_id = f"sig:{signal.symbol}:long:{signal.timestamp.isoformat()}"
            existing = await self._repo.find_order_by_client_id(portfolio.id, client_order_id)
            if existing is not None:
                return PaperOrderResult(
                    portfolio_id=portfolio.id,
                    symbol=signal.symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    status=OrderStatus.REJECTED,
                    requested_qty=Decimal("0"),
                    rejection_reason=f"Duplicate signal order '{client_order_id}' rejected.",
                )

            try:
                quotes, inr_per_usdt = await self._fetch_quotes_for_positions(
                    open_positions, extra_symbol=signal.symbol
                )
            except MarketDataUnavailableError as exc:
                rejected = PaperOrderResult(
                    portfolio_id=portfolio.id,
                    symbol=signal.symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    status=OrderStatus.REJECTED,
                    requested_qty=Decimal("0"),
                    rejection_reason=f"Market data unavailable: {exc}",
                )
                req = PaperOrderRequest(
                    portfolio_id=portfolio.id,
                    symbol=signal.symbol,
                    side=OrderSide.BUY,
                    quantity=Decimal("0"),
                    client_order_id=client_order_id,
                    strategy_name=signal.strategy_name,
                )
                await self._repo.record_order_and_fill(req, rejected, None)
                return rejected
            quote = quotes[signal.symbol]
            equity_inr, _, _ = self._risk.compute_portfolio_equity_inr(
                portfolio, open_positions, quotes, inr_per_usdt
            )
            self._roll_daily_state_if_needed(risk_state, equity_inr, ref_now)
            await self._repo.save_risk_state(risk_state)

            sizing = self._risk.calculate_position_size(
                symbol=signal.symbol,
                entry_price_usdt=quote.ask,
                stop_price_usdt=signal.stop_price,
                inr_per_usdt=inr_per_usdt,
                portfolio=portfolio,
                open_positions=open_positions,
                risk_state=risk_state,
                quotes=quotes,
            )
            if not sizing.approved:
                rejected = PaperOrderResult(
                    portfolio_id=portfolio.id,
                    symbol=signal.symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    status=OrderStatus.REJECTED,
                    requested_qty=Decimal("0"),
                    rejection_reason=sizing.rejection_reason,
                )
                req = PaperOrderRequest(
                    portfolio_id=portfolio.id,
                    symbol=signal.symbol,
                    side=OrderSide.BUY,
                    quantity=Decimal("0"),
                    client_order_id=client_order_id,
                    strategy_name=signal.strategy_name,
                )
                await self._repo.record_order_and_fill(req, rejected, None)
                return rejected

            buy_req = PaperOrderRequest(
                portfolio_id=portfolio.id,
                symbol=signal.symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=sizing.quantity,
                stop_price_usdt=signal.stop_price,
                atr_at_entry=atr_value or Decimal("0"),
                client_order_id=client_order_id,
                signal_timestamp=signal.timestamp,
                strategy_name=signal.strategy_name,
            )
            return await self.submit_order(buy_req, now_utc=ref_now)

        if signal.direction == SignalDirection.EXIT_LONG:
            open_pos = next((p for p in open_positions if p.symbol == signal.symbol), None)
            if open_pos is None:
                return PaperOrderResult(
                    portfolio_id=portfolio.id,
                    symbol=signal.symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    status=OrderStatus.REJECTED,
                    requested_qty=Decimal("0"),
                    rejection_reason=f"No open position to exit for {signal.symbol}.",
                )
            sell_req = PaperOrderRequest(
                portfolio_id=portfolio.id,
                symbol=signal.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=open_pos.quantity,
                client_order_id=f"sig:{signal.symbol}:exit:{signal.timestamp.isoformat()}",
                strategy_name=signal.reason,
            )
            return await self.submit_order(sell_req, now_utc=ref_now)

        return PaperOrderResult(
            portfolio_id=portfolio.id,
            symbol=signal.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            status=OrderStatus.REJECTED,
            requested_qty=Decimal("0"),
            rejection_reason="FLAT signal requires no order execution.",
        )

    async def process_stop_and_trailing_exits(
        self,
        portfolio_id: UUID,
        *,
        atr_by_symbol: dict[str, Decimal] | None = None,
        now_utc: datetime | None = None,
    ) -> list[PaperOrderResult]:
        """Monitor open positions against public quotes for stop-loss & trailing-stop exits."""
        ref_now = now_utc or datetime.now(UTC)
        open_positions = await self._repo.get_open_positions(portfolio_id)
        if not open_positions:
            return []

        quotes, _ = await self._fetch_quotes_for_positions(open_positions)
        results: list[PaperOrderResult] = []
        atr_map = atr_by_symbol or {}

        for pos in open_positions:
            quote = quotes[pos.symbol]
            active_stop = max(pos.initial_stop_price_usdt, pos.trailing_stop_price_usdt)
            if quote.bid <= active_stop:
                reason = (
                    "Trailing stop triggered"
                    if pos.trailing_stop_price_usdt > pos.initial_stop_price_usdt
                    else "Stop-loss triggered"
                )
                sell_req = PaperOrderRequest(
                    portfolio_id=portfolio_id,
                    symbol=pos.symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=pos.quantity,
                    client_order_id=f"stop:{pos.id}:{ref_now.isoformat()}",
                    strategy_name=reason,
                )
                results.append(await self.submit_order(sell_req, now_utc=ref_now))
            else:
                new_high = max(pos.highest_price_usdt, quote.last)
                atr_val = atr_map.get(pos.symbol, pos.atr_at_entry)
                if atr_val > Decimal("0") and new_high > pos.highest_price_usdt:
                    candidate = new_high - (atr_val * pos.trailing_atr_multiplier)
                    pos.trailing_stop_price_usdt = max(pos.trailing_stop_price_usdt, candidate)
                pos.highest_price_usdt = new_high
                await self._repo.save_position(pos)
        return results

    async def activate_kill_switch(
        self,
        portfolio_id: UUID,
        *,
        reason: str,
        flatten_positions: bool = True,
        now_utc: datetime | None = None,
    ) -> list[PaperOrderResult]:
        """Halt all new entries immediately, cancel pending orders, and optionally flatten."""
        ref_now = now_utc or datetime.now(UTC)
        risk_state = await self._repo.get_or_create_risk_state(
            portfolio_id, initial_capital_inr=self._initial_capital_inr
        )
        risk_state.kill_switch_active = True
        risk_state.kill_switch_reason = reason
        risk_state.kill_switch_triggered_at = ref_now
        await self._repo.save_risk_state(risk_state)
        await self._repo.cancel_pending_orders(portfolio_id, f"Kill switch: {reason}")

        logger.critical(
            "emergency_kill_switch_activated",
            portfolio_id=str(portfolio_id),
            reason=reason,
            flatten_positions=flatten_positions,
        )

        if not flatten_positions:
            return []

        open_positions = await self._repo.get_open_positions(portfolio_id)
        results: list[PaperOrderResult] = []
        for pos in open_positions:
            sell_req = PaperOrderRequest(
                portfolio_id=portfolio_id,
                symbol=pos.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=pos.quantity,
                client_order_id=f"kill:{pos.id}:{ref_now.isoformat()}",
                strategy_name=f"Emergency kill switch: {reason}",
            )
            results.append(await self.submit_order(sell_req, now_utc=ref_now))
        return results

    async def compute_pnl_summary(self, portfolio_id: UUID) -> PortfolioPnLSummary:
        """Compute live realized, unrealized P&L, drawdown, and daily loss percentages."""
        portfolio = await self._repo.get_or_create_portfolio(
            portfolio_id, initial_capital_inr=self._initial_capital_inr
        )
        open_positions = await self._repo.get_open_positions(portfolio.id)
        risk_state = await self._repo.get_or_create_risk_state(
            portfolio.id, initial_capital_inr=self._initial_capital_inr
        )
        quotes, inr_per_usdt = await self._fetch_quotes_for_positions(open_positions)
        equity_inr, holdings_inr, unrealized_inr = self._risk.compute_portfolio_equity_inr(
            portfolio, open_positions, quotes, inr_per_usdt
        )
        drawdown_pct, daily_loss_pct = self._risk.compute_drawdown_and_daily_loss(
            equity_inr, risk_state
        )

        return PortfolioPnLSummary(
            portfolio_id=portfolio.id,
            cash_balance_inr=portfolio.cash_balance_inr,
            holdings_value_inr=holdings_inr,
            total_equity_inr=equity_inr,
            realized_pnl_inr=risk_state.total_realized_pnl_inr,
            unrealized_pnl_inr=unrealized_inr,
            drawdown_pct=drawdown_pct,
            daily_loss_pct=daily_loss_pct,
            open_positions_count=len(open_positions),
            daily_entries_count=risk_state.daily_entries_count,
            kill_switch_active=risk_state.kill_switch_active,
        )

    async def reconcile_on_startup(
        self,
        portfolio_id: UUID | None = None,
        *,
        now_utc: datetime | None = None,
    ) -> ReconciliationReport:
        """Reconcile persisted portfolio balances, open positions, and daily risk state."""
        ref_now = now_utc or datetime.now(UTC)
        portfolio = await self._repo.get_or_create_portfolio(
            portfolio_id, initial_capital_inr=self._initial_capital_inr
        )
        open_positions = await self._repo.get_open_positions(portfolio.id)
        risk_state = await self._repo.get_or_create_risk_state(
            portfolio.id, initial_capital_inr=self._initial_capital_inr
        )
        ledger = await self._repo.list_trade_ledger(portfolio.id)

        discrepancies: list[str] = []
        repaired = False

        # 1. Reconcile open positions against per-asset portfolio_balances
        expected_qty_by_asset: dict[str, Decimal] = {}
        for pos in open_positions:
            expected_qty_by_asset[pos.asset] = (
                expected_qty_by_asset.get(pos.asset, Decimal("0")) + pos.quantity
            )

        all_assets = set(portfolio.holdings.keys()) | set(expected_qty_by_asset.keys())
        for asset in all_assets:
            expected_qty = expected_qty_by_asset.get(asset, Decimal("0"))
            holding = portfolio.holdings.get(asset)
            actual_qty = holding.free_qty if holding is not None else Decimal("0")
            if actual_qty != expected_qty:
                discrepancies.append(
                    f"Balance mismatch for {asset}: stored={actual_qty}, "
                    f"open_positions={expected_qty}."
                )
                portfolio.holdings[asset] = AssetHolding(
                    asset=asset,
                    free_qty=expected_qty,
                    avg_entry_price_usdt=(
                        holding.avg_entry_price_usdt if holding is not None else Decimal("0")
                    ),
                )
                repaired = True

        if repaired:
            await self._repo.save_portfolio(portfolio)

        # 2. Verify cash ledger conservation: initial + realized - open_entry_cost == cash
        realized_sum = sum((e.realized_pnl_inr for e in ledger), Decimal("0"))
        open_cost_sum = sum((p.entry_cost_inr for p in open_positions), Decimal("0"))
        expected_cash = (
            portfolio.initial_capital_inr + realized_sum - open_cost_sum
        ).quantize(_INR_QUANT, rounding=ROUND_HALF_UP)
        if abs(portfolio.cash_balance_inr - expected_cash) > Decimal("0.05"):
            discrepancies.append(
                f"Cash ledger drift: actual={portfolio.cash_balance_inr:.2f}, "
                f"expected={expected_cash:.2f}."
            )

        # 3. Roll over daily risk counters if UTC date changed across restart
        approx_equity = portfolio.cash_balance_inr + open_cost_sum
        rolled = self._roll_daily_state_if_needed(risk_state, approx_equity, ref_now)
        if rolled:
            await self._repo.save_risk_state(risk_state)

        logger.info(
            "startup_portfolio_reconciled",
            portfolio_id=str(portfolio.id),
            open_positions=len(open_positions),
            discrepancies=len(discrepancies),
            repaired=repaired,
            daily_rolled_over=rolled,
        )
        return ReconciliationReport(
            portfolio_id=portfolio.id,
            cash_balance_inr=portfolio.cash_balance_inr,
            reconciled_positions=len(open_positions),
            discrepancies=discrepancies,
            repaired=repaired,
            daily_rolled_over=rolled,
        )

