"""Initial PostgreSQL schema for NEXUS AI TRADER paper trading.

Revision ID: 20261112_0001
Revises: None
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261112_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("trading_mode", sa.String(length=16), nullable=False),
        sa.Column("market_type", sa.String(length=16), nullable=False),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
        sa.Column("initial_capital_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("cash_balance_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("trading_mode = 'paper'", name="paper_mode_only"),
        sa.CheckConstraint("market_type = 'spot'", name="spot_market_only"),
        sa.CheckConstraint("base_currency = 'INR'", name="inr_base_currency"),
        sa.CheckConstraint("initial_capital_inr > 0", name="positive_initial_capital"),
        sa.CheckConstraint("cash_balance_inr >= 0", name="non_negative_cash"),
        sa.PrimaryKeyConstraint("id", name="pk_portfolios"),
        sa.UniqueConstraint("name", name="uq_portfolios_name"),
    )

    op.create_table(
        "portfolio_balances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("asset", sa.String(length=16), nullable=False),
        sa.Column("free_qty", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("locked_qty", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("avg_entry_price_usdt", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("free_qty >= 0", name="non_negative_free_qty"),
        sa.CheckConstraint("locked_qty >= 0", name="non_negative_locked_qty"),
        sa.CheckConstraint(
            "avg_entry_price_usdt >= 0",
            name="non_negative_entry_price",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name="fk_portfolio_balances_portfolio_id_portfolios",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_portfolio_balances"),
        sa.UniqueConstraint("portfolio_id", "asset", name="uq_portfolio_balances_portfolio_asset"),
    )

    op.create_table(
        "paper_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("trading_mode", sa.String(length=16), nullable=False),
        sa.Column("market_type", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("limit_price_usdt", sa.Numeric(precision=24, scale=10), nullable=True),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("trading_mode = 'paper'", name="order_paper_only"),
        sa.CheckConstraint("market_type = 'spot'", name="order_spot_only"),
        sa.CheckConstraint("side IN ('buy', 'sell')", name="valid_order_side"),
        sa.CheckConstraint(
            "order_type IN ('market', 'limit')", name="valid_order_type"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'filled', 'rejected', 'cancelled')",
            name="valid_order_status",
        ),
        sa.CheckConstraint("quantity > 0", name="positive_order_qty"),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name="fk_paper_orders_portfolio_id_portfolios",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_paper_orders"),
    )
    op.create_index(
        "ix_paper_orders_portfolio_symbol",
        "paper_orders",
        ["portfolio_id", "symbol"],
        unique=False,
    )

    op.create_table(
        "paper_fills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("executed_qty", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("executed_price_usdt", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("fee_usdt", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("inr_per_usdt_rate", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("total_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("slippage_bps", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("executed_qty > 0", name="positive_fill_qty"),
        sa.CheckConstraint("executed_price_usdt > 0", name="positive_fill_price"),
        sa.CheckConstraint("fee_usdt >= 0", name="non_negative_fee"),
        sa.CheckConstraint("inr_per_usdt_rate > 0", name="positive_fx_rate"),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["paper_orders.id"],
            name="fk_paper_fills_order_id_paper_orders",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_paper_fills"),
    )

    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exchange_id", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("bar_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open_price", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("high_price", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("low_price", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("close_price", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("volume", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_market_snapshots"),
        sa.UniqueConstraint(
            "exchange_id",
            "symbol",
            "timeframe",
            "bar_timestamp",
            name="uq_ohlcv_bar",
        ),
    )
    op.create_index(
        "ix_market_snapshots_symbol_ts",
        "market_snapshots",
        ["symbol", "bar_timestamp"],
        unique=False,
    )

    op.create_table(
        "strategy_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_strategy_runs"),
    )


def downgrade() -> None:
    op.drop_table("strategy_runs")
    op.drop_index("ix_market_snapshots_symbol_ts", table_name="market_snapshots")
    op.drop_table("market_snapshots")
    op.drop_table("paper_fills")
    op.drop_index("ix_paper_orders_portfolio_symbol", table_name="paper_orders")
    op.drop_table("paper_orders")
    op.drop_table("portfolio_balances")
    op.drop_table("portfolios")

