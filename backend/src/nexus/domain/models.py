"""Immutable Pydantic domain models for paper trading and market data."""

import math
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from nexus.domain.enums import (
    MarketRegime,
    MarketType,
    OrderSide,
    OrderStatus,
    OrderType,
    SignalAction,
    SignalDirection,
    TradingMode,
    TrendDirection,
    VolatilityLevel,
)


class TickerQuote(BaseModel):
    """Validated real spot market quote fetched from an exchange feed."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange_id: str
    bid: Decimal = Field(gt=Decimal("0"))
    ask: Decimal = Field(gt=Decimal("0"))
    last: Decimal = Field(gt=Decimal("0"))
    timestamp: datetime

    @property
    def mid(self) -> Decimal:
        """Compute midpoint between best bid and best ask."""
        return (self.bid + self.ask) / Decimal("2")


class OHLCVBar(BaseModel):
    """Single spot OHLCV candlestick bar stored in UTC."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    timestamp: datetime
    open: Decimal = Field(gt=Decimal("0"))
    high: Decimal = Field(gt=Decimal("0"))
    low: Decimal = Field(gt=Decimal("0"))
    close: Decimal = Field(gt=Decimal("0"))
    volume: Decimal = Field(ge=Decimal("0"))
    is_closed: bool = True


class CandleValidationReport(BaseModel):
    """Structured outcome of OHLCV candle validation."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    total_input: int
    valid_closed_count: int
    rejected_incomplete_count: int
    duplicate_timestamps: list[datetime] = Field(default_factory=list)
    missing_timestamps: list[datetime] = Field(default_factory=list)
    is_clean: bool


class HistoricalDownloadSummary(BaseModel):
    """Result of downloading and persisting historical OHLCV candles."""

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    symbol: str
    timeframe: str
    fetched_count: int
    stored_count: int
    validation: CandleValidationReport


class AssetHolding(BaseModel):
    """Spot asset balance held inside a virtual paper portfolio."""

    asset: str
    free_qty: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    locked_qty: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    avg_entry_price_usdt: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))


class PortfolioState(BaseModel):
    """Virtual portfolio state starting at INR 10,000.00."""

    id: UUID = Field(default_factory=uuid4)
    name: str = "nexus-default-paper"
    trading_mode: TradingMode = TradingMode.PAPER
    market_type: MarketType = MarketType.SPOT
    base_currency: str = "INR"
    initial_capital_inr: Decimal = Field(default=Decimal("10000.00"), gt=Decimal("0"))
    cash_balance_inr: Decimal = Field(default=Decimal("10000.00"), ge=Decimal("0"))
    holdings: dict[str, AssetHolding] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PaperOrderRequest(BaseModel):
    """Request to place a simulated spot paper order."""

    model_config = ConfigDict(frozen=True)

    portfolio_id: UUID
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: Decimal
    limit_price_usdt: Decimal | None = None
    stop_price_usdt: Decimal | None = None
    trailing_atr_multiplier: Decimal | None = None
    atr_at_entry: Decimal | None = None
    client_order_id: str | None = None
    signal_timestamp: datetime | None = None
    strategy_name: str = "manual"
    trading_mode: TradingMode = TradingMode.PAPER
    market_type: MarketType = MarketType.SPOT
    leverage: Decimal = Field(default=Decimal("1"))
    is_withdrawal: bool = False


class PaperFill(BaseModel):
    """Virtual execution fill settled against real market quote prices."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    symbol: str
    side: OrderSide
    executed_qty: Decimal = Field(gt=Decimal("0"))
    executed_price_usdt: Decimal = Field(gt=Decimal("0"))
    fee_usdt: Decimal = Field(ge=Decimal("0"))
    inr_per_usdt_rate: Decimal = Field(gt=Decimal("0"))
    total_inr: Decimal = Field(gt=Decimal("0"))
    slippage_bps: Decimal = Field(ge=Decimal("0"))
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PaperOrderResult(BaseModel):
    """Result of processing a paper order through risk validation and simulation."""

    model_config = ConfigDict(frozen=True)

    order_id: UUID = Field(default_factory=uuid4)
    portfolio_id: UUID
    symbol: str
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    requested_qty: Decimal
    fill: PaperFill | None = None
    rejection_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TradingSignal(BaseModel):
    """Quantitative signal emitted by a strategy evaluation."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    action: SignalAction
    confidence: float = Field(ge=0.0, le=1.0)
    strategy_name: str
    reason: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PositionContext(BaseModel):
    """Open spot LONG position state used for causal exit and trailing-stop evaluation."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    entry_timestamp: datetime
    entry_price: Decimal = Field(gt=Decimal("0"))
    quantity: Decimal = Field(gt=Decimal("0"))
    initial_stop_price: Decimal = Field(gt=Decimal("0"))
    trailing_stop_price: Decimal = Field(gt=Decimal("0"))
    highest_price_since_entry: Decimal = Field(gt=Decimal("0"))


