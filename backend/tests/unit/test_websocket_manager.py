"""Unit tests for MarketDataWebSocketManager (WS streaming, reconnects, polling fallback)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from nexus.application.market_data.websocket_manager import MarketDataWebSocketManager
from nexus.core.exceptions import MarketDataUnavailableError
from nexus.domain.models import OHLCVBar, TickerQuote


class _ReconnectingWsClient:
    exchange_id = "binance"

    def __init__(self, *, supports_ws: bool = True, fail_first_n: int = 0) -> None:
        self._supports_ws = supports_ws
        self._fail_first_n = fail_first_n
        self.watch_calls = 0
        self.fetch_calls = 0

    @property
    def supports_websocket(self) -> bool:
        return self._supports_ws

    async def watch_ohlcv(self, symbol: str, timeframe: str = "15m") -> list[OHLCVBar]:
        self.watch_calls += 1
        if self.watch_calls <= self._fail_first_n:
            raise MarketDataUnavailableError("WebSocket disconnected")
        t_closed = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
        t_open = datetime.now(UTC).replace(second=0, microsecond=0)
        return [
            OHLCVBar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=t_closed,
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("104"),
                volume=Decimal("10"),
            ),
            OHLCVBar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=t_open,
                open=Decimal("104"),
                high=Decimal("106"),
                low=Decimal("103"),
                close=Decimal("105"),
                volume=Decimal("2"),
            ),
        ]

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "15m", since_ms: int | None = None, limit: int = 100
    ) -> list[OHLCVBar]:
        self.fetch_calls += 1
        return await self.watch_ohlcv(symbol, timeframe)

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        raise NotImplementedError

    async def watch_ticker(self, symbol: str) -> TickerQuote:
        raise NotImplementedError

    async def fetch_inr_per_usdt(self) -> Decimal:
        return Decimal("85")

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_ws_manager_reconnects_filters_incomplete_and_deduplicates_emissions() -> None:
    client = _ReconnectingWsClient(supports_ws=True, fail_first_n=1)
    manager = MarketDataWebSocketManager(
        exchange_client=client,
        reconnect_min_delay_s=0.01,
        reconnect_max_delay_s=0.02,
    )
    emitted: list[OHLCVBar] = []

    async def _on_candle(bar: OHLCVBar) -> None:
        emitted.append(bar)

    manager.on_closed_candle(_on_candle)

    # First iteration fails and reconnects; second + third receive the same closed bar
    await manager.stream_ohlcv_loop("SOL/USDT", "15m", max_iterations=3)

    assert client.watch_calls == 3
    assert len(emitted) == 1
    assert emitted[0].timestamp == datetime(2026, 11, 12, 8, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_ws_manager_falls_back_to_rest_polling_when_ws_unsupported() -> None:
    client = _ReconnectingWsClient(supports_ws=False)
    manager = MarketDataWebSocketManager(
        exchange_client=client,
        polling_fallback_interval_s=0.01,
    )
    emitted: list[OHLCVBar] = []

    async def _on_candle(bar: OHLCVBar) -> None:
        emitted.append(bar)

    manager.on_closed_candle(_on_candle)
    await manager.stream_ohlcv_loop("BTC/USDT", "5m", max_iterations=1)

    assert client.fetch_calls == 1
    assert len(emitted) == 1
    assert emitted[0].timestamp <= datetime.now(UTC) - timedelta(minutes=5)

