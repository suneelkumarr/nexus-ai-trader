"""Public WebSocket market data manager with reconnect backoff and polling fallback."""

import asyncio
import contextlib
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from nexus.application.market_data.validator import CandleValidator, get_timeframe_seconds
from nexus.core.exceptions import MarketDataUnavailableError, RateLimitError
from nexus.core.logging import get_logger
from nexus.domain.interfaces import CandleRepository, PublicExchangeClient
from nexus.domain.models import OHLCVBar, TickerQuote

logger = get_logger(__name__)

CandleCallback = Callable[[OHLCVBar], Awaitable[None]]
TickerCallback = Callable[[TickerQuote], Awaitable[None]]


class MarketDataWebSocketManager:
    """Streams real-time spot OHLCV and ticker updates with resilient reconnection."""

    def __init__(
        self,
        *,
        exchange_client: PublicExchangeClient,
        candle_repository: CandleRepository | None = None,
        validator: CandleValidator | None = None,
        reconnect_min_delay_s: float = 1.0,
        reconnect_max_delay_s: float = 30.0,
        polling_fallback_interval_s: float = 15.0,
    ) -> None:
        self._exchange = exchange_client
        self._repository = candle_repository
        self._validator = validator or CandleValidator()
        self._min_delay_s = reconnect_min_delay_s
        self._max_delay_s = reconnect_max_delay_s
        self._poll_interval_s = polling_fallback_interval_s

        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._candle_callbacks: list[CandleCallback] = []
        self._ticker_callbacks: list[TickerCallback] = []
        self._last_emitted_bar_ts: dict[tuple[str, str], datetime] = {}

    def on_closed_candle(self, callback: CandleCallback) -> None:
        """Register an async listener invoked whenever a newly closed candle arrives."""
        self._candle_callbacks.append(callback)

    def on_ticker(self, callback: TickerCallback) -> None:
        """Register an async listener invoked on each live ticker update."""
        self._ticker_callbacks.append(callback)

    async def process_ohlcv_batch(
        self,
        symbol: str,
        timeframe: str,
        bars: list[OHLCVBar],
        *,
        now_utc: datetime | None = None,
    ) -> list[OHLCVBar]:
        """Validate WebSocket OHLCV updates, persist closed candles, and notify listeners."""
        ref_now = now_utc or datetime.now(UTC)
        closed_bars, _ = self._validator.validate_and_clean(
            bars,
            symbol=symbol,
            timeframe=timeframe,
            now_utc=ref_now,
            reject_incomplete=True,
            strict=False,
        )
        if not closed_bars:
            return []

        key = (symbol.upper().strip(), timeframe.lower().strip())
        prev_ts = self._last_emitted_bar_ts.get(key)
        newly_closed = [b for b in closed_bars if prev_ts is None or b.timestamp > prev_ts]
        if not newly_closed:
            return []

        if self._repository is not None:
            await self._repository.upsert_candles(self._exchange.exchange_id, newly_closed)

        self._last_emitted_bar_ts[key] = newly_closed[-1].timestamp
        for bar in newly_closed:
            for cb in self._candle_callbacks:
                await cb(bar)
        return newly_closed

    async def stream_ohlcv_loop(
        self,
        symbol: str,
        timeframe: str,
        *,
        max_iterations: int | None = None,
    ) -> None:
        """Continuously watch OHLCV (via WS or REST fallback) with exponential reconnect backoff."""
        get_timeframe_seconds(timeframe)
        consecutive_failures = 0
        iterations = 0
        use_ws = self._exchange.supports_websocket

        if not use_ws:
            logger.info(
                "websocket_unsupported_using_rest_polling",
                exchange_id=self._exchange.exchange_id,
                symbol=symbol,
                timeframe=timeframe,
            )

        while not self._stop_event.is_set():
            if max_iterations is not None and iterations >= max_iterations:
                break
            iterations += 1

            try:
                if use_ws:
                    bars = await self._exchange.watch_ohlcv(symbol, timeframe=timeframe)
                else:
                    bars = await self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=5)

                consecutive_failures = 0
                await self.process_ohlcv_batch(symbol, timeframe, bars)

                if not use_ws and not self._stop_event.is_set():
                    await asyncio.sleep(self._poll_interval_s)
            except asyncio.CancelledError:
                raise
            except (RateLimitError, MarketDataUnavailableError, Exception) as exc:
                consecutive_failures += 1
                backoff = min(
                    self._max_delay_s,
                    self._min_delay_s * (2 ** (consecutive_failures - 1)),
                )
                delay = backoff + random.uniform(0.0, 0.25)
                logger.warning(
                    "market_stream_reconnecting",
                    exchange_id=self._exchange.exchange_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    mode="websocket" if use_ws else "polling",
                    failures=consecutive_failures,
                    reconnect_delay_s=round(delay, 3),
                    error=str(exc),
                )
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)

    async def stream_ticker_loop(
        self,
        symbol: str,
        *,
        max_iterations: int | None = None,
    ) -> None:
        """Continuously stream spot ticker quotes with reconnect backoff."""
        consecutive_failures = 0
        iterations = 0
        use_ws = self._exchange.supports_websocket

        while not self._stop_event.is_set():
            if max_iterations is not None and iterations >= max_iterations:
                break
            iterations += 1

            try:
                quote = (
                    await self._exchange.watch_ticker(symbol)
                    if use_ws
                    else await self._exchange.fetch_ticker(symbol)
                )
                consecutive_failures = 0
                for cb in self._ticker_callbacks:
                    await cb(quote)

                if not use_ws and not self._stop_event.is_set():
                    await asyncio.sleep(self._poll_interval_s)
            except asyncio.CancelledError:
                raise
            except (RateLimitError, MarketDataUnavailableError, Exception) as exc:
                consecutive_failures += 1
                backoff = min(
                    self._max_delay_s,
                    self._min_delay_s * (2 ** (consecutive_failures - 1)),
                )
                delay = backoff + random.uniform(0.0, 0.25)
                logger.warning(
                    "ticker_stream_reconnecting",
                    exchange_id=self._exchange.exchange_id,
                    symbol=symbol,
                    failures=consecutive_failures,
                    reconnect_delay_s=round(delay, 3),
                    error=str(exc),
                )
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)

    def start(self, symbols: list[str], timeframes: list[str]) -> None:
        """Launch background streaming tasks for all symbol/timeframe pairs."""
        self._stop_event.clear()
        for symbol in symbols:
            self._tasks.append(
                asyncio.create_task(
                    self.stream_ticker_loop(symbol),
                    name=f"nexus-ticker-{symbol}",
                )
            )
            for timeframe in timeframes:
                self._tasks.append(
                    asyncio.create_task(
                        self.stream_ohlcv_loop(symbol, timeframe),
                        name=f"nexus-ohlcv-{symbol}-{timeframe}",
                    )
                )

    async def stop(self) -> None:
        """Signal all streaming loops to stop and await clean task cancellation."""
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
