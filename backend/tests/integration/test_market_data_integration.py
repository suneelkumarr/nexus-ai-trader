"""Integration tests for PostgreSQL/SQLAlchemy candle storage and MarketDataService."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from nexus.application.market_data.service import MarketDataService
from nexus.application.market_data.validator import CandleValidator
from nexus.application.strategy_engine import EmaCrossoverStrategy
from nexus.core.config import Settings
from nexus.core.exceptions import CandleValidationError, IncompleteCandleError
from nexus.domain.models import OHLCVBar, TickerQuote
from nexus.infrastructure.db.base import Base
from nexus.infrastructure.db.candle_repository import SqlAlchemyCandleRepository
from nexus.infrastructure.db.session import DatabaseManager
from nexus.workers.scheduler import PaperTradingCycleRunner


class _PublicStubExchange:
    exchange_id = "binance"
    supports_websocket = False

    def __init__(self, bars: list[OHLCVBar]) -> None:
        self._bars = bars

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        return TickerQuote(
            symbol=symbol,
            exchange_id=self.exchange_id,
            bid=Decimal("90000"),
            ask=Decimal("90010"),
            last=Decimal("90005"),
            timestamp=datetime.now(UTC),
        )

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        since_ms: int | None = None,
        limit: int = 100,
    ) -> list[OHLCVBar]:
        filtered = [
            b
            for b in self._bars
            if b.symbol == symbol
            and b.timeframe == timeframe
            and (since_ms is None or int(b.timestamp.timestamp() * 1000) >= since_ms)
        ]
        return filtered[:limit]

    async def fetch_inr_per_usdt(self) -> Decimal:
        return Decimal("85.0")

    async def watch_ticker(self, symbol: str) -> TickerQuote:
        raise NotImplementedError

    async def watch_ohlcv(self, symbol: str, timeframe: str = "15m") -> list[OHLCVBar]:
        raise NotImplementedError

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_candle_repository_upsert_and_utc_persistence(test_settings: Settings) -> None:
    db = DatabaseManager(test_settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    repo = SqlAlchemyCandleRepository(db.session_factory)
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
    bar_v1 = OHLCVBar(
        symbol="BTC/USDT",
        timeframe="15m",
        timestamp=t0,
        open=Decimal("90000"),
        high=Decimal("90100"),
        low=Decimal("89900"),
        close=Decimal("90020"),
        volume=Decimal("10"),
    )
    bar_v2 = bar_v1.model_copy(update={"close": Decimal("90080")})

    await repo.upsert_candles("binance", [bar_v1])
    await repo.upsert_candles("binance", [bar_v2])

    loaded = await repo.get_candles("binance", "BTC/USDT", "15m")
    assert len(loaded) == 1
    assert loaded[0].close == Decimal("90080")
    assert loaded[0].timestamp == t0
    assert loaded[0].timestamp.tzinfo == UTC
    assert await repo.get_latest_timestamp("binance", "BTC/USDT", "15m") == t0

    await db.dispose()


@pytest.mark.asyncio
async def test_market_data_service_download_store_and_signal_gating(
    test_settings: Settings,
) -> None:
    db = DatabaseManager(test_settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    repo = SqlAlchemyCandleRepository(db.session_factory)
    t0 = datetime(2026, 11, 12, 0, 0, tzinfo=UTC)
    now_utc = t0 + timedelta(minutes=15 * 30 + 5)  # 30th bar is still forming!

    bars: list[OHLCVBar] = []
    for symbol in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
        for i in range(31):
            bars.append(
                OHLCVBar(
                    symbol=symbol,
                    timeframe="15m",
                    timestamp=t0 + timedelta(minutes=15 * i),
                    open=Decimal(str(100 + i)),
                    high=Decimal(str(102 + i)),
                    low=Decimal(str(99 + i)),
                    close=Decimal(str(101 + i)),
                    volume=Decimal("25"),
                )
            )

    service = MarketDataService(
        settings=test_settings,
        exchange_client=_PublicStubExchange(bars),
        candle_repository=repo,
    )

    summary = await service.download_historical(
        symbol="BTC/USDT",
        timeframe="15m",
        start_utc=t0,
        end_utc=now_utc,
    )
    assert summary.stored_count == 30
    assert summary.validation.rejected_incomplete_count == 1

    stored = await service.get_stored_candles("BTC/USDT", "15m")
    assert len(stored) == 30

    closed_bars, df = await service.get_closed_candles_for_signal(
        "BTC/USDT", "15m", min_bars=25, now_utc=now_utc
    )
    assert len(closed_bars) == 30
    assert len(df) == 30

    runner = PaperTradingCycleRunner(
        settings=test_settings,
        market_data=service,
        strategy=EmaCrossoverStrategy(fast_span=9, slow_span=21),
    )
    signals = await runner.run_once(now_utc=now_utc)
    assert [s.symbol for s in signals] == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

    # Incomplete candles are rejected for signal generation
    with pytest.raises(IncompleteCandleError):
        CandleValidator.validate_for_signal_generation(
            bars[:2],
            symbol="BTC/USDT",
            timeframe="15m",
            now_utc=t0 + timedelta(minutes=20),
        )
    with pytest.raises(CandleValidationError):
        await runner.run_once(now_utc=t0 + timedelta(minutes=5))

    await service.close()
    await db.dispose()
