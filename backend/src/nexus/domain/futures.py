"""Immutable Pydantic domain models for Crypto Futures Paper Trading Simulation.

Provides isolated margin perpetual futures modeling with 1x to 5x leverage,
liquidation threshold calculations, funding rate tracking, and P&L attribution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class FuturesSide(StrEnum):
    """Position direction in USDT-M perpetuals."""

    LONG = "LONG"
    SHORT = "SHORT"


class FuturesOrderAction(StrEnum):
    """Execution action for simulated futures orders."""

    OPEN_LONG = "OPEN_LONG"
    CLOSE_LONG = "CLOSE_LONG"
    OPEN_SHORT = "OPEN_SHORT"
    CLOSE_SHORT = "CLOSE_SHORT"


class FuturesOrderStatus(StrEnum):
    """Lifecycle states of a simulated futures order."""

    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class FuturesPositionStatus(StrEnum):
    """State of a simulated perpetual futures position."""

    OPEN = "open"
    CLOSED = "closed"
    LIQUIDATED = "liquidated"


class FuturesMarginMode(StrEnum):
    """Margin allocation mode — strictly ISOLATED for risk containment."""

    ISOLATED = "ISOLATED"


class FuturesPosition(BaseModel):
    """Simulated USDT-M perpetual futures position with isolated margin & liquidation math."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    portfolio_id: UUID
    symbol: str
    side: FuturesSide
    leverage: int = Field(default=2, ge=1, le=5)
    margin_mode: FuturesMarginMode = FuturesMarginMode.ISOLATED
    quantity: Decimal = Field(gt=Decimal("0"))
    entry_price: Decimal = Field(gt=Decimal("0"))
    mark_price: Decimal = Field(gt=Decimal("0"))
    liquidation_price: Decimal = Field(gt=Decimal("0"))
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    initial_margin_inr: Decimal = Field(gt=Decimal("0"))
    entry_fee_inr: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    unrealized_pnl_usd: Decimal = Decimal("0")
    unrealized_pnl_inr: Decimal = Decimal("0")
    roe_pct: Decimal = Decimal("0")
    status: FuturesPositionStatus = FuturesPositionStatus.OPEN
    close_price: Decimal | None = None
    close_reason: str | None = None
    realized_pnl_inr: Decimal = Decimal("0")
    opened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None


class FuturesOrderRequest(BaseModel):
    """User or autonomous strategy order request to open/close a futures position."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    action: FuturesOrderAction
    quantity: Decimal = Field(gt=Decimal("0"))
    leverage: int = Field(default=2, ge=1, le=5)
    limit_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    client_order_id: str | None = None


class FuturesOrderResult(BaseModel):
    """Outcome of submitting a simulated futures order."""

    model_config = ConfigDict(frozen=True)

    order_id: UUID = Field(default_factory=uuid4)
    portfolio_id: UUID
    symbol: str
    action: FuturesOrderAction
    status: FuturesOrderStatus
    quantity: Decimal
    executed_price: Decimal | None = None
    fee_inr: Decimal = Decimal("0")
    position_id: UUID | None = None
    rejection_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FundingRateInfo(BaseModel):
    """Real-time Binance USDT-M perpetual funding rate telemetry."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    funding_rate: Decimal
    funding_rate_pct: Decimal
    mark_price: Decimal
    index_price: Decimal
    funding_time: datetime
    next_funding_time: datetime


class FuturesAccountSummary(BaseModel):
    """Consolidated futures portfolio performance and margin metrics."""

    model_config = ConfigDict(frozen=True)

    total_margin_inr: Decimal
    available_cash_inr: Decimal
    unrealized_pnl_inr: Decimal
    realized_pnl_inr: Decimal
    open_positions_count: int
    closed_positions_count: int
    liquidated_count: int
    total_trades_count: int
    win_rate_pct: Decimal
    auto_trade_enabled: bool = False

