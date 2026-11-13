"""Add risk_states, paper_positions, trade_ledger, and client_order_id idempotency.

Revision ID: 20261112_0002
Revises: 20261112_0001
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261112_0002"
down_revision: str | Sequence[str] | None = "20261112_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_orders", sa.Column("client_order_id", sa.String(length=128), nullable=True)
    )
    op.create_unique_constraint(
        "uq_portfolio_client_order",
        "paper_orders",
        ["portfolio_id", "client_order_id"],
    )

    op.create_table(
        "risk_states",
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("trading_date_utc", sa.Date(), nullable=False),
        sa.Column("daily_starting_equity_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("peak_equity_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("daily_entries_count", sa.Integer(), nullable=False),
        sa.Column("daily_realized_pnl_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("total_realized_pnl_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("kill_switch_active", sa.Boolean(), nullable=False),
        sa.Column("kill_switch_reason", sa.Text(), nullable=True),
        sa.Column("kill_switch_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "daily_starting_equity_inr > 0", name="positive_daily_start_equity"
        ),
        sa.CheckConstraint("peak_equity_inr > 0", name="positive_peak_equity"),
        sa.CheckConstraint("daily_entries_count >= 0", name="non_negative_daily_entries"),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name="fk_risk_states_portfolio_id_portfolios",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("portfolio_id", name="pk_risk_states"),
    )

    op.create_table(
        "paper_positions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("asset", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("avg_entry_price_usdt", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("entry_cost_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("entry_fee_usdt", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("initial_stop_price_usdt", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("trailing_stop_price_usdt", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("highest_price_usdt", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("trailing_atr_multiplier", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("atr_at_entry", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="positive_position_qty"),
        sa.CheckConstraint("avg_entry_price_usdt > 0", name="positive_entry_price"),
        sa.CheckConstraint("entry_cost_inr > 0", name="positive_entry_cost"),
        sa.CheckConstraint("initial_stop_price_usdt > 0", name="positive_initial_stop"),
        sa.CheckConstraint("trailing_stop_price_usdt > 0", name="positive_trailing_stop"),
        sa.CheckConstraint("status IN ('open', 'closed')", name="valid_position_status"),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name="fk_paper_positions_portfolio_id_portfolios",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_paper_positions"),
    )
    op.create_index(
        "ix_paper_positions_portfolio_status",
        "paper_positions",
        ["portfolio_id", "status"],
        unique=False,
    )

    op.create_table(
        "trade_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("position_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("entry_order_id", sa.Uuid(), nullable=False),
        sa.Column("exit_order_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("entry_price_usdt", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("exit_price_usdt", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("entry_cost_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("exit_proceeds_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("total_fees_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("realized_pnl_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("realized_pnl_pct", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("exit_reason", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="positive_ledger_qty"),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name="fk_trade_ledger_portfolio_id_portfolios",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["paper_positions.id"],
            name="fk_trade_ledger_position_id_paper_positions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trade_ledger"),
    )
    op.create_index(
        "ix_trade_ledger_portfolio_closed",
        "trade_ledger",
        ["portfolio_id", "closed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trade_ledger_portfolio_closed", table_name="trade_ledger")
    op.drop_table("trade_ledger")
    op.drop_index("ix_paper_positions_portfolio_status", table_name="paper_positions")
    op.drop_table("paper_positions")
    op.drop_table("risk_states")
    op.drop_constraint("uq_portfolio_client_order", "paper_orders", type_="unique")
    op.drop_column("paper_orders", "client_order_id")

