"""Unit tests for IndependentRiskManager (sizing, caps, daily loss, drawdown, limits)."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from nexus.application.risk_manager import IndependentRiskManager
from nexus.core.exceptions import (
    InsufficientBalanceError,
    LiveTradingForbiddenError,
    RiskViolationError,
)
from nexus.core.risk_config import RiskConfig
from nexus.domain.enums import OrderSide
from nexus.domain.models import (
    OpenPaperPosition,
    PaperOrderRequest,
    PortfolioState,
    RiskState,
    TickerQuote,
)


def _risk_state(
    portfolio: PortfolioState,
    *,
    daily_start: Decimal = Decimal("10000.00"),
    peak: Decimal = Decimal("10000.00"),
    daily_entries: int = 0,
    kill_switch: bool = False,
) -> RiskState:
    return RiskState(
        portfolio_id=portfolio.id,
        trading_date_utc=datetime.now(UTC).date(),
        daily_starting_equity_inr=daily_start,
        peak_equity_inr=peak,
        daily_entries_count=daily_entries,
        kill_switch_active=kill_switch,
    )


def _open_pos(portfolio: PortfolioState, symbol: str) -> OpenPaperPosition:
    return OpenPaperPosition(
        portfolio_id=portfolio.id,
        symbol=symbol,
        asset=symbol.split("/")[0],
        quantity=Decimal("1"),
        avg_entry_price_usdt=Decimal("100"),
        entry_cost_inr=Decimal("1500"),
        initial_stop_price_usdt=Decimal("95"),
        trailing_stop_price_usdt=Decimal("95"),
        highest_price_usdt=Decimal("100"),
    )


def test_stop_distance_sizing_respects_half_percent_risk_and_twenty_percent_notional(
    initial_portfolio: PortfolioState,
) -> None:
    mgr = IndependentRiskManager(
        allowed_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        risk_config=RiskConfig(),
        fee_bps=Decimal("10"),
        slippage_bps=Decimal("5"),
    )
    # Wide stop -> 0.5% risk (INR 50) governs size (< 20% notional)
    wide = mgr.calculate_position_size(
        symbol="SOL/USDT",
        entry_price_usdt=Decimal("100"),
        stop_price_usdt=Decimal("90"),
        inr_per_usdt=Decimal("85"),
        portfolio=initial_portfolio,
        open_positions=[],
        risk_state=_risk_state(initial_portfolio),
    )
    assert wide.approved is True
    assert wide.risk_inr <= Decimal("50.01")
    assert wide.notional_inr <= Decimal("2000.00")

    # Very tight stop -> 20% notional cap (INR 2,000) governs size
    tight = mgr.calculate_position_size(
        symbol="SOL/USDT",
        entry_price_usdt=Decimal("100"),
        stop_price_usdt=Decimal("99.5"),
        inr_per_usdt=Decimal("85"),
        portfolio=initial_portfolio,
        open_positions=[],
        risk_state=_risk_state(initial_portfolio),
    )
    assert tight.approved is True
    assert tight.notional_inr <= Decimal("2000.00")
    assert tight.notional_inr > Decimal("1900.00")


def test_insufficient_balance_rejected(
    initial_portfolio: PortfolioState, btc_quote: TickerQuote
) -> None:
    mgr = IndependentRiskManager(allowed_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    low_cash = initial_portfolio.model_copy(update={"cash_balance_inr": Decimal("25.00")})

    sizing = mgr.calculate_position_size(
        symbol="BTC/USDT",
        entry_price_usdt=btc_quote.ask,
        stop_price_usdt=Decimal("88000"),
        inr_per_usdt=Decimal("85"),
        portfolio=low_cash,
        open_positions=[],
        risk_state=_risk_state(low_cash),
    )
    assert sizing.approved is False
    assert sizing.rejection_reason is not None

    req = PaperOrderRequest(
        portfolio_id=low_cash.id,
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.001"),
    )
    with pytest.raises(InsufficientBalanceError):
        mgr.validate_order(req, low_cash, btc_quote, Decimal("85"))


def test_max_concurrent_positions_and_daily_entries_enforced(
    initial_portfolio: PortfolioState,
) -> None:
    mgr = IndependentRiskManager(allowed_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    two_open = [_open_pos(initial_portfolio, "BTC/USDT"), _open_pos(initial_portfolio, "ETH/USDT")]

    res_conc = mgr.calculate_position_size(
        symbol="SOL/USDT",
        entry_price_usdt=Decimal("100"),
        stop_price_usdt=Decimal("95"),
        inr_per_usdt=Decimal("85"),
        portfolio=initial_portfolio,
        open_positions=two_open,
        risk_state=_risk_state(initial_portfolio),
    )
    assert res_conc.approved is False
    assert "concurrent positions" in (res_conc.rejection_reason or "").lower()

    res_daily = mgr.calculate_position_size(
        symbol="SOL/USDT",
        entry_price_usdt=Decimal("100"),
        stop_price_usdt=Decimal("95"),
        inr_per_usdt=Decimal("85"),
        portfolio=initial_portfolio,
        open_positions=[],
        risk_state=_risk_state(initial_portfolio, daily_entries=5),
    )
    assert res_daily.approved is False
    assert "daily entries" in (res_daily.rejection_reason or "").lower()


def test_daily_loss_limit_and_max_drawdown_enforced(
    initial_portfolio: PortfolioState,
) -> None:
    mgr = IndependentRiskManager(allowed_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"])

    # 2% daily loss: daily start = 10,000, current cash = 9,790 -> 2.1% loss
    daily_lost = initial_portfolio.model_copy(update={"cash_balance_inr": Decimal("9790.00")})
    res_dl = mgr.calculate_position_size(
        symbol="BTC/USDT",
        entry_price_usdt=Decimal("90000"),
        stop_price_usdt=Decimal("88000"),
        inr_per_usdt=Decimal("85"),
        portfolio=daily_lost,
        open_positions=[],
        risk_state=_risk_state(daily_lost, daily_start=Decimal("10000.00"), peak=Decimal("10000")),
    )
    assert res_dl.approved is False
    assert "daily loss limit" in (res_dl.rejection_reason or "").lower()

    # 8% max drawdown: peak = 11,000, daily start = 10,100, current = 10,050 -> 8.63% DD
    dd_port = initial_portfolio.model_copy(update={"cash_balance_inr": Decimal("10050.00")})
    res_dd = mgr.calculate_position_size(
        symbol="BTC/USDT",
        entry_price_usdt=Decimal("90000"),
        stop_price_usdt=Decimal("88000"),
        inr_per_usdt=Decimal("85"),
        portfolio=dd_port,
        open_positions=[],
        risk_state=_risk_state(dd_port, daily_start=Decimal("10100.00"), peak=Decimal("11000.00")),
    )
    assert res_dd.approved is False
    assert "drawdown" in (res_dd.rejection_reason or "").lower()


def test_invalid_orders_and_forbidden_leverage_rejected(
    initial_portfolio: PortfolioState, btc_quote: TickerQuote
) -> None:
    mgr = IndependentRiskManager(allowed_symbols=["BTC/USDT"])

    with pytest.raises(LiveTradingForbiddenError):
        mgr.validate_order(
            PaperOrderRequest(
                portfolio_id=initial_portfolio.id,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                quantity=Decimal("0.001"),
                leverage=Decimal("3"),
            ),
            initial_portfolio,
            btc_quote,
            Decimal("85"),
        )

    with pytest.raises(RiskViolationError):
        mgr.validate_order(
            PaperOrderRequest(
                portfolio_id=initial_portfolio.id,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                quantity=Decimal("0"),
            ),
            initial_portfolio,
            btc_quote,
            Decimal("85"),
        )