class StrategySignal(BaseModel):
    """Structured Strategy V1 signal containing required execution & risk fields."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    direction: SignalDirection
    entry_price: Decimal = Field(gt=Decimal("0"))
    stop_price: Decimal = Field(ge=Decimal("0"))
    strategy_name: str
    reason: str
    indicators: dict[str, float] = Field(default_factory=dict)


class RiskState(BaseModel):
    """Persistent daily risk counters, peak equity, and emergency kill-switch state."""

    portfolio_id: UUID
    trading_date_utc: date
    daily_starting_equity_inr: Decimal = Field(gt=Decimal("0"))
    peak_equity_inr: Decimal = Field(gt=Decimal("0"))
    daily_entries_count: int = Field(default=0, ge=0)
    daily_realized_pnl_inr: Decimal = Field(default=Decimal("0"))
    total_realized_pnl_inr: Decimal = Field(default=Decimal("0"))
    kill_switch_active: bool = False
    kill_switch_reason: str | None = None
    kill_switch_triggered_at: datetime | None = None


class OpenPaperPosition(BaseModel):
    """Persistent virtual spot position with ATR stop-loss and trailing stop."""

    id: UUID = Field(default_factory=uuid4)
    portfolio_id: UUID
    symbol: str
    asset: str
    quantity: Decimal = Field(gt=Decimal("0"))
    avg_entry_price_usdt: Decimal = Field(gt=Decimal("0"))
    entry_cost_inr: Decimal = Field(gt=Decimal("0"))
    entry_fee_usdt: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    initial_stop_price_usdt: Decimal = Field(gt=Decimal("0"))
    trailing_stop_price_usdt: Decimal = Field(gt=Decimal("0"))
    highest_price_usdt: Decimal = Field(gt=Decimal("0"))
    trailing_atr_multiplier: Decimal = Field(default=Decimal("2.5"), gt=Decimal("0"))
    atr_at_entry: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    status: Literal["open", "closed"] = "open"
    opened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None


class TradeLedgerEntry(BaseModel):
    """Immutable realized P&L record for a closed virtual spot trade."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    portfolio_id: UUID
    position_id: UUID
    symbol: str
    entry_order_id: UUID
    exit_order_id: UUID
    quantity: Decimal = Field(gt=Decimal("0"))
    entry_price_usdt: Decimal = Field(gt=Decimal("0"))
    exit_price_usdt: Decimal = Field(gt=Decimal("0"))
    entry_cost_inr: Decimal = Field(gt=Decimal("0"))
    exit_proceeds_inr: Decimal = Field(gt=Decimal("0"))
    total_fees_inr: Decimal = Field(ge=Decimal("0"))
    realized_pnl_inr: Decimal
    realized_pnl_pct: Decimal
    exit_reason: str
    opened_at: datetime
    closed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PositionSizingResult(BaseModel):
    """Stop-distance position sizing outcome from IndependentRiskManager."""

    model_config = ConfigDict(frozen=True)

    approved: bool
    quantity: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    notional_inr: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    risk_inr: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    estimated_fee_inr: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    rejection_reason: str | None = None


