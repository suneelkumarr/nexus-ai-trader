"""Independent Risk Manager enforcing stop-based sizing, caps, and emergency halts."""

from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from nexus.core.exceptions import (
    InsufficientBalanceError,
    LiveTradingForbiddenError,
    RiskViolationError,
)
from nexus.core.risk_config import RiskConfig
from nexus.domain.enums import MarketType, OrderSide, TradingMode
from nexus.domain.models import (
    OpenPaperPosition,
    PaperOrderRequest,
    PortfolioState,
    PositionSizingResult,
    RiskState,
    TickerQuote,
)

_QTY_QUANT = Decimal("0.00000001")
_INR_QUANT = Decimal("0.01")


class IndependentRiskManager:
    """Stateless risk evaluator enforcing NEXUS portfolio limits without exchange coupling."""

    def __init__(
        self,
        *,
        allowed_symbols: list[str],
        risk_config: RiskConfig | None = None,
        fee_bps: Decimal = Decimal("10.0"),
        slippage_bps: Decimal = Decimal("5.0"),
    ) -> None:
        self._allowed_symbols = {s.strip().upper() for s in allowed_symbols}
        self._risk = risk_config or RiskConfig()
        self._fee_bps = fee_bps
        self._slippage_bps = slippage_bps

    @property
    def config(self) -> RiskConfig:
        """Return active RiskConfig."""
        return self._risk

    def compute_portfolio_equity_inr(
        self,
        portfolio: PortfolioState,
        open_positions: list[OpenPaperPosition],
        quotes: dict[str, TickerQuote],
        inr_per_usdt: Decimal,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Return (total_equity_inr, holdings_value_inr, unrealized_pnl_inr)."""
        holdings_inr = Decimal("0")
        cost_inr = Decimal("0")
        for pos in open_positions:
            quote = quotes.get(pos.symbol)
            mark_usdt = quote.bid if quote is not None else pos.avg_entry_price_usdt
            holdings_inr += pos.quantity * mark_usdt * inr_per_usdt
            cost_inr += pos.entry_cost_inr

        holdings_inr = holdings_inr.quantize(_INR_QUANT, rounding=ROUND_HALF_UP)
        unrealized_inr = (holdings_inr - cost_inr).quantize(_INR_QUANT, rounding=ROUND_HALF_UP)
        equity_inr = (portfolio.cash_balance_inr + holdings_inr).quantize(
            _INR_QUANT, rounding=ROUND_HALF_UP
        )
        return equity_inr, holdings_inr, unrealized_inr

    def compute_drawdown_and_daily_loss(
        self,
        equity_inr: Decimal,
        risk_state: RiskState,
    ) -> tuple[Decimal, Decimal]:
        """Compute current (drawdown_pct, daily_loss_pct) as non-negative percentages."""
        peak = max(risk_state.peak_equity_inr, equity_inr)
        drawdown_pct = (
            ((peak - equity_inr) / peak) * Decimal("100")
            if peak > Decimal("0") and equity_inr < peak
            else Decimal("0")
        )
        daily_start = risk_state.daily_starting_equity_inr
        daily_loss_pct = (
            ((daily_start - equity_inr) / daily_start) * Decimal("100")
            if daily_start > Decimal("0") and equity_inr < daily_start
            else Decimal("0")
        )
        return (
            drawdown_pct.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            daily_loss_pct.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        )

    def check_global_entry_gates(
        self,
        *,
        symbol: str,
        portfolio: PortfolioState,
        open_positions: list[OpenPaperPosition],
        risk_state: RiskState,
        equity_inr: Decimal,
        quotes: dict[str, TickerQuote] | None = None,
    ) -> str | None:
        """Return rejection reason if portfolio-level entry limits are breached, else None."""
        if risk_state.kill_switch_active:
            return f"Emergency kill switch active: {risk_state.kill_switch_reason or 'halted'}."

        if quotes is not None and open_positions:
            missing = [p.symbol for p in open_positions if p.symbol not in quotes]
            if missing:
                return (
                    f"Market quote unavailable for held position(s) {missing}; "
                    "new entries halted for data fidelity."
                )

        drawdown_pct, daily_loss_pct = self.compute_drawdown_and_daily_loss(
            equity_inr, risk_state
        )
        if drawdown_pct >= self._risk.max_drawdown_pct:
            return (
                f"Maximum drawdown breached ({drawdown_pct:.2f}% >= "
                f"{self._risk.max_drawdown_pct:.2f}%)."
            )
        if daily_loss_pct >= self._risk.daily_loss_limit_pct:
            return (
                f"Daily loss limit breached ({daily_loss_pct:.2f}% >= "
                f"{self._risk.daily_loss_limit_pct:.2f}%)."
            )
        if len(open_positions) >= self._risk.max_concurrent_positions:
            return (
                f"Maximum concurrent positions reached ({len(open_positions)} >= "
                f"{self._risk.max_concurrent_positions})."
            )
        if risk_state.daily_entries_count >= self._risk.max_daily_entries:
            return (
                f"Maximum daily entries reached ({risk_state.daily_entries_count} >= "
                f"{self._risk.max_daily_entries})."
            )

        norm_symbol = symbol.strip().upper()
        base_asset = norm_symbol.split("/", maxsplit=1)[0]
        if any(p.symbol == norm_symbol for p in open_positions):
            return f"Open position already exists for {norm_symbol}."
        holding = portfolio.holdings.get(base_asset)
        if holding is not None and (holding.free_qty + holding.locked_qty) > Decimal("0"):
            return f"Spot holding already exists for {base_asset}."
        return None

    def calculate_position_size(
        self,
        *,
        symbol: str,
        entry_price_usdt: Decimal,
        stop_price_usdt: Decimal,
        inr_per_usdt: Decimal,
        portfolio: PortfolioState,
        open_positions: list[OpenPaperPosition],
        risk_state: RiskState,
        quotes: dict[str, TickerQuote] | None = None,
    ) -> PositionSizingResult:
        """Size spot LONG quantity from stop distance while capping notional, risk, and cash."""
        norm_symbol = symbol.strip().upper()
        if norm_symbol not in self._allowed_symbols:
            return PositionSizingResult(
                approved=False,
                rejection_reason=f"Symbol '{norm_symbol}' is outside allowed universe.",
            )
        if entry_price_usdt <= Decimal("0") or stop_price_usdt <= Decimal("0"):
            return PositionSizingResult(
                approved=False,
                rejection_reason="Entry and stop prices must be positive.",
            )
        if stop_price_usdt >= entry_price_usdt:
            return PositionSizingResult(
                approved=False,
                rejection_reason="Stop price must be strictly below entry price for LONG.",
            )
        if inr_per_usdt <= Decimal("0"):
            return PositionSizingResult(
                approved=False,
                rejection_reason="INR/USDT conversion rate must be positive.",
            )

        equity_inr, _, _ = self.compute_portfolio_equity_inr(
            portfolio, open_positions, quotes or {}, inr_per_usdt
        )
        gate_rejection = self.check_global_entry_gates(
            symbol=norm_symbol,
            portfolio=portfolio,
            open_positions=open_positions,
            risk_state=risk_state,
            equity_inr=equity_inr,
            quotes=quotes,
        )
        if gate_rejection is not None:
            return PositionSizingResult(approved=False, rejection_reason=gate_rejection)

        slippage_ratio = self._slippage_bps / Decimal("10000")
        fee_ratio = self._fee_bps / Decimal("10000")
        effective_entry_usdt = entry_price_usdt * (Decimal("1") + slippage_ratio)
        stop_distance_usdt = effective_entry_usdt - stop_price_usdt
        if stop_distance_usdt <= Decimal("0"):
            return PositionSizingResult(
                approved=False,
                rejection_reason="Effective entry price is not above stop price.",
            )

        risk_budget_inr = equity_inr * (self._risk.risk_per_trade_pct / Decimal("100"))
        stop_distance_inr = stop_distance_usdt * inr_per_usdt
        qty_by_risk = risk_budget_inr / stop_distance_inr

        max_notional_inr = equity_inr * (self._risk.max_position_notional_pct / Decimal("100"))
        unit_total_cost_inr = effective_entry_usdt * (Decimal("1") + fee_ratio) * inr_per_usdt
        qty_by_notional = max_notional_inr / unit_total_cost_inr
        qty_by_cash = portfolio.cash_balance_inr / unit_total_cost_inr

        raw_qty = min(qty_by_risk, qty_by_notional, qty_by_cash)
        final_qty = raw_qty.quantize(_QTY_QUANT, rounding=ROUND_DOWN)
        if final_qty <= Decimal("0"):
            return PositionSizingResult(
                approved=False,
                rejection_reason="Insufficient virtual INR cash or risk budget for minimum size.",
            )

        notional_inr = (final_qty * effective_entry_usdt * inr_per_usdt).quantize(
            _INR_QUANT, rounding=ROUND_HALF_UP
        )
        estimated_fee_inr = (notional_inr * fee_ratio).quantize(
            _INR_QUANT, rounding=ROUND_HALF_UP
        )
        total_required_inr = notional_inr + estimated_fee_inr
        if total_required_inr > portfolio.cash_balance_inr:
            return PositionSizingResult(
                approved=False,
                rejection_reason=(
                    f"Insufficient balance: need {total_required_inr:.2f} INR, "
                    f"have {portfolio.cash_balance_inr:.2f} INR."
                ),
            )
        if notional_inr < self._risk.min_order_notional_inr:
            return PositionSizingResult(
                approved=False,
                rejection_reason=(
                    f"Order notional {notional_inr:.2f} INR below minimum "
                    f"{self._risk.min_order_notional_inr:.2f} INR."
                ),
            )

        actual_risk_inr = (final_qty * stop_distance_inr).quantize(
            _INR_QUANT, rounding=ROUND_HALF_UP
        )
        return PositionSizingResult(
            approved=True,
            quantity=final_qty,
            notional_inr=notional_inr,
            risk_inr=actual_risk_inr,
            estimated_fee_inr=estimated_fee_inr,
        )

    def validate_order(
        self,
        request: PaperOrderRequest,
        portfolio: PortfolioState,
        quote: TickerQuote,
        inr_per_usdt: Decimal,
        *,
        open_positions: list[OpenPaperPosition] | None = None,
        risk_state: RiskState | None = None,
        quotes: dict[str, TickerQuote] | None = None,
    ) -> None:
        """Validate a direct PaperOrderRequest against invariants, sizing, and risk caps."""
        if request.trading_mode != TradingMode.PAPER or portfolio.trading_mode != TradingMode.PAPER:
            raise LiveTradingForbiddenError("Live trading is permanently disabled in NEXUS.")
        if request.market_type != MarketType.SPOT or portfolio.market_type != MarketType.SPOT:
            raise LiveTradingForbiddenError(
                "Futures, margin, and derivative markets are forbidden."
            )
        if request.leverage != Decimal("1"):
            raise LiveTradingForbiddenError("Leverage is forbidden. Only 1x spot trades allowed.")
        if request.is_withdrawal:
            raise LiveTradingForbiddenError("Withdrawals are permanently disabled.")

        norm_symbol = request.symbol.strip().upper()
        if norm_symbol not in self._allowed_symbols:
            raise RiskViolationError(f"Symbol '{norm_symbol}' is not in allowed spot universe.")
        if request.quantity <= Decimal("0"):
            raise RiskViolationError("Order quantity must be strictly positive.")
        if inr_per_usdt <= Decimal("0"):
            raise RiskViolationError("INR/USDT exchange rate must be positive.")

        positions = open_positions if open_positions is not None else []
        state = risk_state

        if request.side == OrderSide.BUY:
            slippage_ratio = self._slippage_bps / Decimal("10000")
            fee_ratio = self._fee_bps / Decimal("10000")
            effective_price = quote.ask * (Decimal("1") + slippage_ratio)
            order_notional_inr = effective_price * request.quantity * inr_per_usdt
            total_cost_inr = (order_notional_inr * (Decimal("1") + fee_ratio)).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )

            if state is not None:
                equity_inr, _, _ = self.compute_portfolio_equity_inr(
                    portfolio, positions, quotes or {norm_symbol: quote}, inr_per_usdt
                )
                gate_err = self.check_global_entry_gates(
                    symbol=norm_symbol,
                    portfolio=portfolio,
                    open_positions=positions,
                    risk_state=state,
                    equity_inr=equity_inr,
                )
                if gate_err is not None:
                    raise RiskViolationError(gate_err)

                max_notional_inr = equity_inr * (
                    self._risk.max_position_notional_pct / Decimal("100")
                )
                if order_notional_inr > max_notional_inr:
                    raise RiskViolationError(
                        f"Order notional {order_notional_inr:.2f} INR exceeds "
                        f"{self._risk.max_position_notional_pct}% cap ({max_notional_inr:.2f} INR)."
                    )

            if portfolio.cash_balance_inr < total_cost_inr:
                raise InsufficientBalanceError(
                    f"Insufficient virtual INR cash: have {portfolio.cash_balance_inr:.2f}, "
                    f"need {total_cost_inr:.2f}."
                )
        else:
            base_asset = norm_symbol.split("/", maxsplit=1)[0]
            holding = portfolio.holdings.get(base_asset)
            available = holding.free_qty if holding is not None else Decimal("0")
            if available < request.quantity:
                raise InsufficientBalanceError(
                    f"Insufficient spot {base_asset} balance to sell: "
                    f"have {available}, requested {request.quantity}."
                )

    def approve_entry(
        self,
        *,
        symbol: str,
        timestamp: datetime,
        entry_price: Decimal,
        stop_price: Decimal,
        portfolio: PortfolioState,
    ) -> tuple[bool, str | None]:
        """SignalRiskApprover compatibility hook for Strategy Engine V1."""
        del timestamp
        if portfolio.trading_mode != TradingMode.PAPER or portfolio.market_type != MarketType.SPOT:
            return False, "Paper spot mode required."
        norm_sym = symbol.strip().upper()
        if norm_sym not in self._allowed_symbols:
            return False, f"Symbol '{norm_sym}' not allowed."
        if entry_price <= Decimal("0") or stop_price <= Decimal("0") or stop_price >= entry_price:
            return False, "Invalid LONG entry/stop levels."
        base_asset = norm_sym.split("/", maxsplit=1)[0]
        holding = portfolio.holdings.get(base_asset)
        if holding is not None and (holding.free_qty + holding.locked_qty) > Decimal("0"):
            return False, f"Position already open for {base_asset}."
        if portfolio.cash_balance_inr < self._risk.min_order_notional_inr:
            return False, "Insufficient virtual INR cash for minimum order."
        return True, None
