"""Unit tests for NEXUS event-driven backtester: bias, stops, fees, metrics, benchmark."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from nexus.application.backtesting.engine import EventDrivenBacktester
from nexus.application.backtesting.models import AssetListingWindow, BacktestConfig
from nexus.core.exceptions import BacktestBiasError, IncompleteCandleError
from nexus.domain.enums import SignalDirection
from nexus.domain.models import OHLCVBar, PortfolioState, PositionContext, StrategySignal


def _bar(
    idx: int,
    *,
    o: float,
    h: float,
    low_p: float,
    c: float,
    vol: float = 100.0,
    is_closed: bool = True,
) -> OHLCVBar:
    ts = datetime(2026, 10, 1, 0, 0, tzinfo=UTC) + timedelta(minutes=15 * idx)
    return OHLCVBar(
        symbol="BTC/USDT",
        timeframe="15m",
        timestamp=ts,
        open=Decimal(f"{o:.2f}"),
        high=Decimal(f"{h:.2f}"),
        low=Decimal(f"{low_p:.2f}"),
        close=Decimal(f"{c:.2f}"),
        volume=Decimal(f"{vol:.2f}"),
        is_closed=is_closed,
    )


class _SpyFixedBarEvaluator:
    """Emits a deterministic LONG on bar index `entry_idx` and EXIT on `exit_idx`."""

    def __init__(self, *, entry_idx: int, exit_idx: int | None, stop_price: Decimal) -> None:
        self._entry_idx = entry_idx
        self._exit_idx = exit_idx
        self._stop_price = stop_price
        self.observed_prefix_lengths: list[int] = []
        self.observed_last_timestamps: list[datetime] = []

    def evaluate_closed_prefix(
        self,
        *,
        symbol: str,
        timeframe: str,
        closed_bars: Sequence[OHLCVBar],
        portfolio: PortfolioState,
        position: PositionContext | None,
        now_utc: datetime,
    ) -> StrategySignal | None:
        # Must never see future bars beyond now_utc
        last_bar = closed_bars[-1]
        assert last_bar.timestamp + timedelta(minutes=15) == now_utc
        self.observed_prefix_lengths.append(len(closed_bars))
        self.observed_last_timestamps.append(last_bar.timestamp)

        idx = len(closed_bars) - 1
        if idx == self._entry_idx and position is None:
            return StrategySignal(
                symbol=symbol,
                timestamp=last_bar.timestamp,
                direction=SignalDirection.LONG,
                entry_price=last_bar.close,
                stop_price=self._stop_price,
                strategy_name="spy_v1",
                reason="Test causal LONG signal",
            )
        if self._exit_idx is not None and idx == self._exit_idx and position is not None:
            return StrategySignal(
                symbol=symbol,
                timestamp=last_bar.timestamp,
                direction=SignalDirection.EXIT_LONG,
                entry_price=last_bar.close,
                stop_price=self._stop_price,
                strategy_name="spy_v1",
                reason="Test causal EXIT signal",
            )
        return None


def test_no_lookahead_signal_fills_next_bar_open_and_rejects_incomplete_bars() -> None:
    bars = [
        _bar(0, o=100, h=102, low_p=99, c=101),
        _bar(1, o=101, h=103, low_p=100, c=102),  # LONG signal emitted on bar 1 close
        _bar(2, o=110, h=112, low_p=108, c=111),  # Fills at bar 2 open = 110 (NOT bar 1 close!)
        _bar(3, o=111, h=122, low_p=110, c=120),  # EXIT signal emitted on bar 3 close
        _bar(4, o=125, h=126, low_p=123, c=124),  # Fills at bar 4 open = 125 (NOT bar 3 close!)
        _bar(5, o=124, h=125, low_p=123, c=124),
    ]
    cfg = BacktestConfig(
        symbol="BTC/USDT",
        timeframe="15m",
        spread_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
        maker_fee_bps=Decimal("10"),
        taker_fee_bps=Decimal("10"),
        use_risk_manager=False,
    )
    spy = _SpyFixedBarEvaluator(entry_idx=1, exit_idx=3, stop_price=Decimal("90.00"))
    result = EventDrivenBacktester().run(
        scored_bars=bars,
        backtest_config=cfg,
        strategy_evaluator=spy,
    )

    assert spy.observed_prefix_lengths == [1, 2, 3, 4, 5]
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_signal_at == bars[1].timestamp
    assert trade.entry_filled_at == bars[2].timestamp
    assert trade.entry_ref_price_usdt == Decimal("110.00")
    assert trade.exit_filled_at == bars[4].timestamp
    assert trade.exit_ref_price_usdt == Decimal("125.00")

    # Incomplete bar must be rejected cleanly
    bad_bars = [*bars[:-1], bars[-1].model_copy(update={"is_closed": False})]
    with pytest.raises(IncompleteCandleError):
        EventDrivenBacktester().run(scored_bars=bad_bars, backtest_config=cfg)


def test_survivorship_bias_listing_windows_enforced() -> None:
    bars = [_bar(i, o=100 + i, h=102 + i, low_p=99 + i, c=101 + i) for i in range(6)]
    cfg = BacktestConfig(symbol="BTC/USDT", timeframe="15m", use_risk_manager=False)

    # Asset listed AFTER backtest start -> survivorship/look-ahead violation
    late_listing = [
        AssetListingWindow(
            symbol="BTC/USDT",
            listed_at_utc=bars[2].timestamp,
        )
    ]
    with pytest.raises(BacktestBiasError, match="precedes listing"):
        EventDrivenBacktester().run(
            scored_bars=bars,
            backtest_config=cfg,
            listing_windows=late_listing,
        )

    # Asset delisted inside window -> survivorship violation
    early_delist = [
        AssetListingWindow(
            symbol="BTC/USDT",
            listed_at_utc=bars[0].timestamp - timedelta(days=1),
            delisted_at_utc=bars[3].timestamp,
        )
    ]
    with pytest.raises(BacktestBiasError, match="delisted"):
        EventDrivenBacktester().run(
            scored_bars=bars,
            backtest_config=cfg,
            listing_windows=early_delist,
        )


def test_conservative_stop_loss_models_gap_down_before_intrabar_rally() -> None:
    bars = [
        _bar(0, o=100, h=101, low_p=99, c=100),  # Entry signal emitted
        _bar(1, o=100, h=102, low_p=99.5, c=101),  # Buy filled at 100, stop = 98
        # Bar 2 gaps DOWN at open to 95.0 (below stop 98.0), even though intrabar high hit 110!
        _bar(2, o=95, h=110, low_p=94, c=109),
        _bar(3, o=109, h=111, low_p=108, c=110),
    ]
    cfg = BacktestConfig(
        symbol="BTC/USDT",
        timeframe="15m",
        spread_bps=Decimal("4"),
        slippage_bps=Decimal("10"),
        taker_fee_bps=Decimal("10"),
        conservative_stop_model=True,
        use_risk_manager=False,
    )
    spy = _SpyFixedBarEvaluator(entry_idx=0, exit_idx=None, stop_price=Decimal("98.00"))
    result = EventDrivenBacktester().run(
        scored_bars=bars,
        backtest_config=cfg,
        strategy_evaluator=spy,
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    # Gap-down fills conservatively at bar 2 open (95.00), not optimistically at stop (98.00)
    assert trade.exit_ref_price_usdt == Decimal("95.00")
    assert trade.exit_exec_price_usdt < Decimal("95.00")
    assert "Conservative stop_loss" in trade.exit_reason
    assert trade.net_pnl_inr < Decimal("0")


def test_maker_taker_fees_spread_slippage_and_gross_vs_net_separation() -> None:
    bars = [
        _bar(0, o=100, h=101, low_p=99, c=100),
        _bar(1, o=100, h=104, low_p=99, c=103),
        _bar(2, o=103, h=112, low_p=102, c=110),
        _bar(3, o=115, h=118, low_p=114, c=116),
    ]

    taker_cfg = BacktestConfig(
        symbol="BTC/USDT",
        timeframe="15m",
        maker_fee_bps=Decimal("2.0"),
        taker_fee_bps=Decimal("20.0"),
        spread_bps=Decimal("6.0"),
        slippage_bps=Decimal("10.0"),
        entry_liquidity="taker",
        exit_liquidity="taker",
        use_risk_manager=False,
    )
    maker_cfg = taker_cfg.model_copy(update={"entry_liquidity": "maker", "exit_liquidity": "maker"})

    spy_taker = _SpyFixedBarEvaluator(entry_idx=0, exit_idx=2, stop_price=Decimal("90.00"))
    spy_maker = _SpyFixedBarEvaluator(entry_idx=0, exit_idx=2, stop_price=Decimal("90.00"))

    taker_res = EventDrivenBacktester().run(
        scored_bars=bars, backtest_config=taker_cfg, strategy_evaluator=spy_taker
    )
    maker_res = EventDrivenBacktester().run(
        scored_bars=bars, backtest_config=maker_cfg, strategy_evaluator=spy_maker
    )

    tm = taker_res.metrics
    mm = maker_res.metrics
    # Gross must strictly exceed net when execution costs exist (never report gross as net)
    assert tm.gross_profit_inr > tm.net_profit_inr
    assert tm.gross_return_pct > tm.total_return_pct
    assert tm.gross_profit_inr - tm.net_profit_inr == tm.fee_impact.total_execution_drag_inr

    # Maker fees/zero slippage yield strictly better net profit and lower drag than taker
    assert mm.net_profit_inr > tm.net_profit_inr
    assert mm.fee_impact.total_execution_drag_inr < tm.fee_impact.total_execution_drag_inr
    assert mm.fee_impact.total_slippage_cost_inr == Decimal("0.00")
    assert tm.fee_impact.total_slippage_cost_inr > Decimal("0.00")

    # Check all required summary metrics & benchmark fields
    assert tm.number_of_trades == 1
    assert tm.win_rate_pct == 100.0
    assert tm.avg_holding_time_hours == pytest.approx(0.5, rel=1e-4)
    assert taker_res.benchmark.benchmark_name == "spot_buy_and_hold"
    assert taker_res.benchmark.excess_net_return_pct == pytest.approx(
        tm.total_return_pct - taker_res.benchmark.benchmark_metrics.total_return_pct,
        abs=1e-3,
    )

