"""Train/Validation/Test chronological splitting and leak-free out-of-sample runner."""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from nexus.application.backtesting.engine import EventDrivenBacktester, StrategyBarEvaluator
from nexus.application.backtesting.models import (
    AssetListingWindow,
    BacktestConfig,
    BacktestSuiteReport,
    OptimizationCandidateScore,
)
from nexus.application.strategy.config import StrategyV1Config
from nexus.core.exceptions import BacktestBiasError, BacktestValidationError
from nexus.domain.models import OHLCVBar


@dataclass(frozen=True)
class ChronologicalDatasetSplits:
    """Strictly ordered non-overlapping Train / Validation / Test OHLCV partitions."""

    train: list[OHLCVBar]
    validation: list[OHLCVBar]
    test: list[OHLCVBar]


def split_ohlcv_periods(
    bars: Sequence[OHLCVBar],
    *,
    train_ratio: float = 0.6,
    validation_ratio: float = 0.2,
    test_ratio: float = 0.2,
    min_bars_per_split: int = 10,
) -> ChronologicalDatasetSplits:
    """Split bars chronologically into non-overlapping Train, Validation, and Test sets."""
    total_ratio = train_ratio + validation_ratio + test_ratio
    if abs(total_ratio - 1.0) > 1e-6 or min(train_ratio, validation_ratio, test_ratio) <= 0.0:
        raise BacktestValidationError(
            "Split ratios must be strictly positive and sum to 1.0."
        )

    ordered = sorted(bars, key=lambda b: b.timestamp)
    n = len(ordered)
    if n < min_bars_per_split * 3:
        raise BacktestValidationError(
            f"Need at least {min_bars_per_split * 3} bars for 3-way split, got {n}."
        )

    train_end = max(min_bars_per_split, int(n * train_ratio))
    val_end = max(train_end + min_bars_per_split, int(n * (train_ratio + validation_ratio)))
    if n - val_end < min_bars_per_split:
        val_end = n - min_bars_per_split
    if val_end - train_end < min_bars_per_split or train_end < min_bars_per_split:
        raise BacktestValidationError(
            f"Insufficient bars ({n}) to satisfy minimum {min_bars_per_split} bars per split."
        )

    train_bars = list(ordered[:train_end])
    val_bars = list(ordered[train_end:val_end])
    test_bars = list(ordered[val_end:])

    if train_bars[-1].timestamp >= val_bars[0].timestamp:
        raise BacktestBiasError("Train split overlaps validation split timestamps.")
    if val_bars[-1].timestamp >= test_bars[0].timestamp:
        raise BacktestBiasError("Validation split overlaps out-of-sample test split timestamps.")

    return ChronologicalDatasetSplits(train=train_bars, validation=val_bars, test=test_bars)


class ParameterOptimizer:
    """Grid optimizer restricted strictly to Train and Validation splits (never Test)."""

    def __init__(self, *, backtester: EventDrivenBacktester | None = None) -> None:
        self._backtester = backtester or EventDrivenBacktester()

    def select_parameters(
        self,
        *,
        train_bars: Sequence[OHLCVBar],
        validation_bars: Sequence[OHLCVBar],
        candidates: Sequence[StrategyV1Config],
        backtest_config: BacktestConfig,
        target_split: Literal["train_validation", "test"] = "train_validation",
        test_start_timestamp: datetime | None = None,
        listing_windows: Sequence[AssetListingWindow] | None = None,
    ) -> tuple[StrategyV1Config, list[OptimizationCandidateScore]]:
        """Select parameters on Train/Validation; forbid optimizing on final Test data."""
        if target_split == "test":
            raise BacktestBiasError(
                "Optimization on the final test period is strictly forbidden."
            )
        if not candidates:
            raise BacktestValidationError("At least one StrategyV1Config candidate is required.")

        if test_start_timestamp is not None:
            latest_val_ts = max(b.timestamp for b in validation_bars)
            latest_train_ts = max(b.timestamp for b in train_bars)
            if latest_val_ts >= test_start_timestamp or latest_train_ts >= test_start_timestamp:
                raise BacktestBiasError(
                    "Candidate optimization input overlaps the held-out final test period."
                )

        scored: list[OptimizationCandidateScore] = []
        for cand in candidates:
            warmup_len = max(cand.min_candles_required, 60)
            train_res = self._backtester.run(
                scored_bars=train_bars,
                strategy_config=cand,
                backtest_config=backtest_config,
                split_name="train",
                listing_windows=listing_windows,
            )
            val_warmup = train_bars[-warmup_len:]
            val_res = self._backtester.run(
                scored_bars=validation_bars,
                warmup_bars=val_warmup,
                strategy_config=cand,
                backtest_config=backtest_config,
                split_name="validation",
                listing_windows=listing_windows,
            )
            objective = round(
                val_res.metrics.sharpe_ratio
                + (val_res.metrics.total_return_pct * 0.25)
                - (val_res.metrics.max_drawdown_pct * 0.5),
                6,
            )
            scored.append(
                OptimizationCandidateScore(
                    strategy_config=cand,
                    train_net_return_pct=train_res.metrics.total_return_pct,
                    validation_net_return_pct=val_res.metrics.total_return_pct,
                    validation_sharpe_ratio=val_res.metrics.sharpe_ratio,
                    validation_max_drawdown_pct=val_res.metrics.max_drawdown_pct,
                    objective_score=objective,
                )
            )

        leaderboard = sorted(
            scored,
            key=lambda item: (
                item.objective_score,
                item.validation_net_return_pct,
                -item.validation_max_drawdown_pct,
            ),
            reverse=True,
        )
        return leaderboard[0].strategy_config, leaderboard


