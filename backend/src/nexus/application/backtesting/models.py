"""Immutable Pydantic models for the NEXUS event-driven historical backtesting engine."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from nexus.core.exceptions import BacktestValidationError
from nexus.core.risk_config import RiskConfig
from nexus.core.strategy_config import StrategyV1Config
from nexus.domain.enums import OrderSide, OrderType, SignalDirection


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise BacktestValidationError("Timestamps in backtest configs must be timezone-aware UTC.")
    return value.astimezone(UTC)


class AssetListingWindow(BaseModel):
    """Point-in-time listing bounds used to guard against survivorship bias."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    listed_at_utc: datetime
    delisted_at_utc: datetime | None = None

    @field_validator("listed_at_utc")
    @classmethod
    def check_listed_utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)

    @field_validator("delisted_at_utc")
    @classmethod
    def check_delisted_utc(cls, value: datetime | None) -> datetime | None:
        return _ensure_utc(value) if value is not None else None


class BacktestConfig(BaseModel):
    """Configuration for deterministic spot-only event-driven historical simulation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = "BTC/USDT"
    timeframe: str = "15m"
    initial_capital_inr: Decimal = Field(default=Decimal("10000.00"), gt=Decimal("0"))
    inr_per_usdt: Decimal = Field(default=Decimal("85.00"), gt=Decimal("0"))
    maker_fee_bps: Decimal = Field(default=Decimal("10.0"), ge=Decimal("0"), le=Decimal("500"))
    taker_fee_bps: Decimal = Field(default=Decimal("10.0"), ge=Decimal("0"), le=Decimal("500"))
    spread_bps: Decimal = Field(default=Decimal("4.0"), ge=Decimal("0"), le=Decimal("500"))
    slippage_bps: Decimal = Field(default=Decimal("5.0"), ge=Decimal("0"), le=Decimal("500"))
    entry_liquidity: Literal["taker", "maker"] = "taker"
    exit_liquidity: Literal["taker", "maker"] = "taker"
    use_risk_manager: bool = True
    risk_config: RiskConfig = Field(default_factory=RiskConfig)
    conservative_stop_model: bool = True
    close_open_positions_at_end: bool = True
    train_ratio: float = Field(default=0.6, gt=0.0, lt=1.0)
    validation_ratio: float = Field(default=0.2, gt=0.0, lt=1.0)
    test_ratio: float = Field(default=0.2, gt=0.0, lt=1.0)
    annualization_periods_per_year: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def check_split_sum(self) -> "BacktestConfig":
        total = self.train_ratio + self.validation_ratio + self.test_ratio
        if abs(total - 1.0) > 1e-6:
            raise BacktestValidationError(
                f"train_ratio + validation_ratio + test_ratio must equal 1.0, got {total:.6f}."
            )
        norm = self.symbol.strip().upper()
        if "/" not in norm or ":" in norm or "PERP" in norm:
            raise BacktestValidationError(
                f"Only spot pairs are supported for backtesting, got '{self.symbol}'."
            )
        return self


class OrderEvent(BaseModel):
    """Pending spot order emitted on bar t close for execution on bar t+1 open."""

    model_config = ConfigDict(frozen=True)

    order_id: UUID = Field(default_factory=uuid4)
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    liquidity_role: Literal["maker", "taker"] = "taker"
    direction: SignalDirection
    signal_timestamp: datetime
    reference_signal_price_usdt: Decimal = Field(gt=Decimal("0"))
    stop_price_usdt: Decimal = Field(ge=Decimal("0"))
    atr_at_signal: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    reason: str


class FillEvent(BaseModel):
    """Simulated execution fill accounting for spread, slippage, and maker/taker fees."""

    model_config = ConfigDict(frozen=True)

    order_id: UUID
    symbol: str
    side: OrderSide
    liquidity_role: Literal["maker", "taker"]
    reference_price_usdt: Decimal = Field(gt=Decimal("0"))
    executed_price_usdt: Decimal = Field(gt=Decimal("0"))
    quantity: Decimal = Field(gt=Decimal("0"))
    gross_notional_inr: Decimal = Field(gt=Decimal("0"))
    net_cash_delta_inr: Decimal
    spread_cost_inr: Decimal = Field(ge=Decimal("0"))
    slippage_cost_inr: Decimal = Field(ge=Decimal("0"))
    fee_inr: Decimal = Field(ge=Decimal("0"))
    executed_at: datetime
    reason: str


class BacktestTradeRecord(BaseModel):
    """Closed round-trip spot trade capturing both gross and net execution performance."""

    model_config = ConfigDict(frozen=True)

    trade_index: int = Field(ge=1)
    symbol: str
    quantity: Decimal = Field(gt=Decimal("0"))
    entry_signal_at: datetime
    entry_filled_at: datetime
    exit_filled_at: datetime
    holding_seconds: float = Field(ge=0.0)
    entry_ref_price_usdt: Decimal = Field(gt=Decimal("0"))
    entry_exec_price_usdt: Decimal = Field(gt=Decimal("0"))
    exit_ref_price_usdt: Decimal = Field(gt=Decimal("0"))
    exit_exec_price_usdt: Decimal = Field(gt=Decimal("0"))
    entry_liquidity: Literal["maker", "taker"]
    exit_liquidity: Literal["maker", "taker"]
    gross_pnl_inr: Decimal
    net_pnl_inr: Decimal
    net_return_pct: float
    total_fees_inr: Decimal = Field(ge=Decimal("0"))
    total_spread_cost_inr: Decimal = Field(ge=Decimal("0"))
    total_slippage_cost_inr: Decimal = Field(ge=Decimal("0"))
    exit_reason: str


class FeeImpactBreakdown(BaseModel):
    """Explicit breakdown of maker/taker fees, spread, and slippage drag."""

    model_config = ConfigDict(frozen=True)

    total_fees_inr: Decimal = Field(ge=Decimal("0"))
    total_spread_cost_inr: Decimal = Field(ge=Decimal("0"))
    total_slippage_cost_inr: Decimal = Field(ge=Decimal("0"))
    total_execution_drag_inr: Decimal = Field(ge=Decimal("0"))
    fee_drag_pct_of_initial_capital: float = Field(ge=0.0)
    gross_minus_net_inr: Decimal


class PerformanceMetrics(BaseModel):
    """Complete risk-adjusted backtest performance metrics (net explicitly separated from gross)."""

    model_config = ConfigDict(frozen=True)

    initial_capital_inr: Decimal
    final_equity_inr: Decimal
    gross_profit_inr: Decimal
    gross_return_pct: float
    total_return_pct: float
    net_profit_inr: Decimal
    win_rate_pct: float = Field(ge=0.0, le=100.0)
    profit_factor: float | None = Field(default=None, ge=0.0)
    max_drawdown_pct: float = Field(ge=0.0)
    sharpe_ratio: float
    avg_holding_time_seconds: float = Field(ge=0.0)
    avg_holding_time_hours: float = Field(ge=0.0)
    number_of_trades: int = Field(ge=0)
    fee_impact: FeeImpactBreakdown


class BenchmarkComparison(BaseModel):
    """Comparison between NEXUS strategy net metrics and spot buy-and-hold benchmark."""

    model_config = ConfigDict(frozen=True)

    benchmark_name: str = "spot_buy_and_hold"
    benchmark_metrics: PerformanceMetrics
    excess_net_return_pct: float
    excess_net_profit_inr: Decimal
    drawdown_difference_pct: float
    sharpe_difference: float


class EquityPoint(BaseModel):
    """Bar-level portfolio valuation snapshot along the simulation timeline."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    cash_inr: Decimal
    holdings_qty: Decimal
    mark_close_usdt: Decimal
    equity_inr: Decimal
    benchmark_equity_inr: Decimal


