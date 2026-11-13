"""Configurable parameters for NEXUS Strategy Engine V1."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrategyV1Config(BaseModel):
    """Validated parameters for EMA Trend + RSI + ATR + Volume confirmation."""

    model_config = ConfigDict(frozen=True)

    strategy_name: str = "nexus_ema_rsi_atr_vol_v1"
    ema_fast_period: int = Field(default=20, ge=2, le=200)
    ema_slow_period: int = Field(default=50, ge=5, le=500)
    rsi_period: int = Field(default=14, ge=2, le=100)
    rsi_entry_min: float = Field(default=50.0, ge=1.0, le=99.0)
    rsi_entry_max: float = Field(default=70.0, ge=1.0, le=99.0)
    atr_period: int = Field(default=14, ge=2, le=100)
    volume_sma_period: int = Field(default=20, ge=2, le=200)
    stop_atr_multiplier: Decimal = Field(default=Decimal("2.0"), gt=Decimal("0"))
    trailing_atr_multiplier: Decimal = Field(default=Decimal("2.5"), gt=Decimal("0"))
    confirm_reversal_with_close: bool = False

    @model_validator(mode="after")
    def validate_relationships(self) -> "StrategyV1Config":
        """Ensure period and threshold ordering is mathematically consistent."""
        if self.ema_fast_period >= self.ema_slow_period:
            raise ValueError("ema_fast_period must be strictly less than ema_slow_period.")
        if self.rsi_entry_min >= self.rsi_entry_max:
            raise ValueError("rsi_entry_min must be strictly less than rsi_entry_max.")
        return self

    @property
    def min_candles_required(self) -> int:
        """Minimum closed bars needed so all indicators and t-1 crossover values are valid."""
        return (
            max(
                self.ema_slow_period,
                self.rsi_period + 1,
                self.atr_period + 1,
                self.volume_sma_period,
            )
            + 1
        )

