"""Unit tests for AutonomousPaperTradingOrchestrator wiring and checkpoint safety."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from nexus.application.persistent_paper_broker import PersistentPaperBroker
from nexus.application.risk_guard import SpotSignalRiskApprover
from nexus.application.risk_manager import IndependentRiskManager
from nexus.application.strategy.v1_engine import NexusStrategyV1
from nexus.core.config import Settings
from nexus.domain.models import OHLCVBar, TickerQuote
from nexus.infrastructure.db.base import Base
from nexus.infrastructure.db.paper_repository import SqlAlchemyPaperRepository
from nexus.infrastructure.db.session import DatabaseManager
from nexus.workers.scheduler import AutonomousPaperTradingOrchestrator


class _MockMarketData:
    def __init__(self, bars: list[OHLCVBar], quote: TickerQuote) -> None:
        self.bars = bars
        self.quote = quote

    async def get_closed_candles_for_signal(
        self, symbol: str, timeframe: str, **kwargs: object
    ) -> tuple[list[OHLCVBar], None]:
        return self.bars, None

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        return self.quote

    async def fetch_inr_per_usdt(self) -> Decimal:
        return Decimal("85.00")


@pytest.mark.asyncio
async def test_orchestrator_halts_cleanly_when_kill_switch_active() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url_override="sqlite+aiosqlite:///:memory:",
    )
    db = DatabaseManager(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    repo = SqlAlchemyPaperRepository(db.session_factory)
    portfolio = await repo.get_or_create_portfolio(
        None, initial_capital_inr=settings.initial_capital_inr
    )
    risk = IndependentRiskManager(
        allowed_symbols=settings.allowed_symbols,
        risk_config=settings.risk,
    )
    strategy = NexusStrategyV1(
        config=settings.strategy_v1,
        risk_approver=SpotSignalRiskApprover(allowed_symbols=settings.allowed_symbols),
    )
    feed = _MockMarketData(
        [],
        TickerQuote(
            symbol="BTC/USDT",
            exchange_id="binance",
            bid=Decimal("90000"),
            ask=Decimal("90010"),
            last=Decimal("90005"),
            timestamp=datetime.now(UTC),
        ),
    )
    broker = PersistentPaperBroker(
        repository=repo,
        risk_manager=risk,
        market_data=feed,  # type: ignore[arg-type]
        initial_capital_inr=settings.initial_capital_inr,
    )
    await broker.activate_kill_switch(portfolio.id, reason="Unit test emergency halt")

    orchestrator = AutonomousPaperTradingOrchestrator(
        settings=settings,
        market_data=feed,  # type: ignore[arg-type]
        strategy_v1=strategy,
        broker=broker,
        repository=repo,
        risk_manager=risk,
    )

    summary = await orchestrator.run_cycle()
    assert summary.kill_switch_active is True
    assert len(summary.orders_executed) == 0
    await db.dispose()
