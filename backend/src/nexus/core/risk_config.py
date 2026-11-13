"""Configurable risk management parameters for NEXUS paper trading."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RiskConfig(BaseModel):
    """Validated portfolio risk limits (spot-only, zero leverage)."""

    model_config = ConfigDict(frozen=True)

    risk_per_trade_pct: Decimal = Field(default=Decimal("0.5"), gt=Decimal("0"), le=Decimal("10"))
    max_position_notional_pct: Decimal = Field(
        default=Decimal("20.0"), gt=Decimal("0"), le=Decimal("100")
    )
    max_concurrent_positions: int = Field(default=2, ge=1, le=20)
    daily_loss_limit_pct: Decimal = Field(
        default=Decimal("2.0"), gt=Decimal("0"), le=Decimal("50")
    )
    max_drawdown_pct: Decimal = Field(default=Decimal("8.0"), gt=Decimal("0"), le=Decimal("50"))
    max_daily_entries: int = Field(default=5, ge=1, le=100)
    min_order_notional_inr: Decimal = Field(default=Decimal("50.00"), ge=Decimal("0"))

