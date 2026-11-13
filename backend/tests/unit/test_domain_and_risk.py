"""Unit tests for domain invariants and SpotPaperRiskGuard."""

from decimal import Decimal

import pytest

from nexus.application.risk_guard import SpotPaperRiskGuard
from nexus.core.exceptions import (
    InsufficientBalanceError,
    LiveTradingForbiddenError,
    RiskViolationError,
)
from nexus.domain.enums import MarketType, OrderSide, TradingMode
from nexus.domain.models import PaperOrderRequest, PortfolioState, TickerQuote


def test_risk_guard_blocks_leverage_and_withdrawals(
    initial_portfolio: PortfolioState, btc_quote: TickerQuote
) -> None:
    guard = SpotPaperRiskGuard(allowed_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"])

    leveraged_req = PaperOrderRequest(
        portfolio_id=initial_portfolio.id,
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.001"),
        leverage=Decimal("2"),
    )
    with pytest.raises(LiveTradingForbiddenError):
        guard.validate_order(leveraged_req, initial_portfolio, btc_quote, Decimal("85"))

    withdrawal_req = PaperOrderRequest(
        portfolio_id=initial_portfolio.id,
        symbol="BTC/USDT",
        side=OrderSide.SELL,
        quantity=Decimal("0.001"),
        is_withdrawal=True,
    )
    with pytest.raises(LiveTradingForbiddenError):
        guard.validate_order(withdrawal_req, initial_portfolio, btc_quote, Decimal("85"))


def test_risk_guard_blocks_non_spot_or_live_portfolio(
    initial_portfolio: PortfolioState, btc_quote: TickerQuote
) -> None:
    guard = SpotPaperRiskGuard(allowed_symbols=["BTC/USDT"])
    bad_portfolio = initial_portfolio.model_copy(
        update={"trading_mode": TradingMode.PAPER, "market_type": MarketType.SPOT}
    )
    bad_req = PaperOrderRequest(
        portfolio_id=bad_portfolio.id,
        symbol="DOGE/USDT",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
    )
    with pytest.raises(RiskViolationError):
        guard.validate_order(bad_req, bad_portfolio, btc_quote, Decimal("85"))


def test_risk_guard_blocks_short_selling_and_overspend(
    initial_portfolio: PortfolioState, btc_quote: TickerQuote
) -> None:
    guard = SpotPaperRiskGuard(allowed_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"])

    sell_without_holding = PaperOrderRequest(
        portfolio_id=initial_portfolio.id,
        symbol="BTC/USDT",
        side=OrderSide.SELL,
        quantity=Decimal("0.01"),
    )
    with pytest.raises(InsufficientBalanceError):
        guard.validate_order(sell_without_holding, initial_portfolio, btc_quote, Decimal("85"))

    overspend_buy = PaperOrderRequest(
        portfolio_id=initial_portfolio.id,
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        quantity=Decimal("1.0"),
    )
    with pytest.raises(InsufficientBalanceError):
        guard.validate_order(overspend_buy, initial_portfolio, btc_quote, Decimal("85"))

