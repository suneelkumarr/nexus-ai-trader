"""Integration tests for out-of-sample split pipeline, reports, and reproducibility."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from nexus.application.backtesting.models import BacktestConfig
from nexus.application.backtesting.reports import BacktestReportGenerator
from nexus.application.backtesting.splits import (
    OutOfSampleBacktestRunner,
    ParameterOptimizer,
    split_ohlcv_periods,
)
from nexus.application.strategy.config import StrategyV1Config
from nexus.core.exceptions import BacktestBiasError
from nexus.domain.models import OHLCVBar


def _make_cyclical_bars(total_bars: int = 360) -> list[OHLCVBar]:
    """Generate deterministic multi-cycle spot bars producing valid EMA crossovers."""
    start = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    bars: list[OHLCVBar] = []
    price = 50000.0
    for i in range(total_bars):
        ts = start + timedelta(minutes=15 * i)
        phase = i % 90
        if phase < 40:
            delta = -80.0 if phase % 2 == 0 else 30.0
            vol = 90.0
        elif phase < 80:
            delta = 140.0 if phase % 3 != 2 else -100.0
            vol = 260.0 if 45 <= phase <= 65 else 130.0
        else:
            delta = -120.0
            vol = 120.0

        prev = price
        price = max(10000.0, price + delta)
        hi = max(prev, price) + 45.0
        lo = min(prev, price) - 45.0
        bars.append(
            OHLCVBar(
                symbol="BTC/USDT",
                timeframe="15m",
                timestamp=ts,
                open=Decimal(f"{prev:.2f}"),
                high=Decimal(f"{hi:.2f}"),
                low=Decimal(f"{lo:.2f}"),
                close=Decimal(f"{price:.2f}"),
                volume=Decimal(f"{vol:.2f}"),
                is_closed=True,
            )
        )
    return bars


def test_train_validation_test_separation_and_anti_optimization_guard() -> None:
    bars = _make_cyclical_bars(360)
    splits = split_ohlcv_periods(
        bars,
        train_ratio=0.6,
        validation_ratio=0.2,
        test_ratio=0.2,
        min_bars_per_split=60,
    )
    assert len(splits.train) == 216
    assert len(splits.validation) == 72
    assert len(splits.test) == 72
    assert splits.train[-1].timestamp < splits.validation[0].timestamp
    assert splits.validation[-1].timestamp < splits.test[0].timestamp

    bt_cfg = BacktestConfig(
        symbol="BTC/USDT",
        timeframe="15m",
        maker_fee_bps=Decimal("5.0"),
        taker_fee_bps=Decimal("10.0"),
        spread_bps=Decimal("4.0"),
        slippage_bps=Decimal("5.0"),
        use_risk_manager=True,
    )
    candidates = [
        StrategyV1Config(stop_atr_multiplier=Decimal("2.0"), rsi_entry_max=70.0),
        StrategyV1Config(stop_atr_multiplier=Decimal("2.5"), rsi_entry_max=75.0),
    ]

    optimizer = ParameterOptimizer()
    # Explicitly forbidden: attempting optimization on final test split
    with pytest.raises(BacktestBiasError, match="forbidden"):
        optimizer.select_parameters(
            train_bars=splits.train,
            validation_bars=splits.test,
            candidates=candidates,
            backtest_config=bt_cfg,
            target_split="test",
        )

    # Also forbidden: passing validation bars that overlap the test window
    with pytest.raises(BacktestBiasError, match="overlaps"):
        optimizer.select_parameters(
            train_bars=splits.train,
            validation_bars=splits.test,
            candidates=candidates,
            backtest_config=bt_cfg,
            test_start_timestamp=splits.test[0].timestamp,
        )

    runner = OutOfSampleBacktestRunner()
    suite = runner.run_suite(
        bars=bars,
        backtest_config=bt_cfg,
        candidate_configs=candidates,
        min_bars_per_split=60,
    )
    assert suite.optimized_on_splits == ("train", "validation")
    assert suite.out_of_sample_verified is True
    assert len(suite.optimization_leaderboard) == 2
    assert suite.train_result.split.split_name == "train"
    assert suite.validation_result.split.split_name == "validation"
    assert suite.test_result.split.split_name == "test"
    assert suite.validation_result.split.warmup_bars_count >= 50
    assert suite.test_result.split.warmup_bars_count >= 50

    # Ensure buy-and-hold benchmark and net/gross separation exist on out-of-sample test split
    test_m = suite.test_result.metrics
    assert test_m.number_of_trades >= 1
    assert test_m.net_profit_inr < test_m.gross_profit_inr
    assert test_m.fee_impact.total_execution_drag_inr > Decimal("0")
    assert suite.test_result.benchmark.benchmark_name == "spot_buy_and_hold"


def test_reproducibility_and_html_json_report_generation(tmp_path: Path) -> None:
    bars = _make_cyclical_bars(360)
    bt_cfg = BacktestConfig(
        symbol="BTC/USDT",
        timeframe="15m",
        maker_fee_bps=Decimal("8.0"),
        taker_fee_bps=Decimal("10.0"),
        spread_bps=Decimal("4.0"),
        slippage_bps=Decimal("5.0"),
    )
    candidates = [
        StrategyV1Config(stop_atr_multiplier=Decimal("2.0")),
        StrategyV1Config(stop_atr_multiplier=Decimal("3.0")),
    ]

    suite_a = OutOfSampleBacktestRunner().run_suite(
        bars=bars,
        backtest_config=bt_cfg,
        candidate_configs=candidates,
        min_bars_per_split=60,
    )
    suite_b = OutOfSampleBacktestRunner().run_suite(
        bars=bars,
        backtest_config=bt_cfg,
        candidate_configs=candidates,
        min_bars_per_split=60,
    )

    assert suite_a == suite_b

    reporter = BacktestReportGenerator()
    json_a = reporter.to_json(suite_a)
    json_b = reporter.to_json(suite_b)
    html_a = reporter.to_html(suite_a)
    html_b = reporter.to_html(suite_b)

    assert json_a == json_b
    assert html_a == html_b

    json_path = reporter.write_json(suite_a, tmp_path / "backtest_report.json")
    html_path = reporter.write_html(suite_a, tmp_path / "backtest_report.html")
    assert json_path.exists()
    assert html_path.exists()

    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    for key in (
        "total_return_pct",
        "net_profit_inr",
        "gross_profit_inr",
        "win_rate_pct",
        "profit_factor",
        "max_drawdown_pct",
        "sharpe_ratio",
        "avg_holding_time_hours",
        "number_of_trades",
        "fee_impact",
    ):
        assert key in parsed["test_result"]["metrics"]

    html_text = html_path.read_text(encoding="utf-8")
    assert "Out-of-Sample Final Test Period" in html_text
    assert "Buy &amp; Hold" in html_text
    assert "<svg" in html_text
    assert "Fee, Spread &amp; Slippage Impact" in html_text
