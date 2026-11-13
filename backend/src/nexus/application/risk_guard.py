"""Spot-only, paper-only risk validation guard and strategy signal risk approver."""

from datetime import datetime
from decimal import Decimal

from nexus.core.exceptions import (
    InsufficientBalanceError,
    LiveTradingForbiddenError,
    RiskViolationError,
)
from nexus.domain.enums import MarketType, OrderSide, TradingMode
from nexus.domain.models import PaperOrderRequest, PortfolioState, TickerQuote


class SpotSignalRiskApprover:
    """Approves or rejects proposed spot LONG signals against portfolio & invariant rules."""

    def __init__(
        self,
        *,
        allowed_symbols: list[str],
        min_cash_reserve_inr: Decimal = Decimal("100.00"),
        max_risk_per_trade_pct: Decimal = Decimal("2.0"),
    ) -> None:
        self._allowed_symbols = {s.upper() for s in allowed_symbols}
        self._min_cash_reserve_inr = min_cash_reserve_inr
        self._max_risk_per_trade_pct = max_risk_per_trade_pct

    def approve_entry(
        self,
        *,
        symbol: str,
        timestamp: datetime,
        entry_price: Decimal,
        stop_price: Decimal,
        portfolio: PortfolioState,
    ) -> tuple[bool, str | None]:
        """Validate invariants, stop distance, spot holdings, and INR cash availability."""
        del timestamp  # Audit timestamp accepted by protocol; decision is invariant-based
        if portfolio.trading_mode != TradingMode.PAPER:
            return False, "Live trading mode is forbidden."
        if portfolio.market_type != MarketType.SPOT:
            return False, "Non-spot markets are forbidden."

        norm_symbol = symbol.strip().upper()
        if norm_symbol not in self._allowed_symbols:
            return False, f"Symbol '{norm_symbol}' is outside allowed spot universe."

        if entry_price <= Decimal("0") or stop_price <= Decimal("0"):
            return False, "Entry and stop prices must be positive."
        if stop_price >= entry_price:
            return False, "LONG stop price must be strictly below entry price."

        base_asset = norm_symbol.split("/", maxsplit=1)[0]
        holding = portfolio.holdings.get(base_asset)
        if holding is not None and (holding.free_qty + holding.locked_qty) > Decimal("0"):
            return False, f"Existing spot position already open for {base_asset}."

        if portfolio.cash_balance_inr <= self._min_cash_reserve_inr:
            return (
                False,
                f"Virtual INR cash ({portfolio.cash_balance_inr:.2f}) below minimum reserve "
                f"({self._min_cash_reserve_inr:.2f}).",
            )

        return True, None


class SpotPaperRiskGuard:
    """Enforces strict paper-only, spot-only, non-leveraged risk invariants."""

    def __init__(
        self,
        *,
        allowed_symbols: list[str],
        fee_bps: Decimal = Decimal("10.0"),
        slippage_bps: Decimal = Decimal("5.0"),
    ) -> None:
        self._allowed_symbols = {s.upper() for s in allowed_symbols}
        self._fee_bps = fee_bps
        self._slippage_bps = slippage_bps

    def validate_order(
        self,
        request: PaperOrderRequest,
        portfolio: PortfolioState,
        quote: TickerQuote,
        inr_per_usdt: Decimal,
    ) -> None:
        """Verify order adheres to all NEXUS paper-trading and spot-only constraints."""
        if request.trading_mode != TradingMode.PAPER or portfolio.trading_mode != TradingMode.PAPER:
            raise LiveTradingForbiddenError("Live trading is permanently disabled in NEXUS.")

        if request.market_type != MarketType.SPOT or portfolio.market_type != MarketType.SPOT:
            raise LiveTradingForbiddenError(
                "Futures, margin, and derivative markets are forbidden."
            )

        if request.leverage != Decimal("1"):
            raise LiveTradingForbiddenError(
                f"Leverage ({request.leverage}x) is forbidden. Only 1x spot trades are allowed."
            )

        if request.is_withdrawal:
            raise LiveTradingForbiddenError("Withdrawals are permanently disabled.")

        symbol = request.symbol.strip().upper()
        if symbol not in self._allowed_symbols:
            raise RiskViolationError(
                f"Symbol '{symbol}' is outside allowed universe {sorted(self._allowed_symbols)}."
            )

        if inr_per_usdt <= Decimal("0"):
            raise RiskViolationError("INR/USDT exchange rate must be positive.")

        base_asset = symbol.split("/", maxsplit=1)[0]

        if request.side == OrderSide.BUY:
            cost_multiplier = Decimal("1") + (
                (self._slippage_bps + self._fee_bps) / Decimal("10000")
            )
            estimated_usdt = quote.ask * request.quantity * cost_multiplier
            estimated_inr = estimated_usdt * inr_per_usdt
            if portfolio.cash_balance_inr < estimated_inr:
                raise InsufficientBalanceError(
                    f"Insufficient virtual INR cash: have {portfolio.cash_balance_inr:.2f}, "
                    f"need {estimated_inr:.2f}."
                )
        else:
            holding = portfolio.holdings.get(base_asset)
            available = holding.free_qty if holding is not None else Decimal("0")
            if available < request.quantity:
                raise InsufficientBalanceError(
                    f"Insufficient spot {base_asset} balance to sell without shorting: "
                    f"have {available}, requested {request.quantity}."
                )

