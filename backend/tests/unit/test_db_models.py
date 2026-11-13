"""Unit tests for SQLAlchemy ORM schema and database constraints."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from nexus.core.config import Settings
from nexus.infrastructure.db.base import Base
from nexus.infrastructure.db.models import PortfolioORM
from nexus.infrastructure.db.session import DatabaseManager


@pytest.mark.asyncio
async def test_orm_schema_creation_and_check_constraints(test_settings: Settings) -> None:
    db = DatabaseManager(test_settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with db.session_factory() as session:
        portfolio = PortfolioORM(name="default-paper")
        session.add(portfolio)
        await session.commit()

        loaded = (
            await session.execute(select(PortfolioORM).where(PortfolioORM.name == "default-paper"))
        ).scalar_one()
        assert loaded.trading_mode == "paper"
        assert loaded.market_type == "spot"
        assert loaded.base_currency == "INR"
        assert loaded.initial_capital_inr == Decimal("10000.0000")

    async with db.session_factory() as session:
        invalid_live = PortfolioORM(name="forbidden-live", trading_mode="live")
        session.add(invalid_live)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    await db.dispose()