class PortfolioPnLSummary(BaseModel):
    """Real-time realized/unrealized P&L and risk utilization snapshot."""

    model_config = ConfigDict(frozen=True)

    portfolio_id: UUID
    cash_balance_inr: Decimal
    holdings_value_inr: Decimal
    total_equity_inr: Decimal
    realized_pnl_inr: Decimal
    unrealized_pnl_inr: Decimal
    drawdown_pct: Decimal
    daily_loss_pct: Decimal
    open_positions_count: int
    daily_entries_count: int
    kill_switch_active: bool


class ReconciliationReport(BaseModel):
    """Startup reconciliation outcome between persisted ledger, positions, and cash."""

    model_config = ConfigDict(frozen=True)

    portfolio_id: UUID
    cash_balance_inr: Decimal
    reconciled_positions: int
    discrepancies: list[str] = Field(default_factory=list)
    repaired: bool = False
    daily_rolled_over: bool = False


def _ensure_utc_datetime(value: datetime) -> datetime:
    """Validate tz-aware datetime and normalize to UTC."""
    if value.tzinfo is None:
        raise ValueError("Timestamp must include timezone information (UTC).")
    return value.astimezone(UTC)


def _ensure_finite_float(value: float) -> float:
    """Reject NaN and Inf values in indicator inputs."""
    if not math.isfinite(value):
        raise ValueError("Numeric value must be finite (not NaN or Inf).")
    return value


class ValidatedIndicatorSnapshot(BaseModel):
    """Validated market indicator values extracted strictly from closed candles."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    close_usdt: Decimal = Field(gt=Decimal("0"))
    ema_fast: Decimal = Field(gt=Decimal("0"))
    ema_slow: Decimal = Field(gt=Decimal("0"))
    ema_fast_period: int = Field(default=20, ge=1)
    ema_slow_period: int = Field(default=50, ge=2)
    rsi: float = Field(ge=0.0, le=100.0)
    rsi_period: int = Field(default=14, ge=2)
    atr: Decimal = Field(ge=Decimal("0"))
    atr_period: int = Field(default=14, ge=1)
    atr_pct: float = Field(ge=0.0)
    volume: Decimal = Field(ge=Decimal("0"))
    volume_sma: Decimal = Field(ge=Decimal("0"))
    volume_sma_period: int = Field(default=20, ge=1)
    volume_ratio: float = Field(ge=0.0)

    @field_validator("rsi", "atr_pct", "volume_ratio")
    @classmethod
    def check_finite(cls, value: float) -> float:
        return _ensure_finite_float(value)


class HistoricalFeatureSummary(BaseModel):
    """Causal historical context computed over validated closed OHLCV candles."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lookback_bars: int = Field(ge=1)
    return_1_bar_pct: float
    return_5_bar_pct: float
    return_20_bar_pct: float
    realized_volatility_pct: float = Field(ge=0.0)
    atr_percentile: float = Field(ge=0.0, le=100.0)
    volume_zscore: float
    range_high_usdt: Decimal = Field(gt=Decimal("0"))
    range_low_usdt: Decimal = Field(gt=Decimal("0"))
    gap_count: int = Field(default=0, ge=0)
    anomaly_flags: list[str] = Field(default_factory=list)

    @field_validator(
        "return_1_bar_pct",
        "return_5_bar_pct",
        "return_20_bar_pct",
        "realized_volatility_pct",
        "atr_percentile",
        "volume_zscore",
    )
    @classmethod
    def check_finite(cls, value: float) -> float:
        return _ensure_finite_float(value)

    @model_validator(mode="after")
    def check_range_order(self) -> "HistoricalFeatureSummary":
        if self.range_high_usdt < self.range_low_usdt:
            raise ValueError("range_high_usdt must be >= range_low_usdt")
        return self