class OutOfSampleBacktestRunner:
    """Runs chronological Train/Validation tuning followed by frozen Out-of-Sample Testing."""

    def __init__(self, *, backtester: EventDrivenBacktester | None = None) -> None:
        self._backtester = backtester or EventDrivenBacktester()
        self._optimizer = ParameterOptimizer(backtester=self._backtester)

    def run_suite(
        self,
        *,
        bars: Sequence[OHLCVBar],
        backtest_config: BacktestConfig,
        base_strategy_config: StrategyV1Config | None = None,
        candidate_configs: Sequence[StrategyV1Config] = (),
        strategy_evaluator: StrategyBarEvaluator | None = None,
        listing_windows: Sequence[AssetListingWindow] | None = None,
        min_bars_per_split: int = 20,
        generated_at: datetime | None = None,
    ) -> BacktestSuiteReport:
        """Split data into Train/Val/Test, optionally tune on Train+Val, test out-of-sample."""
        splits = split_ohlcv_periods(
            bars,
            train_ratio=backtest_config.train_ratio,
            validation_ratio=backtest_config.validation_ratio,
            test_ratio=backtest_config.test_ratio,
            min_bars_per_split=min_bars_per_split,
        )

        leaderboard: list[OptimizationCandidateScore] = []
        if candidate_configs:
            selected_cfg, leaderboard = self._optimizer.select_parameters(
                train_bars=splits.train,
                validation_bars=splits.validation,
                candidates=candidate_configs,
                backtest_config=backtest_config,
                test_start_timestamp=splits.test[0].timestamp,
                listing_windows=listing_windows,
            )
        else:
            selected_cfg = base_strategy_config or StrategyV1Config()

        warmup_len = max(selected_cfg.min_candles_required, 60)

        train_res = self._backtester.run(
            scored_bars=splits.train,
            strategy_config=selected_cfg,
            backtest_config=backtest_config,
            split_name="train",
            strategy_evaluator=strategy_evaluator,
            listing_windows=listing_windows,
        )
        val_res = self._backtester.run(
            scored_bars=splits.validation,
            warmup_bars=splits.train[-warmup_len:],
            strategy_config=selected_cfg,
            backtest_config=backtest_config,
            split_name="validation",
            strategy_evaluator=strategy_evaluator,
            listing_windows=listing_windows,
        )
        # Strictly causal warmup from train + validation tail; ZERO look-ahead or tuning on test.
        pre_test_history = [*splits.train, *splits.validation]
        test_res = self._backtester.run(
            scored_bars=splits.test,
            warmup_bars=pre_test_history[-warmup_len:],
            strategy_config=selected_cfg,
            backtest_config=backtest_config,
            split_name="test",
            strategy_evaluator=strategy_evaluator,
            listing_windows=listing_windows,
        )

        report_ts = generated_at or splits.test[-1].timestamp
        digest_src = json.dumps(
            {
                "symbol": backtest_config.symbol,
                "timeframe": backtest_config.timeframe,
                "first_bar": splits.train[0].timestamp.isoformat(),
                "last_bar": splits.test[-1].timestamp.isoformat(),
                "strategy_config": selected_cfg.model_dump(mode="json"),
                "backtest_config": backtest_config.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        report_id = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()[:16]

        return BacktestSuiteReport(
            report_id=report_id,
            generated_at=report_ts,
            symbol=backtest_config.symbol.strip().upper(),
            timeframe=backtest_config.timeframe.strip().lower(),
            selected_strategy_config=selected_cfg,
            out_of_sample_verified=True,
            train_result=train_res,
            validation_result=val_res,
            test_result=test_res,
            optimization_leaderboard=leaderboard,
        )
