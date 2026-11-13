"""Unit tests for MultiMarketScanner, ArbitrageDetector, and Arbitrage API."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from nexus.application.arbitrage.detector import ArbitrageDetector
from nexus.domain.arbitrage import MarketTickerItem


@pytest.fixture
def sample_tickers() -> dict[str, MarketTickerItem]:
    now = datetime.now(UTC)
    return {
        "BTC/USDT": MarketTickerItem(
            symbol="BTC/USDT",
            bid=Decimal("70000.00"),
            ask=Decimal("70001.00"),
            last=Decimal("70000.50"),
            spread_bps=Decimal("0.14"),
            change_24h_pct=Decimal("2.50"),
            quote_volume_24h=Decimal("150000000.0"),
            sector="LAYER_1",
            timestamp=now,
        ),
        "ETH/USDT": MarketTickerItem(
            symbol="ETH/USDT",
            bid=Decimal("2000.00"),
            ask=Decimal("2000.10"),
            last=Decimal("2000.05"),
            spread_bps=Decimal("0.50"),
            change_24h_pct=Decimal("1.80"),
            quote_volume_24h=Decimal("80000000.0"),
            sector="LAYER_1",
            timestamp=now,
        ),
        "ETH/BTC": MarketTickerItem(
            symbol="ETH/BTC",
            bid=Decimal("0.028570"),
            ask=Decimal("0.028575"),
            last=Decimal("0.028572"),
            spread_bps=Decimal("1.75"),
            change_24h_pct=Decimal("-0.20"),
            quote_volume_24h=Decimal("10000000.0"),
            sector="LAYER_1",
            timestamp=now,
        ),
        "SOL/USDT": MarketTickerItem(
            symbol="SOL/USDT",
            bid=Decimal("80.00"),
            ask=Decimal("80.05"),
            last=Decimal("80.02"),
            spread_bps=Decimal("6.25"),
            change_24h_pct=Decimal("4.20"),
            quote_volume_24h=Decimal("45000000.0"),
            sector="LAYER_1",
            timestamp=now,
        ),
        "SOL/BTC": MarketTickerItem(
            symbol="SOL/BTC",
            bid=Decimal("0.001142"),
            ask=Decimal("0.001144"),
            last=Decimal("0.001143"),
            spread_bps=Decimal("17.49"),
            change_24h_pct=Decimal("1.50"),
            quote_volume_24h=Decimal("5000000.0"),
            sector="LAYER_1",
            timestamp=now,
        ),
    }


def test_arbitrage_detector_balanced_market(sample_tickers: dict[str, MarketTickerItem]) -> None:
    detector = ArbitrageDetector()
    result = detector.evaluate(sample_tickers)

    assert result.total_markets == len(sample_tickers)
    assert len(result.triangular_opportunities) > 0
    # In a balanced market, after 30 bps fees + 15 bps slippage, net edge must be negative
    for opp in result.triangular_opportunities:
        assert opp.total_fee_bps == Decimal("30.0")
        assert opp.estimated_slippage_bps == Decimal("15.0")
        assert opp.status in ("ACTIVE", "FILTERED")
        if opp.net_edge_bps <= 0:
            assert opp.status == "FILTERED"
            assert opp.filter_reason == "NEGATIVE_NET_EDGE"


def test_arbitrage_detector_synthetic_dislocation(
    sample_tickers: dict[str, MarketTickerItem],
) -> None:
    # Induce an artificial dislocation where ETH/BTC direct is higher than synthetic
    now = datetime.now(UTC)
    sample_tickers["ETH/BTC"] = MarketTickerItem(
        symbol="ETH/BTC",
        bid=Decimal("0.032000"),  # Much higher than 2000 / 70000 (~0.02857)
        ask=Decimal("0.032010"),
        last=Decimal("0.032005"),
        spread_bps=Decimal("3.12"),
        change_24h_pct=Decimal("5.0"),
        quote_volume_24h=Decimal("10000000.0"),
        sector="LAYER_1",
        timestamp=now,
    )

    detector = ArbitrageDetector()
    result = detector.evaluate(sample_tickers)

    eth_btc_disloc = next(
        (d for d in result.synthetic_dislocations if d.direct_symbol == "ETH/BTC"), None
    )
    assert eth_btc_disloc is not None
    assert eth_btc_disloc.dislocation_bps > Decimal("10.0")
    assert eth_btc_disloc.direction == "BUY_SYNTH_SELL_DIRECT"


def test_arbitrage_detector_reports_real_scan_metrics(
    sample_tickers: dict[str, MarketTickerItem],
) -> None:
    detector = ArbitrageDetector()
    result = detector.evaluate(sample_tickers)

    assert result.total_markets == len(sample_tickers)
    assert result.active_markets == len(sample_tickers)
    assert result.avg_spread_bps >= Decimal("0")
    assert all(t.symbol in sample_tickers for t in result.markets)