class StrategySignalSummary(BaseModel):
    """Read-only summary of a deterministic signal emitted by NEXUS Strategy Engine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    timestamp: datetime
    direction: SignalDirection
    entry_price: Decimal = Field(gt=Decimal("0"))
    stop_price: Decimal = Field(ge=Decimal("0"))
    strategy_name: str
    reason: str

    @field_validator("timestamp")
    @classmethod
    def check_utc(cls, value: datetime) -> datetime:
        return _ensure_utc_datetime(value)


class StrategyPerformanceSnapshot(BaseModel):
    """Historical realized metrics for comparing deterministic strategies."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_name: str = Field(min_length=1)
    trades_count: int = Field(ge=0)
    win_rate_pct: float = Field(ge=0.0, le=100.0)
    net_pnl_inr: Decimal
    max_drawdown_pct: float = Field(ge=0.0)
    profit_factor: float | None = Field(default=None, ge=0.0)
    avg_return_pct: float

    @field_validator("win_rate_pct", "max_drawdown_pct", "avg_return_pct")
    @classmethod
    def check_finite(cls, value: float) -> float:
        return _ensure_finite_float(value)

    @field_validator("profit_factor")
    @classmethod
    def check_optional_finite(cls, value: float | None) -> float | None:
        return _ensure_finite_float(value) if value is not None else None


class MarketAnalysisInput(BaseModel):
    """Strict input contract for advisory AI market analysis (validated closed data only)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=3)
    timeframe: str = Field(min_length=2)
    as_of_timestamp: datetime
    indicators: ValidatedIndicatorSnapshot
    historical_features: HistoricalFeatureSummary
    strategy_signals: list[StrategySignalSummary] = Field(default_factory=list)
    strategy_comparisons: list[StrategyPerformanceSnapshot] = Field(default_factory=list)

    @field_validator("symbol")
    @classmethod
    def validate_spot_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if "/" not in symbol or ":" in symbol or "PERP" in symbol:
            raise ValueError(f"Only spot pairs are supported for analysis, got '{value}'.")
        return symbol

    @field_validator("as_of_timestamp")
    @classmethod
    def check_utc(cls, value: datetime) -> datetime:
        return _ensure_utc_datetime(value)


class SignalExplanation(BaseModel):
    """Human-readable explanation of a deterministic strategy signal (advisory only)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_name: str = Field(min_length=1)
    symbol: str = Field(min_length=3)
    direction: SignalDirection
    signal_timestamp: datetime
    rationale: str = Field(min_length=5)
    regime_alignment: str = Field(min_length=3)
    advisory_only: Literal[True] = True

    @field_validator("signal_timestamp")
    @classmethod
    def check_utc(cls, value: datetime) -> datetime:
        return _ensure_utc_datetime(value)


class StrategyAssessment(BaseModel):
    """Advisory assessment of deterministic strategy signals and comparative performance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_explanations: list[SignalExplanation] = Field(default_factory=list)
    performance_comparison: str = Field(min_length=5)
    unusual_conditions_detected: bool = False
    unusual_conditions: list[str] = Field(default_factory=list)
    advisory_only: Literal[True] = True
    executable_signal: Literal[False] = False


class MarketAnalysisOutput(BaseModel):
    """Strict 7-field JSON output produced by the NEXUS AI market analysis module."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    market_regime: MarketRegime
    trend_direction: TrendDirection
    volatility_level: VolatilityLevel
    risk_observations: list[str] = Field(min_length=1)
    strategy_assessment: StrategyAssessment
    explanation: str = Field(min_length=10)
    timestamp: datetime

    @field_validator("risk_observations")
    @classmethod
    def validate_non_empty_observations(cls, items: list[str]) -> list[str]:
        cleaned = [item.strip() for item in items if item.strip()]
        if not cleaned:
            raise ValueError("risk_observations must contain at least one non-empty observation.")
        return cleaned

    @field_validator("timestamp")
    @classmethod
    def check_utc(cls, value: datetime) -> datetime:
        return _ensure_utc_datetime(value)

