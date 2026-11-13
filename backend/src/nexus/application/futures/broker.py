"""Simulated Futures Paper Broker managing isolated margin perpetuals."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from nexus.application.futures.calculator import FuturesRiskCalculator
from nexus.application.futures.funding_service import FuturesFundingService
from nexus.core.logging import get_logger
from nexus.domain.futures import (
    FuturesAccountSummary,
    FuturesMarginMode,
    FuturesOrderAction,
    FuturesOrderRequest,
    FuturesOrderResult,
    FuturesOrderStatus,
    FuturesPosition,
    FuturesPositionStatus,
    FuturesSide,
)
from nexus.domain.interfaces import MarketDataProvider, PaperLedgerRepository
from nexus.infrastructure.db.futures_repository import SqlAlchemyFuturesRepository
from nexus.infrastructure.db.models import (
    PaperFuturesOrderORM,
    PaperFuturesPositionORM,
)

logger = get_logger(__name__)


class FuturesPaperBroker:
    """High-fidelity virtual futures trading engine with isolated margin and short selling."""

    def __init__(
        self,
        *,
        repository: SqlAlchemyFuturesRepository,
        market_data: MarketDataProvider,
        funding_service: FuturesFundingService | None = None,
        paper_repo: PaperLedgerRepository | None = None,
        slippage_bps: Decimal = Decimal("5.0"),
        fee_rate: Decimal = Decimal("0.0004"),
    ) -> None:
        self._repo = repository
        self._market_data = market_data
        self._funding = funding_service or FuturesFundingService()
        self._paper_repo = paper_repo
        self._slippage_bps = slippage_bps
        self._fee_rate = fee_rate
        self._calc = FuturesRiskCalculator()
        self._auto_trade_enabled = False

    async def _kill_switch_reason(self, portfolio_id: UUID) -> str | None:
        """Return the active kill-switch reason, if the shared risk state is halted."""
        if self._paper_repo is None:
            return None
        risk_state = await self._paper_repo.get_or_create_risk_state(portfolio_id)
        if not risk_state.kill_switch_active:
            return None
        return risk_state.kill_switch_reason or "Emergency kill switch active"

    @property
    def auto_trade_enabled(self) -> bool:
        return self._auto_trade_enabled

    def set_auto_trade(self, enabled: bool) -> None:
        self._auto_trade_enabled = enabled

    async def get_account_summary(self) -> FuturesAccountSummary:
        """Fetch consolidated account summary including real-time unrealized PnL."""
        portfolio = await self._repo.get_or_create_portfolio()
        summary_raw = await self._repo.get_summary_metrics(portfolio.id)
        open_positions = await self.get_open_positions()

        total_unrealized_inr = sum(
            (pos.unrealized_pnl_inr for pos in open_positions), Decimal("0")
        )

        return FuturesAccountSummary(
            total_margin_inr=summary_raw["total_futures_margin_inr"],
            available_cash_inr=summary_raw["available_cash_inr"],
            unrealized_pnl_inr=total_unrealized_inr,
            realized_pnl_inr=summary_raw["realized_pnl_inr"],
            open_positions_count=len(open_positions),
            closed_positions_count=summary_raw["closed_positions_count"],
            liquidated_count=summary_raw["liquidated_count"],
            total_trades_count=summary_raw["total_trades_count"],
            win_rate_pct=summary_raw["win_rate_pct"],
            auto_trade_enabled=self._auto_trade_enabled,
        )

    async def submit_order(self, request: FuturesOrderRequest) -> FuturesOrderResult:
        """Process a simulated futures order (OPEN_LONG, OPEN_SHORT, etc.)."""
        portfolio = await self._repo.get_or_create_portfolio()
        now = datetime.now(UTC)

        halt_reason = await self._kill_switch_reason(portfolio.id)
        if halt_reason is not None and request.action in (
            FuturesOrderAction.OPEN_LONG,
            FuturesOrderAction.OPEN_SHORT,
        ):
            return FuturesOrderResult(
                portfolio_id=portfolio.id,
                symbol=request.symbol,
                action=request.action,
                status=FuturesOrderStatus.REJECTED,
                quantity=request.quantity,
                rejection_reason=f"Futures entries halted: {halt_reason}",
            )

        try:
            ticker = await self._market_data.fetch_ticker(request.symbol)
            inr_rate = await self._market_data.fetch_inr_per_usdt()
        except Exception as exc:
            logger.warning("futures_order_ticker_error", symbol=request.symbol, error=str(exc))
            return FuturesOrderResult(
                portfolio_id=portfolio.id,
                symbol=request.symbol,
                action=request.action,
                status=FuturesOrderStatus.REJECTED,
                quantity=request.quantity,
                rejection_reason=f"Market data unavailable: {exc}",
            )

        # Slippage simulation
        slippage_factor = self._slippage_bps / Decimal("10000")
        if request.action in (FuturesOrderAction.OPEN_LONG, FuturesOrderAction.CLOSE_SHORT):
            exec_price = ticker.ask * (Decimal("1") + slippage_factor)
            side = FuturesSide.LONG
        else:
            exec_price = ticker.bid * (Decimal("1") - slippage_factor)
            side = FuturesSide.SHORT

        # Validate leverage
        leverage = min(max(request.leverage, 1), 5)

        # Handle Close Order
        if request.action in (FuturesOrderAction.CLOSE_LONG, FuturesOrderAction.CLOSE_SHORT):
            open_positions = await self._repo.get_open_positions(portfolio.id)
            target_side = (
                FuturesSide.LONG.value
                if request.action == FuturesOrderAction.CLOSE_LONG
                else FuturesSide.SHORT.value
            )
            target_pos = next(
                (p for p in open_positions if p.symbol == request.symbol and p.side == target_side),
                None,
            )
            if not target_pos:
                return FuturesOrderResult(
                    portfolio_id=portfolio.id,
                    symbol=request.symbol,
                    action=request.action,
                    status=FuturesOrderStatus.REJECTED,
                    quantity=request.quantity,
                    rejection_reason=(
                        f"No open {request.action.value} position found for {request.symbol}"
                    ),
                )

            closed_pos = await self.close_position_by_id(
                target_pos.id, reason="Manual user close order"
            )
            return FuturesOrderResult(
                portfolio_id=portfolio.id,
                symbol=request.symbol,
                action=request.action,
                status=FuturesOrderStatus.FILLED,
                quantity=request.quantity,
                executed_price=closed_pos.close_price,
                position_id=closed_pos.id,
            )

        # Handle Open Order (OPEN_LONG or OPEN_SHORT)
        try:
            initial_margin_inr = self._calc.compute_initial_margin(
                entry_price=exec_price,
                quantity=request.quantity,
                leverage=leverage,
                inr_rate=inr_rate,
            )
            fee_inr = self._calc.compute_trading_fee(
                price=exec_price,
                quantity=request.quantity,
                inr_rate=inr_rate,
                fee_rate=self._fee_rate,
            )
            liq_price = self._calc.compute_liquidation_price(
                entry_price=exec_price,
                side=side,
                leverage=leverage,
            )
        except Exception as exc:
            return FuturesOrderResult(
                portfolio_id=portfolio.id,
                symbol=request.symbol,
                action=request.action,
                status=FuturesOrderStatus.REJECTED,
                quantity=request.quantity,
                rejection_reason=f"Risk calculation error: {exc}",
            )

        # Check cash balance
        if portfolio.cash_balance_inr < (initial_margin_inr + fee_inr):
            return FuturesOrderResult(
                portfolio_id=portfolio.id,
                symbol=request.symbol,
                action=request.action,
                status=FuturesOrderStatus.REJECTED,
                quantity=request.quantity,
                rejection_reason=(
                    f"Insufficient balance: needed ₹{(initial_margin_inr + fee_inr):,.2f}, "
                    f"available ₹{portfolio.cash_balance_inr:,.2f}"
                ),
            )

        order_orm = PaperFuturesOrderORM(
            portfolio_id=portfolio.id,
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.action.value,
            order_type="market" if request.limit_price is None else "limit",
            leverage=leverage,
            quantity=request.quantity,
            executed_price_usdt=exec_price,
            limit_price_usdt=request.limit_price,
            stop_loss_price_usdt=request.stop_loss_price,
            take_profit_price_usdt=request.take_profit_price,
            fee_inr=fee_inr,
            status="filled",
        )

        pos_orm = PaperFuturesPositionORM(
            portfolio_id=portfolio.id,
            symbol=request.symbol,
            side=side.value,
            leverage=leverage,
            margin_mode="ISOLATED",
            quantity=request.quantity,
            entry_price_usdt=exec_price,
            liquidation_price_usdt=liq_price,
            stop_loss_price_usdt=request.stop_loss_price,
            take_profit_price_usdt=request.take_profit_price,
            initial_margin_inr=initial_margin_inr,
            entry_fee_inr=fee_inr,
            status="open",
            opened_at=now,
        )

        try:
            persisted_pos = await self._repo.open_position(
                portfolio_id=portfolio.id,
                order=order_orm,
                position=pos_orm,
                initial_margin_inr=initial_margin_inr,
                fee_inr=fee_inr,
            )
            logger.info(
                "futures_position_opened",
                symbol=request.symbol,
                side=side.value,
                leverage=leverage,
                entry_price=str(exec_price),
                margin_inr=str(initial_margin_inr),
            )
            return FuturesOrderResult(
                portfolio_id=portfolio.id,
                symbol=request.symbol,
                action=request.action,
                status=FuturesOrderStatus.FILLED,
                quantity=request.quantity,
                executed_price=exec_price,
                fee_inr=fee_inr,
                position_id=persisted_pos.id,
            )
        except Exception as exc:
            logger.error("futures_open_position_failed", error=str(exc))
            return FuturesOrderResult(
                portfolio_id=portfolio.id,
                symbol=request.symbol,
                action=request.action,
                status=FuturesOrderStatus.REJECTED,
                quantity=request.quantity,
                rejection_reason=f"Failed to open position: {exc}",
            )

    async def get_open_positions(self) -> list[FuturesPosition]:
        """Fetch all open positions enriched with real-time mark price, PnL & liquidation check."""
        portfolio = await self._repo.get_or_create_portfolio()
        open_rows = await self._repo.get_open_positions(portfolio.id)
        if not open_rows:
            return []

        try:
            inr_rate = await self._market_data.fetch_inr_per_usdt()
        except Exception:
            inr_rate = Decimal("85.00")

        results: list[FuturesPosition] = []
        for row in open_rows:
            side = FuturesSide.LONG if row.side == "LONG" else FuturesSide.SHORT
            try:
                ticker = await self._market_data.fetch_ticker(row.symbol)
                mark_price = ticker.last
            except Exception:
                mark_price = row.entry_price_usdt

            # Liquidation check
            is_liq = self._calc.is_liquidated(
                mark_price=mark_price,
                liquidation_price=row.liquidation_price_usdt,
                side=side,
            )
            if is_liq:
                logger.warning(
                    "futures_position_auto_liquidated",
                    symbol=row.symbol,
                    side=row.side,
                    entry=str(row.entry_price_usdt),
                    mark=str(mark_price),
                    liq=str(row.liquidation_price_usdt),
                )
                await self._repo.close_position(
                    portfolio_id=portfolio.id,
                    position_id=row.id,
                    exit_price=mark_price,
                    realized_pnl_inr=-row.initial_margin_inr,
                    exit_fee_inr=Decimal("0"),
                    close_reason="Liquidated: mark price crossed liquidation threshold",
                    status="liquidated",
                )
                continue

            # Stop-loss check
            if row.stop_loss_price_usdt:
                sl_hit = (
                    mark_price <= row.stop_loss_price_usdt
                    if side == FuturesSide.LONG
                    else mark_price >= row.stop_loss_price_usdt
                )
                if sl_hit:
                    await self.close_position_by_id(
                        row.id, reason="Stop-loss triggered at market"
                    )
                    continue

            # Take-profit check
            if row.take_profit_price_usdt:
                tp_hit = (
                    mark_price >= row.take_profit_price_usdt
                    if side == FuturesSide.LONG
                    else mark_price <= row.take_profit_price_usdt
                )
                if tp_hit:
                    await self.close_position_by_id(
                        row.id, reason="Take-profit reached at market"
                    )
                    continue

            # PnL math
            pnl_usd, pnl_inr, roe_pct = self._calc.compute_pnl(
                entry_price=row.entry_price_usdt,
                mark_price=mark_price,
                quantity=row.quantity,
                side=side,
                initial_margin_inr=row.initial_margin_inr,
                inr_rate=inr_rate,
            )

            results.append(
                FuturesPosition(
                    id=row.id,
                    portfolio_id=row.portfolio_id,
                    symbol=row.symbol,
                    side=side,
                    leverage=row.leverage,
                    margin_mode=FuturesMarginMode.ISOLATED,
                    quantity=row.quantity,
                    entry_price=row.entry_price_usdt,
                    mark_price=mark_price,
                    liquidation_price=row.liquidation_price_usdt,
                    stop_loss_price=row.stop_loss_price_usdt,
                    take_profit_price=row.take_profit_price_usdt,
                    initial_margin_inr=row.initial_margin_inr,
                    entry_fee_inr=row.entry_fee_inr,
                    unrealized_pnl_usd=pnl_usd,
                    unrealized_pnl_inr=pnl_inr,
                    roe_pct=roe_pct,
                    status=FuturesPositionStatus.OPEN,
                    opened_at=row.opened_at,
                )
            )

        return results

    async def get_all_positions(self, limit: int = 50) -> list[FuturesPosition]:
        """Fetch historical positions including closed and liquidated."""
        portfolio = await self._repo.get_or_create_portfolio()
        rows = await self._repo.get_all_positions(portfolio.id, limit=limit)
        results: list[FuturesPosition] = []
        for r in rows:
            side = FuturesSide.LONG if r.side == "LONG" else FuturesSide.SHORT
            status = FuturesPositionStatus(r.status)
            results.append(
                FuturesPosition(
                    id=r.id,
                    portfolio_id=r.portfolio_id,
                    symbol=r.symbol,
                    side=side,
                    leverage=r.leverage,
                    margin_mode=FuturesMarginMode.ISOLATED,
                    quantity=r.quantity,
                    entry_price=r.entry_price_usdt,
                    mark_price=r.exit_price_usdt or r.entry_price_usdt,
                    liquidation_price=r.liquidation_price_usdt,
                    stop_loss_price=r.stop_loss_price_usdt,
                    take_profit_price=r.take_profit_price_usdt,
                    initial_margin_inr=r.initial_margin_inr,
                    entry_fee_inr=r.entry_fee_inr,
                    realized_pnl_inr=r.realized_pnl_inr,
                    status=status,
                    close_price=r.exit_price_usdt,
                    close_reason=r.close_reason,
                    opened_at=r.opened_at,
                    closed_at=r.closed_at,
                )
            )
        return results

    async def close_all_positions(self, reason: str = "Emergency kill switch") -> int:
        """Flatten every open simulated futures position at market."""
        portfolio = await self._repo.get_or_create_portfolio()
        open_rows = await self._repo.get_open_positions(portfolio.id)
        closed = 0
        for row in open_rows:
            try:
                await self.close_position_by_id(row.id, reason=reason)
                closed += 1
            except Exception as exc:
                logger.warning(
                    "futures_kill_switch_close_failed",
                    position_id=str(row.id),
                    error=str(exc),
                )
        return closed

    async def close_position_by_id(
        self, position_id: UUID, reason: str = "User closed position"
    ) -> FuturesPosition:
        """Close an open position at current market price."""
        portfolio = await self._repo.get_or_create_portfolio()
        pos = await self._repo.get_position_by_id(position_id)
        if not pos or pos.status != "open":
            raise ValueError(f"Position {position_id} is not open or does not exist.")

        side = FuturesSide.LONG if pos.side == "LONG" else FuturesSide.SHORT
        try:
            ticker = await self._market_data.fetch_ticker(pos.symbol)
            inr_rate = await self._market_data.fetch_inr_per_usdt()
            # Sell into bid for long exit, buy ask for short exit
            exit_price = ticker.bid if side == FuturesSide.LONG else ticker.ask
        except Exception:
            exit_price = pos.entry_price_usdt
            inr_rate = Decimal("85.00")

        exit_fee_inr = self._calc.compute_trading_fee(
            price=exit_price,
            quantity=pos.quantity,
            inr_rate=inr_rate,
            fee_rate=self._fee_rate,
        )

        _, realized_pnl_inr, roe_pct = self._calc.compute_pnl(
            entry_price=pos.entry_price_usdt,
            mark_price=exit_price,
            quantity=pos.quantity,
            side=side,
            initial_margin_inr=pos.initial_margin_inr,
            inr_rate=inr_rate,
        )

        closed_row = await self._repo.close_position(
            portfolio_id=portfolio.id,
            position_id=pos.id,
            exit_price=exit_price,
            realized_pnl_inr=realized_pnl_inr,
            exit_fee_inr=exit_fee_inr,
            close_reason=reason,
            status="closed",
        )

        logger.info(
            "futures_position_closed",
            symbol=pos.symbol,
            side=pos.side,
            entry=str(pos.entry_price_usdt),
            exit=str(exit_price),
            realized_pnl_inr=str(realized_pnl_inr),
        )

        return FuturesPosition(
            id=closed_row.id,
            portfolio_id=closed_row.portfolio_id,
            symbol=closed_row.symbol,
            side=side,
            leverage=closed_row.leverage,
            quantity=closed_row.quantity,
            entry_price=closed_row.entry_price_usdt,
            mark_price=exit_price,
            liquidation_price=closed_row.liquidation_price_usdt,
            initial_margin_inr=closed_row.initial_margin_inr,
            realized_pnl_inr=realized_pnl_inr,
            status=FuturesPositionStatus.CLOSED,
            close_price=exit_price,
            close_reason=reason,
            opened_at=closed_row.opened_at,
            closed_at=closed_row.closed_at,
        )
