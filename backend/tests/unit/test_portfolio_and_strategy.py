"""Unit tests for PortfolioService and EmaCrossoverStrategy using pandas & numpy."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from nexus.application.portfolio_service import PortfolioService
from nexus.application.strategy_engine import EmaCrossoverStrategy, ohlcv_to_dataframe
from nexus.core.config import Settings
from nexus.domain.enums import SignalAction
from nexus.domain.models import AssetHolding, OHLCVBar, TickerQuote


def test_portfolio_valuation_with_holdings() -> None:
    settings = Settings(_env_file=None)
    service = PortfolioService(settings)
    portfolio = service.create_initial_portfolio()
    assert portfolio.initial_capital_inr == Decimal("10000.00")

    portfolio.cash_balance_inr = Decimal("5000.00")
    portfolio.holdings["SOL"] = AssetHolding(
        asset="SOL",
        free_qty=Decimal("0.5"),
        avg_entry_price_usdt=Decimal("100.00"),
    )
    sol_quote = TickerQuote(
        symbol="SOL/USDT",
        exchange_id="binance",
        bid=Decimal("120.00"),
        ask=Decimal("120.50"),
        last=Decimal("120.00"),
        timestamp=datetime.now(UTC),
    )

    valuation = service.valuate_portfolio(portfolio, {"SOL/USDT": sol_quote}, Decimal("85.00"))
    assert valuation["cash_balance_inr"] == 5000.0
    assert valuation["holdings_value_inr"] == 5100.0
    assert valuation["total_equity_inr"] == 10100.0
    assert valuation["total_return_pct"] == 1.0


def test_ema_crossover_strategy_signals() -> None:
    strategy = EmaCrossoverStrategy(fast_span=3, slow_span=8)
    start = datetime.now(UTC) - timedelta(hours=30)

    # Declining then sharp rebound to trigger bullish crossover
    closes = [100.0 - i * 0.5 for i in range(15)] + [93.0 + i * 2.0 for i in range(10)]
    bars = [
        OHLCVBar(
            symbol="BTC/USDT",
            timeframe="15m",
            timestamp=start + timedelta(minutes=15 * i),
            open=Decimal(str(price)),
            high=Decimal(str(price + 1.0)),
            low=Decimal(str(price - 1.0)),
            close=Decimal(str(price)),
            volume=Decimal("10"),
        )
        for i, price in enumerate(closes)
    ]
    df = ohlcv_to_dataframe(bars)
    signal = strategy.evaluate("BTC/USDT", df)
    assert signal.symbol == "BTC/USDT"
    assert signal.action in {SignalAction.BUY, SignalAction.HOLD, SignalAction.SELL}