class DatasetSplitBounds(BaseModel):
    """Chronological non-overlapping split boundaries."""

    model_config = ConfigDict(frozen=True)

    split_name: Literal["train", "validation", "test", "full"]
    start_timestamp: datetime
    end_timestamp: datetime
    warmup_bars_count: int = Field(ge=0)
    scored_bars_count: int = Field(ge=1)


class BacktestRunResult(BaseModel):
    """Complete output of running the event-driven backtester over a candle window."""

    model_config = ConfigDict(frozen=True)

    split: DatasetSplitBounds
    symbol: str
    timeframe: str
    strategy_config: StrategyV1Config
    backtest_config: BacktestConfig
    metrics: PerformanceMetrics
    benchmark: BenchmarkComparison
    trades: list[BacktestTradeRecord]
    fills: list[FillEvent]
    equity_curve: list[EquityPoint]
    rejected_signals_count: int = Field(ge=0)


class OptimizationCandidateScore(BaseModel):
    """Scored candidate parameter set evaluated strictly on train/validation periods."""

    model_config = ConfigDict(frozen=True)

    strategy_config: StrategyV1Config
    train_net_return_pct: float
    validation_net_return_pct: float
    validation_sharpe_ratio: float
    validation_max_drawdown_pct: float
    objective_score: float


class BacktestSuiteReport(BaseModel):
    """Complete train/validation/out-of-sample test report package ready for HTML/JSON export."""

    model_config = ConfigDict(frozen=True)

    report_id: str
    generated_at: datetime
    symbol: str
    timeframe: str
    selected_strategy_config: StrategyV1Config
    optimized_on_splits: tuple[Literal["train", "validation"], ...] = ("train", "validation")
    out_of_sample_verified: Literal[True] = True
    train_result: BacktestRunResult
    validation_result: BacktestRunResult
    test_result: BacktestRunResult
    optimization_leaderboard: list[OptimizationCandidateScore] = Field(default_factory=list)

