"""PostgreSQL / SQLAlchemy repository for historical UTC OHLCV candles."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.domain.models import OHLCVBar
from nexus.infrastructure.db.models import MarketSnapshotORM


def _ensure_utc(dt: datetime) -> datetime:
    """Normalize a datetime loaded from DB into timezone-aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class SqlAlchemyCandleRepository:
    """Persists and queries historical OHLCV bars with idempotent conflict upserts."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def upsert_candles(self, exchange_id: str, bars: Sequence[OHLCVBar]) -> int:
        """Upsert OHLCV bars keyed by (exchange_id, symbol, timeframe, bar_timestamp)."""
        if not bars:
            return 0

        normalized_exchange = exchange_id.lower().strip()
        records = [
            {
                "exchange_id": normalized_exchange,
                "symbol": bar.symbol.upper().strip(),
                "timeframe": bar.timeframe.lower().strip(),
                "bar_timestamp": _ensure_utc(bar.timestamp),
                "open_price": bar.open,
                "high_price": bar.high,
                "low_price": bar.low,
                "close_price": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]

        async with self._session_factory() as session:
            dialect_name = session.bind.dialect.name if session.bind is not None else ""
            if dialect_name == "postgresql":
                stmt_pg = pg_insert(MarketSnapshotORM).values(records)
                await session.execute(
                    stmt_pg.on_conflict_do_update(
                        index_elements=["exchange_id", "symbol", "timeframe", "bar_timestamp"],
                        set_={
                            "open_price": stmt_pg.excluded.open_price,
                            "high_price": stmt_pg.excluded.high_price,
                            "low_price": stmt_pg.excluded.low_price,
                            "close_price": stmt_pg.excluded.close_price,
                            "volume": stmt_pg.excluded.volume,
                        },
                    )
                )
            else:
                stmt_sqlite = sqlite_insert(MarketSnapshotORM).values(records)
                await session.execute(
                    stmt_sqlite.on_conflict_do_update(
                        index_elements=["exchange_id", "symbol", "timeframe", "bar_timestamp"],
                        set_={
                            "open_price": stmt_sqlite.excluded.open_price,
                            "high_price": stmt_sqlite.excluded.high_price,
                            "low_price": stmt_sqlite.excluded.low_price,
                            "close_price": stmt_sqlite.excluded.close_price,
                            "volume": stmt_sqlite.excluded.volume,
                        },
                    )
                )

            await session.commit()
            return len(records)

    async def get_candles(
        self,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        start_utc: datetime | None = None,
        end_utc: datetime | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        """Load stored UTC OHLCV bars sorted chronologically ascending."""
        query = (
            select(MarketSnapshotORM)
            .where(
                MarketSnapshotORM.exchange_id == exchange_id.lower().strip(),
                MarketSnapshotORM.symbol == symbol.upper().strip(),
                MarketSnapshotORM.timeframe == timeframe.lower().strip(),
            )
            .order_by(MarketSnapshotORM.bar_timestamp.asc())
            .limit(limit)
        )
        if start_utc is not None:
            query = query.where(MarketSnapshotORM.bar_timestamp >= _ensure_utc(start_utc))
        if end_utc is not None:
            query = query.where(MarketSnapshotORM.bar_timestamp <= _ensure_utc(end_utc))

        async with self._session_factory() as session:
            rows = (await session.execute(query)).scalars().all()

        return [
            OHLCVBar(
                symbol=row.symbol,
                timeframe=row.timeframe,
                timestamp=_ensure_utc(row.bar_timestamp),
                open=row.open_price,
                high=row.high_price,
                low=row.low_price,
                close=row.close_price,
                volume=row.volume,
                is_closed=True,
            )
            for row in rows
        ]

    async def get_latest_timestamp(
        self, exchange_id: str, symbol: str, timeframe: str
    ) -> datetime | None:
        """Return latest stored UTC bar timestamp or None if empty."""
        query = (
            select(func.max(MarketSnapshotORM.bar_timestamp))
            .where(
                MarketSnapshotORM.exchange_id == exchange_id.lower().strip(),
                MarketSnapshotORM.symbol == symbol.upper().strip(),
                MarketSnapshotORM.timeframe == timeframe.lower().strip(),
            )
        )
        async with self._session_factory() as session:
            latest = (await session.execute(query)).scalar_one_or_none()
        return _ensure_utc(latest) if latest is not None else None

    async def get_recent_candles(
        self,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> list[OHLCVBar]:
        """Load the most recent N stored candles returned in ascending chronological order."""
        query = (
            select(MarketSnapshotORM)
            .where(
                MarketSnapshotORM.exchange_id == exchange_id.lower().strip(),
                MarketSnapshotORM.symbol == symbol.upper().strip(),
                MarketSnapshotORM.timeframe == timeframe.lower().strip(),
            )
            .order_by(desc(MarketSnapshotORM.bar_timestamp))
            .limit(limit)
        )
        async with self._session_factory() as session:
            rows = list((await session.execute(query)).scalars().all())
        rows.reverse()
        return [
            OHLCVBar(
                symbol=row.symbol,
                timeframe=row.timeframe,
                timestamp=_ensure_utc(row.bar_timestamp),
                open=row.open_price,
                high=row.high_price,
                low=row.low_price,
                close=row.close_price,
                volume=row.volume,
                is_closed=True,
            )
            for row in rows
        ]
