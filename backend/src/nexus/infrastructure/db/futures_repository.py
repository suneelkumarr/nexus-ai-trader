"""Database repository for persistent futures paper positions, orders, and ledger."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.core.logging import get_logger
from nexus.infrastructure.db.models import (
    PaperFuturesOrderORM,
    PaperFuturesPositionORM,
    PortfolioORM,
)

logger = get_logger(__name__)


class SqlAlchemyFuturesRepository:
    """Async repository for simulated USDT-M perpetuals orders and positions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_or_create_portfolio(self) -> PortfolioORM:
        """Fetch the default virtual portfolio."""
        async with self._session_factory() as session:
            stmt = select(PortfolioORM).order_by(PortfolioORM.created_at.asc()).limit(1)
            row = (await session.execute(stmt)).scalars().first()
            if row is not None:
                return row

            portfolio = PortfolioORM(name="nexus-default-paper")
            session.add(portfolio)
            await session.commit()
            await session.refresh(portfolio)
            return portfolio

    async def get_open_positions(self, portfolio_id: UUID) -> list[PaperFuturesPositionORM]:
        """Fetch all currently open simulated futures positions."""
        async with self._session_factory() as session:
            stmt = (
                select(PaperFuturesPositionORM)
                .where(
                    PaperFuturesPositionORM.portfolio_id == portfolio_id,
                    PaperFuturesPositionORM.status == "open",
                )
                .order_by(desc(PaperFuturesPositionORM.opened_at))
            )
            return list((await session.execute(stmt)).scalars().all())

    async def get_all_positions(
        self, portfolio_id: UUID, limit: int = 50
    ) -> list[PaperFuturesPositionORM]:
        """Fetch recent positions (open and closed)."""
        async with self._session_factory() as session:
            stmt = (
                select(PaperFuturesPositionORM)
                .where(PaperFuturesPositionORM.portfolio_id == portfolio_id)
                .order_by(desc(PaperFuturesPositionORM.opened_at))
                .limit(limit)
            )
            return list((await session.execute(stmt)).scalars().all())

    async def get_position_by_id(
        self, position_id: UUID
    ) -> PaperFuturesPositionORM | None:
        """Fetch a specific position by UUID."""
        async with self._session_factory() as session:
            return await session.get(PaperFuturesPositionORM, position_id)

    async def record_order(
        self, order: PaperFuturesOrderORM
    ) -> PaperFuturesOrderORM:
        """Persist a simulated futures order."""
        async with self._session_factory() as session:
            session.add(order)
            await session.commit()
            await session.refresh(order)
            return order

    async def open_position(
        self,
        *,
        portfolio_id: UUID,
        order: PaperFuturesOrderORM,
        position: PaperFuturesPositionORM,
        initial_margin_inr: Decimal,
        fee_inr: Decimal,
    ) -> PaperFuturesPositionORM:
        """Atomically lock isolated margin from portfolio cash balance and open position."""
        async with self._session_factory() as session:
            port = await session.get(PortfolioORM, portfolio_id)
            if port is None:
                raise ValueError(f"Portfolio {portfolio_id} not found")

            total_deduction = initial_margin_inr + fee_inr
            if port.cash_balance_inr < total_deduction:
                raise ValueError(
                    f"Insufficient cash balance: available ₹{port.cash_balance_inr:,.2f}, "
                    f"required ₹{total_deduction:,.2f}"
                )

            port.cash_balance_inr = port.cash_balance_inr - total_deduction
            session.add(order)
            session.add(position)
            await session.commit()
            await session.refresh(position)
            return position

    async def close_position(
        self,
        *,
        portfolio_id: UUID,
        position_id: UUID,
        exit_price: Decimal,
        realized_pnl_inr: Decimal,
        exit_fee_inr: Decimal,
        close_reason: str,
        status: str = "closed",
    ) -> PaperFuturesPositionORM:
        """Atomically return margin + realized PnL - exit fee to portfolio cash balance."""
        async with self._session_factory() as session:
            pos = await session.get(PaperFuturesPositionORM, position_id)
            if pos is None:
                raise ValueError(f"Position {position_id} not found")
            if pos.status != "open":
                raise ValueError(f"Position {position_id} is already {pos.status}")

            port = await session.get(PortfolioORM, portfolio_id)
            if port is None:
                raise ValueError(f"Portfolio {portfolio_id} not found")

            now = datetime.now(UTC)
            pos.exit_price_usdt = exit_price
            pos.exit_fee_inr = exit_fee_inr
            pos.realized_pnl_inr = realized_pnl_inr
            pos.close_reason = close_reason
            pos.status = status
            pos.closed_at = now

            if status == "liquidated":
                # Liquidation: user loses isolated margin entirely, 0 returned
                amount_to_return = Decimal("0")
            else:
                # Normal close: return margin + pnl - exit_fee (bounded at 0)
                amount_to_return = pos.initial_margin_inr + realized_pnl_inr - exit_fee_inr
                if amount_to_return < Decimal("0"):
                    amount_to_return = Decimal("0")

            port.cash_balance_inr = port.cash_balance_inr + amount_to_return
            await session.commit()
            await session.refresh(pos)
            return pos

    async def get_summary_metrics(self, portfolio_id: UUID) -> dict[str, Any]:
        """Compute aggregated metrics across open and closed futures positions."""
        async with self._session_factory() as session:
            port = await session.get(PortfolioORM, portfolio_id)
            cash_bal = port.cash_balance_inr if port else Decimal("10000.00")

            # Open positions margin sum
            open_stmt = select(
                func.count(PaperFuturesPositionORM.id),
                func.coalesce(func.sum(PaperFuturesPositionORM.initial_margin_inr), Decimal("0")),
            ).where(
                PaperFuturesPositionORM.portfolio_id == portfolio_id,
                PaperFuturesPositionORM.status == "open",
            )
            open_res = (await session.execute(open_stmt)).one()
            open_count: int = open_res[0]
            total_margin: Decimal = open_res[1]

            # Closed positions metrics
            closed_stmt = select(
                func.count(PaperFuturesPositionORM.id),
                func.coalesce(func.sum(PaperFuturesPositionORM.realized_pnl_inr), Decimal("0")),
            ).where(
                PaperFuturesPositionORM.portfolio_id == portfolio_id,
                PaperFuturesPositionORM.status == "closed",
            )
            closed_res = (await session.execute(closed_stmt)).one()
            closed_count: int = closed_res[0]
            realized_pnl: Decimal = closed_res[1]

            # Liquidated count
            liq_stmt = select(func.count(PaperFuturesPositionORM.id)).where(
                PaperFuturesPositionORM.portfolio_id == portfolio_id,
                PaperFuturesPositionORM.status == "liquidated",
            )
            liq_count: int = (await session.execute(liq_stmt)).scalar() or 0

            # Winning trades count
            win_stmt = select(func.count(PaperFuturesPositionORM.id)).where(
                PaperFuturesPositionORM.portfolio_id == portfolio_id,
                PaperFuturesPositionORM.status == "closed",
                PaperFuturesPositionORM.realized_pnl_inr > Decimal("0"),
            )
            win_count: int = (await session.execute(win_stmt)).scalar() or 0

            total_closed = closed_count + liq_count
            win_rate = (
                (Decimal(win_count) / Decimal(total_closed) * Decimal("100")).quantize(
                    Decimal("0.01")
                )
                if total_closed > 0
                else Decimal("0")
            )

            return {
                "total_futures_margin_inr": total_margin,
                "available_cash_inr": cash_bal,
                "realized_pnl_inr": realized_pnl,
                "open_positions_count": open_count,
                "closed_positions_count": closed_count,
                "liquidated_count": liq_count,
                "total_trades_count": total_closed + open_count,
                "win_rate_pct": win_rate,
            }
