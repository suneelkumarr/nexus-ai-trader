"""SQLAlchemy 2.0 ORM models for virtual spot paper trading."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.infrastructure.db.base import Base, TimestampMixin


class PortfolioORM(TimestampMixin, Base):
    """Virtual paper-trading portfolio initialized with INR 10,000.00."""

    __tablename__ = "portfolios"
    __table_args__ = (
        CheckConstraint("trading_mode = 'paper'", name="paper_mode_only"),
        CheckConstraint("market_type = 'spot'", name="spot_market_only"),
        CheckConstraint("base_currency = 'INR'", name="inr_base_currency"),
        CheckConstraint("initial_capital_inr > 0", name="positive_initial_capital"),
        CheckConstraint("cash_balance_inr >= 0", name="non_negative_cash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    trading_mode: Mapped[str] = mapped_column(String(16), default="paper", nullable=False)
    market_type: Mapped[str] = mapped_column(String(16), default="spot", nullable=False)
    base_currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    initial_capital_inr: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("10000.0000"), nullable=False
    )
    cash_balance_inr: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("10000.0000"), nullable=False
    )

    balances: Mapped[list["PortfolioBalanceORM"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    orders: Mapped[list["PaperOrderORM"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class PortfolioBalanceORM(TimestampMixin, Base):
    """Per-asset spot balance inside a virtual portfolio."""

    __tablename__ = "portfolio_balances"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "asset", name="portfolio_asset"),
        CheckConstraint("free_qty >= 0", name="non_negative_free_qty"),
        CheckConstraint("locked_qty >= 0", name="non_negative_locked_qty"),
        CheckConstraint("avg_entry_price_usdt >= 0", name="non_negative_entry_price"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    asset: Mapped[str] = mapped_column(String(16), nullable=False)
    free_qty: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), default=Decimal("0"), nullable=False
    )
    locked_qty: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), default=Decimal("0"), nullable=False
    )
    avg_entry_price_usdt: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), default=Decimal("0"), nullable=False
    )

    portfolio: Mapped["PortfolioORM"] = relationship(back_populates="balances")


class PaperOrderORM(TimestampMixin, Base):
    """Virtual spot order record."""

    __tablename__ = "paper_orders"
    __table_args__ = (
        CheckConstraint("trading_mode = 'paper'", name="order_paper_only"),
        CheckConstraint("market_type = 'spot'", name="order_spot_only"),
        CheckConstraint("side IN ('buy', 'sell')", name="valid_order_side"),
        CheckConstraint("order_type IN ('market', 'limit')", name="valid_order_type"),
        CheckConstraint(
            "status IN ('pending', 'filled', 'rejected', 'cancelled')",
            name="valid_order_status",
        ),
        CheckConstraint("quantity > 0", name="positive_order_qty"),
        UniqueConstraint("portfolio_id", "client_order_id", name="uq_portfolio_client_order"),
        Index("ix_paper_orders_portfolio_symbol", "portfolio_id", "symbol"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    client_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    trading_mode: Mapped[str] = mapped_column(String(16), default="paper", nullable=False)
    market_type: Mapped[str] = mapped_column(String(16), default="spot", nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    limit_price_usdt: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    strategy_name: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    portfolio: Mapped["PortfolioORM"] = relationship(back_populates="orders")
    fills: Mapped[list["PaperFillORM"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class PaperFillORM(Base):
    """Executed virtual paper fill settled against real market quote prices."""

    __tablename__ = "paper_fills"
    __table_args__ = (
        CheckConstraint("executed_qty > 0", name="positive_fill_qty"),
        CheckConstraint("executed_price_usdt > 0", name="positive_fill_price"),
        CheckConstraint("fee_usdt >= 0", name="non_negative_fee"),
        CheckConstraint("inr_per_usdt_rate > 0", name="positive_fx_rate"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("paper_orders.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    executed_qty: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    executed_price_usdt: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    fee_usdt: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    inr_per_usdt_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    total_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    slippage_bps: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    order: Mapped["PaperOrderORM"] = relationship(back_populates="fills")


class MarketSnapshotORM(Base):
    """Persisted real OHLCV/ticker observations from CCXT."""

    __tablename__ = "market_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "exchange_id", "symbol", "timeframe", "bar_timestamp", name="uq_ohlcv_bar"
        ),
        Index("ix_market_snapshots_symbol_ts", "symbol", "bar_timestamp"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    exchange_id: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    bar_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open_price: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    high_price: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    low_price: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)


class StrategyRunORM(Base):
    """Audit record for automated strategy signal evaluations."""

    __tablename__ = "strategy_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RiskStateORM(TimestampMixin, Base):
    """Persistent daily risk metrics, peak equity, and emergency kill-switch state."""

    __tablename__ = "risk_states"
    __table_args__ = (
        CheckConstraint("daily_starting_equity_inr > 0", name="positive_daily_start_equity"),
        CheckConstraint("peak_equity_inr > 0", name="positive_peak_equity"),
        CheckConstraint("daily_entries_count >= 0", name="non_negative_daily_entries"),
    )

    portfolio_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        primary_key=True,
    )
    trading_date_utc: Mapped[date] = mapped_column(Date, nullable=False)
    daily_starting_equity_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    peak_equity_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    daily_entries_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    daily_realized_pnl_inr: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0"), nullable=False
    )
    total_realized_pnl_inr: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0"), nullable=False
    )
    kill_switch_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    kill_switch_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    kill_switch_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PaperPositionORM(TimestampMixin, Base):
    """Persistent open/closed virtual spot positions with stop-loss and trailing stop."""

    __tablename__ = "paper_positions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_position_qty"),
        CheckConstraint("avg_entry_price_usdt > 0", name="positive_entry_price"),
        CheckConstraint("entry_cost_inr > 0", name="positive_entry_cost"),
        CheckConstraint("initial_stop_price_usdt > 0", name="positive_initial_stop"),
        CheckConstraint("trailing_stop_price_usdt > 0", name="positive_trailing_stop"),
        CheckConstraint("status IN ('open', 'closed')", name="valid_position_status"),
        Index("ix_paper_positions_portfolio_status", "portfolio_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    asset: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    avg_entry_price_usdt: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    entry_cost_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    entry_fee_usdt: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), default=Decimal("0"), nullable=False
    )
    initial_stop_price_usdt: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    trailing_stop_price_usdt: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    highest_price_usdt: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    trailing_atr_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("2.5"), nullable=False
    )
    atr_at_entry: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), default=Decimal("0"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TradeLedgerORM(Base):
    """Persistent closed round-trip realized P&L ledger."""

    __tablename__ = "trade_ledger"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_ledger_qty"),
        Index("ix_trade_ledger_portfolio_closed", "portfolio_id", "closed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    position_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("paper_positions.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    entry_order_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    exit_order_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    entry_price_usdt: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    exit_price_usdt: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    entry_cost_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    exit_proceeds_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_fees_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    realized_pnl_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    realized_pnl_pct: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    exit_reason: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

