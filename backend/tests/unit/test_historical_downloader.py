"""Unit tests for HistoricalDataDownloader pagination, deduplication, and persistence."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from nexus.application.market_data.downloader import HistoricalDataDownloader
from nexus.domain.models import OHLCVBar, TickerQuote


class _PaginatingExchangeClient:
    exchange_id = "binance"
    supports_websocket = False

    def __init__(self, all_bars: list[OHLCVBar]) -> None:
        self._bars = sorted(all_bars, key=lambda b: b.timestamp)
        self.fetch_calls: list[tuple[str, str, int | None, int]] = []

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        raise NotImplementedError

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        since_ms: int | None = None,
        limit: int = 100,
    ) -> list[OHLCVBar]:
        self.fetch_calls.append((symbol, timeframe, since_ms, limit))
        matching = [
            b
            for b in self._bars
            if b.symbol == symbol
            and b.timeframe == timeframe
            and (since_ms is None or int(b.timestamp.timestamp() * 1000) >= since_ms)
        ]
        return matching[:limit]

    async def fetch_inr_per_usdt(self) -> Decimal:
        return Decimal("85")

    async def watch_ticker(self, symbol: str) -> TickerQuote:
        raise NotImplementedError

    async def watch_ohlcv(self, symbol: str, timeframe: str = "15m") -> list[OHLCVBar]:
        raise NotImplementedError

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class _InMemoryCandleRepo:
    def __init__(self) -> None:
        self.stored: dict[tuple[str, str, str, datetime], OHLCVBar] = {}

    async def upsert_candles(self, exchange_id: str, bars: Sequence[OHLCVBar]) -> int:
        for b in bars:
            self.stored[(exchange_id, b.symbol, b.timeframe, b.timestamp)] = b
        return len(bars)

    async def get_candles(
        self,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        start_utc: datetime | None = None,
        end_utc: datetime | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        return [
            b
            for (ex, sym, tf, _ts), b in sorted(self.stored.items(), key=lambda item: item[0][3])
            if ex == exchange_id and sym == symbol and tf == timeframe
        ][:limit]

    async def get_latest_timestamp(
        self, exchange_id: str, symbol: str, timeframe: str
    ) -> datetime | None:
        times = [
            ts
            for (ex, sym, tf, ts) in self.stored
            if ex == exchange_id and sym == symbol and tf == timeframe
        ]
        return max(times) if times else None


@pytest.mark.asyncio
async def test_downloader_paginates_filters_incomplete_and_persists() -> None:
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
    # 5 closed 5m candles + 1 incomplete candle starting at 10:25 when end_utc is 10:27
    bars = [
        OHLCVBar(
            symbol="BTC/USDT",
            timeframe="5m",
            timestamp=t0 + timedelta(minutes=5 * i),
            open=Decimal("90000"),
            high=Decimal("90100"),
            low=Decimal("89900"),
            close=Decimal("90050"),
            volume=Decimal("5"),
        )
        for i in range(6)
    ]
    end_utc = t0 + timedelta(minutes=27)
    exchange = _PaginatingExchangeClient(bars)
    repo = _InMemoryCandleRepo()

    downloader = HistoricalDataDownloader(
        exchange_client=exchange,
        candle_repository=repo,
        batch_limit=2,
        inter_request_delay_s=0.0,
    )
    summary = await downloader.download_range(
        symbol="BTC/USDT",
        timeframe="5m",
        start_utc=t0,
        end_utc=end_utc,
    )

    assert len(exchange.fetch_calls) >= 3
    assert summary.stored_count == 5
    assert summary.validation.rejected_incomplete_count == 1
    assert summary.validation.is_clean is True


@pytest.mark.asyncio
async def test_downloader_sync_all_covers_universe_and_timeframes() -> None:
    t0 = datetime(2026, 11, 12, 0, 0, tzinfo=UTC)
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    timeframes = ["5m", "15m", "1h", "4h"]
    bars = [
        OHLCVBar(
            symbol=sym,
            timeframe=tf,
            timestamp=t0,
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("1"),
        )
        for sym in symbols
        for tf in timeframes
    ]
    downloader = HistoricalDataDownloader(
        exchange_client=_PaginatingExchangeClient(bars),
        candle_repository=_InMemoryCandleRepo(),
        inter_request_delay_s=0.0,
    )
    summaries = await downloader.sync_all(
        symbols=symbols,
        timeframes=timeframes,
        lookback_bars=100,
        end_utc=t0 + timedelta(hours=5),
    )
    assert len(summaries) == 12
    assert all(s.stored_count == 1 for s in summaries)
