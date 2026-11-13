"""Async SQLAlchemy engine, session factory, and health diagnostics."""

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from nexus.core.config import Settings
from nexus.core.logging import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """Manages async SQLAlchemy engine lifecycle and session creation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        engine_kwargs: dict[str, object] = {
            "echo": settings.database_echo,
            "pool_pre_ping": True,
        }
        if not settings.async_database_url.startswith("sqlite"):
            engine_kwargs["pool_size"] = settings.db_pool_size
            engine_kwargs["max_overflow"] = settings.db_max_overflow

        self.engine: AsyncEngine = create_async_engine(
            settings.async_database_url,
            **engine_kwargs,
        )
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield an async database session with clean rollback on failure."""
        async with self.session_factory() as db_session:
            try:
                yield db_session
            except Exception:
                await db_session.rollback()
                raise

    async def check_health(self) -> tuple[bool, str | None]:
        """Execute a lightweight SELECT 1 probe against PostgreSQL."""
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True, None
        except Exception as exc:
            logger.warning(
                "database_health_check_failed",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return False, "Database connectivity check failed"

    async def dispose(self) -> None:
        """Close all pooled connections gracefully on shutdown."""
        await self.engine.dispose()

