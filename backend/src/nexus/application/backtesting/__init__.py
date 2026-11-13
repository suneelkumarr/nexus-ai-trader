"""Event-driven causal historical backtesting and out-of-sample reporting package."""

from nexus.application.backtesting.engine import (
    EventDrivenBacktester,
    StrategyBarEvaluator,
    StrategyV1BacktestAdapter,
)
from nexus.application.backtesting.metrics import (
    compare_to_benchmark,
    compute_max_drawdown_pct,
    compute_performance_metrics,
    compute_sharpe_ratio,
    simulate_buy_and_hold,
)
from nexus.application.backtesting.models import (
    AssetListingWindow,
    BacktestConfig,
    BacktestRunResult,
    BacktestSuiteReport,
    BacktestTradeRecord,
    BenchmarkComparison,
    DatasetSplitBounds,
    EquityPoint,
    FeeImpactBreakdown,
    FillEvent,
    OptimizationCandidateScore,
    OrderEvent,
    PerformanceMetrics,
)
from nexus.application.backtesting.reports import BacktestReportGenerator
from nexus.application.backtesting.splits import (
    ChronologicalDatasetSplits,
    OutOfSampleBacktestRunner,
    ParameterOptimizer,
    split_ohlcv_periods,
)

__all__ = [
    "AssetListingWindow",
    "BacktestConfig",
    "BacktestReportGenerator",
    "BacktestRunResult",
    "BacktestSuiteReport",
    "BacktestTradeRecord",
    "BenchmarkComparison",
    "ChronologicalDatasetSplits",
    "DatasetSplitBounds",
    "EquityPoint",
    "EventDrivenBacktester",
    "FeeImpactBreakdown",
    "FillEvent",
    "OptimizationCandidateScore",
    "OrderEvent",
    "OutOfSampleBacktestRunner",
    "ParameterOptimizer",
    "PerformanceMetrics",
    "StrategyBarEvaluator",
    "StrategyV1BacktestAdapter",
    "compare_to_benchmark",
    "compute_max_drawdown_pct",
    "compute_performance_metrics",
    "compute_sharpe_ratio",
    "simulate_buy_and_hold",
    "split_ohlcv_periods",
]

