"""Unit tests for SpotPaperBroker simulated fills."""

from decimal import Decimal

from nexus.application.paper_broker import SpotPaperBroker
from nexus.application.risk_guard import SpotPaperRiskGuard
from nexus.domain.enums import OrderSide, OrderStatus
from nexus.domain.models import PaperOrderRequest, PortfolioState, TickerQuote


def test_paper_broker_buy_and_sell_cycle(
    initial_portfolio: PortfolioState, btc_quote: TickerQuote
) -> None:
    guard = SpotPaperRiskGuard(
        allowed_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        fee_bps=Decimal("10"),
        slippage_bps=Decimal("5"),
    )
    broker = SpotPaperBroker(
        risk_guard=guard,
        fee_bps=Decimal("10"),
        slippage_bps=Decimal("5"),
    )
    fx = Decimal("85.00")

    buy_req = PaperOrderRequest(
        portfolio_id=initial_portfolio.id,
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.001"),
    )
    buy_res = broker.execute_order(buy_req, initial_portfolio, btc_quote, fx)

    assert buy_res.status == OrderStatus.FILLED
    assert buy_res.fill is not None
    assert initial_portfolio.cash_balance_inr < Decimal("10000.00")
    assert initial_portfolio.holdings["BTC"].free_qty == Decimal("0.001")

    sell_req = PaperOrderRequest(
        portfolio_id=initial_portfolio.id,
        symbol="BTC/USDT",
        side=OrderSide.SELL,
        quantity=Decimal("0.001"),
    )
    sell_res = broker.execute_order(sell_req, initial_portfolio, btc_quote, fx)

    assert sell_res.status == OrderStatus.FILLED
    assert initial_portfolio.holdings["BTC"].free_qty == Decimal("0")
    # Net cash slightly below 10000 due to spread + fees + slippage
    assert initial_portfolio.cash_balance_inr < Decimal("10000.00")


def test_paper_broker_rejects_insufficient_funds_cleanly(
    initial_portfolio: PortfolioState, btc_quote: TickerQuote
) -> None:
    guard = SpotPaperRiskGuard(allowed_symbols=["BTC/USDT"])
    broker = SpotPaperBroker(risk_guard=guard)

    req = PaperOrderRequest(
        portfolio_id=initial_portfolio.id,
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.5"),
    )
    res = broker.execute_order(req, initial_portfolio, btc_quote, Decimal("85.00"))
    assert res.status == OrderStatus.REJECTED
    assert res.fill is None
    assert res.rejection_reason is not None

