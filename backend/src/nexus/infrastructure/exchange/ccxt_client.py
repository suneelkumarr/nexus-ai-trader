"""Public-endpoint-only CCXT exchange client (REST + WebSocket).

Guarantees:
- Uses public spot market endpoints only (`defaultType = 'spot'`).
- Never requests, accepts, or configures private API keys.
- Never fabricates or hardcodes fake exchange quotes/candles.
- Handles rate limits and transient network errors with exponential backoff.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import ccxt.async_support as ccxt_async
import ccxt.pro as ccxt_pro
import httpx

from nexus.core.exceptions import (
    MarketDataUnavailableError,
    RateLimitError,
    RiskViolationError,
)
from nexus.core.logging import get_logger
from nexus.domain.models import OHLCVBar, TickerQuote

logger = get_logger(__name__)

_FRANKFURTER_FX_URL = "https://api.frankfurter.dev/v1/latest"
_SUPPORTED_TIMEFRAMES: frozenset[str] = frozenset({"5m", "15m", "1h", "4h"})

_RETRYABLE_ERRORS: tuple[type[BaseException], ...] = (
    ccxt_async.RateLimitExceeded,
    ccxt_async.DDoSProtection,
    ccxt_async.NetworkError,
    ccxt_async.ExchangeNotAvailable,
    ccxt_async.RequestTimeout,
)


def to_positive_decimal(value: Any, field_name: str) -> Decimal:
    """Convert numeric exchange field to positive finite Decimal."""
    if value is None:
        raise MarketDataUnavailableError(
            f"Exchange payload missing required field '{field_name}'."
        )
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MarketDataUnavailableError(
            f"Invalid numeric value for '{field_name}': {value!r}"
        ) from exc
    if not dec.is_finite() or dec <= Decimal("0"):
        raise MarketDataUnavailableError(
            f"Non-positive or non-finite value for '{field_name}': {dec}"
        )
    return dec


def parse_ticker_payload(symbol: str, exchange_id: str, raw: Any) -> TickerQuote:
    """Validate and parse a CCXT ticker dict into a UTC TickerQuote."""
    if not isinstance(raw, dict):
        raise MarketDataUnavailableError(
            f"Malformed ticker payload from {exchange_id} for {symbol}"
        )
    last = to_positive_decimal(raw.get("last") or raw.get("close"), "last")
    bid = to_positive_decimal(raw.get("bid") or last, "bid")
    ask = to_positive_decimal(raw.get("ask") or last, "ask")
    ts_ms = raw.get("timestamp")
    if not isinstance(ts_ms, (int, float)) or ts_ms <= 0:
        raise MarketDataUnavailableError(
            f"Exchange {exchange_id} ticker payload for {symbol} is missing verified timestamp"
        )
    timestamp = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=UTC)
    return TickerQuote(
        symbol=symbol,
        exchange_id=exchange_id,
        bid=bid,
        ask=ask,
        last=last,
        timestamp=timestamp,
    )


def parse_ohlcv_rows(
    symbol: str, exchange_id: str, timeframe: str, rows: Any
) -> list[OHLCVBar]:
    """Validate and parse CCXT OHLCV matrix into UTC OHLCVBar models."""
    if not rows:
        raise MarketDataUnavailableError(
            f"Exchange {exchange_id} returned empty OHLCV for {symbol} ({timeframe})"
        )
    bars: list[OHLCVBar] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise MarketDataUnavailableError(
                f"Malformed OHLCV row from {exchange_id} for {symbol}"
            )
        ts_ms, open_p, high_p, low_p, close_p, volume = row[:6]
        try:
            vol_dec = Decimal(str(volume))
        except (InvalidOperation, ValueError) as exc:
            raise MarketDataUnavailableError(
                f"Invalid candle volume from {exchange_id}: {volume!r}"
            ) from exc
        if not vol_dec.is_finite() or vol_dec < Decimal("0"):
            raise MarketDataUnavailableError("Negative or non-finite candle volume received")
        bars.append(
            OHLCVBar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=UTC),
                open=to_positive_decimal(open_p, "open"),
                high=to_positive_decimal(high_p, "high"),
                low=to_positive_decimal(low_p, "low"),
                close=to_positive_decimal(close_p, "close"),
                volume=vol_dec,
            )
        )
    return bars


class CCXTPublicExchangeClient:
    """Public-only async CCXT client with rate-limit backoff and WebSocket support."""

    def __init__(
        self,
        *,
        exchange_id: str,
        allowed_symbols: list[str],
        supported_timeframes: list[str] | None = None,
        timeout_ms: int = 10000,
        max_retries: int = 3,
        backoff_base_s: float = 0.5,
        rest_factory: Callable[[str, dict[str, Any]], Any] | None = None,
        ws_factory: Callable[[str, dict[str, Any]], Any] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._exchange_id = exchange_id.lower().strip()
        self._allowed_symbols = {s.strip().upper() for s in allowed_symbols}
        self._supported_timeframes = (
            {tf.strip().lower() for tf in supported_timeframes}
            if supported_timeframes is not None
            else set(_SUPPORTED_TIMEFRAMES)
        )
        self._timeout_ms = timeout_ms
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout_ms / 1000.0)
        self._owns_http_client = http_client is None
        self._cached_inr_rate: Decimal | None = None
        self._cached_inr_ts: float = 0.0
        self._inr_cache_ttl_s: float = 1800.0  # 30-minute cache TTL

        # Public endpoints only — never include apiKey or secret.
        public_config: dict[str, Any] = {
            "enableRateLimit": True,
            "timeout": timeout_ms,
            "options": {"defaultType": "spot"},
        }
        if self._exchange_id == "binance":
            public_config["urls"] = {
                "api": {
                    "public": "https://data-api.binance.vision/api/v3",
                }
            }

        if rest_factory is not None:
            self._rest = rest_factory(self._exchange_id, dict(public_config))
        else:
            rest_cls = getattr(ccxt_async, self._exchange_id, None)
            if rest_cls is None:
                raise MarketDataUnavailableError(
                    f"Unsupported CCXT exchange_id: '{self._exchange_id}'"
                )
            self._rest = rest_cls(dict(public_config))

        if ws_factory is not None:
            self._ws = ws_factory(self._exchange_id, dict(public_config))
        else:
            ws_cls = getattr(ccxt_pro, self._exchange_id, None)
            self._ws = ws_cls(dict(public_config)) if ws_cls is not None else None

    @property
    def exchange_id(self) -> str:
        """Return configured exchange identifier."""
        return self._exchange_id

    @property
    def supports_websocket(self) -> bool:
        """Return True when CCXT Pro WebSocket OHLCV/ticker streaming is available."""
        if self._ws is None:
            return False
        has_map = getattr(self._ws, "has", {}) or {}
        if isinstance(has_map, dict) and (
            has_map.get("watchOHLCV") or has_map.get("watchTicker")
        ):
            return True
        return hasattr(self._ws, "watch_ohlcv") or hasattr(self._ws, "watch_ticker")

    def _validate_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if normalized not in self._allowed_symbols:
            allowed = sorted(self._allowed_symbols)
            raise RiskViolationError(
                f"Symbol '{symbol}' is not in allowed spot universe: {allowed}"
            )
        return normalized

    def _validate_timeframe(self, timeframe: str) -> str:
        normalized = timeframe.strip().lower()
        if normalized not in self._supported_timeframes:
            allowed = sorted(self._supported_timeframes)
            raise RiskViolationError(
                f"Timeframe '{timeframe}' is not supported. Allowed: {allowed}"
            )
        return normalized

    async def _execute_with_retry(
        self, operation_name: str, coro_factory: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Execute an async exchange call with exponential backoff on transient errors."""
        last_exc: BaseException | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await coro_factory()
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                is_rate_limit = isinstance(
                    exc, (ccxt_async.RateLimitExceeded, ccxt_async.DDoSProtection)
                )
                if attempt >= self._max_retries:
                    logger.error(
                        "exchange_request_exhausted_retries",
                        exchange_id=self._exchange_id,
                        operation=operation_name,
                        attempts=attempt + 1,
                        rate_limited=is_rate_limit,
                        error=str(exc),
                    )
                    if is_rate_limit:
                        raise RateLimitError(
                            f"Rate limit exceeded on {self._exchange_id} during {operation_name}"
                        ) from exc
                    raise MarketDataUnavailableError(
                        f"Network/availability failure on {self._exchange_id} "
                        f"during {operation_name}"
                    ) from exc

                delay = self._backoff_base_s * (2**attempt) + random.uniform(0.0, 0.15)
                logger.warning(
                    "exchange_request_retrying",
                    exchange_id=self._exchange_id,
                    operation=operation_name,
                    attempt=attempt + 1,
                    delay_s=round(delay, 3),
                    rate_limited=is_rate_limit,
                    error=str(exc),
                )
                await asyncio.sleep(delay)
            except MarketDataUnavailableError:
                raise
            except Exception as exc:
                logger.error(
                    "exchange_request_failed",
                    exchange_id=self._exchange_id,
                    operation=operation_name,
                    error=str(exc),
                )
                raise MarketDataUnavailableError(
                    f"Failed {operation_name} on {self._exchange_id}: {exc}"
                ) from exc

        raise MarketDataUnavailableError(
            f"Unexpected retry termination for {operation_name}: {last_exc}"
        )

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        """Fetch real spot ticker quote via public REST endpoint."""
        normalized = self._validate_symbol(symbol)
        raw = await self._execute_with_retry(
            f"fetch_ticker:{normalized}",
            lambda: self._rest.fetch_ticker(normalized),
        )
        return parse_ticker_payload(normalized, self._exchange_id, raw)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        since_ms: int | None = None,
        limit: int = 100,
    ) -> list[OHLCVBar]:
        """Fetch real spot OHLCV candlesticks in UTC via public REST endpoint."""
        normalized_sym = self._validate_symbol(symbol)
        normalized_tf = self._validate_timeframe(timeframe)
        rows = await self._execute_with_retry(
            f"fetch_ohlcv:{normalized_sym}:{normalized_tf}",
            lambda: self._rest.fetch_ohlcv(
                normalized_sym, timeframe=normalized_tf, since=since_ms, limit=limit
            ),
        )
        return parse_ohlcv_rows(normalized_sym, self._exchange_id, normalized_tf, rows)

    async def watch_ticker(self, symbol: str) -> TickerQuote:
        """Await next real spot ticker update over public WebSocket."""
        if not self.supports_websocket or self._ws is None:
            raise MarketDataUnavailableError(
                f"Exchange '{self._exchange_id}' does not support WebSocket watch_ticker."
            )
        normalized = self._validate_symbol(symbol)
        try:
            raw = await self._ws.watch_ticker(normalized)
        except Exception as exc:
            raise MarketDataUnavailableError(
                f"WebSocket watch_ticker failed for {normalized}: {exc}"
            ) from exc
        return parse_ticker_payload(normalized, self._exchange_id, raw)

    async def watch_ohlcv(self, symbol: str, timeframe: str = "15m") -> list[OHLCVBar]:
        """Await next real spot OHLCV update over public WebSocket."""
        if not self.supports_websocket or self._ws is None:
            raise MarketDataUnavailableError(
                f"Exchange '{self._exchange_id}' does not support WebSocket watch_ohlcv."
            )
        normalized_sym = self._validate_symbol(symbol)
        normalized_tf = self._validate_timeframe(timeframe)
        try:
            rows = await self._ws.watch_ohlcv(normalized_sym, timeframe=normalized_tf)
        except Exception as exc:
            raise MarketDataUnavailableError(
                f"WebSocket watch_ohlcv failed for {normalized_sym} ({normalized_tf}): {exc}"
            ) from exc
        return parse_ohlcv_rows(normalized_sym, self._exchange_id, normalized_tf, rows)

    async def fetch_inr_per_usdt(self) -> Decimal:
        """Fetch live INR per 1 USDT rate with 30-minute caching and resilient fallback."""
        import time
        now = time.monotonic()
        if (
            self._cached_inr_rate is not None
            and self._cached_inr_ts > 0
            and (now - self._cached_inr_ts) < self._inr_cache_ttl_s
        ):
            return self._cached_inr_rate

        try:
            raw = await self._rest.fetch_ticker("USDT/INR")
            if isinstance(raw, dict) and (raw.get("last") or raw.get("bid")):
                rate = to_positive_decimal(raw.get("last") or raw.get("bid"), "USDT/INR")
                self._cached_inr_rate = rate
                self._cached_inr_ts = now
                return rate
        except Exception:
            logger.debug(
                "exchange_usdt_inr_unavailable_trying_fx_feed",
                exchange_id=self._exchange_id,
            )

        try:
            response = await self._http_client.get(
                _FRANKFURTER_FX_URL,
                params={"base": "USD", "symbols": "INR"},
            )
            response.raise_for_status()
            payload = response.json()
            rate_val = payload.get("rates", {}).get("INR")
            rate = to_positive_decimal(rate_val, "USD/INR")
            self._cached_inr_rate = rate
            self._cached_inr_ts = now
            return rate
        except Exception as exc:
            if self._cached_inr_rate is not None:
                logger.warning(
                    "fx_rate_fetch_failed_using_previous_cached_rate",
                    fallback=str(self._cached_inr_rate),
                    error=str(exc),
                )
                return self._cached_inr_rate
            raise MarketDataUnavailableError(
                f"Failed to obtain INR/USDT conversion rate from both exchange and FX feed: {exc}"
            ) from exc

    async def health_check(self) -> bool:
        """Check whether the public exchange REST endpoint is reachable."""
        try:
            await self._rest.fetch_time()
            return True
        except Exception as exc:
            logger.warning(
                "exchange_health_check_failed",
                exchange_id=self._exchange_id,
                error=str(exc),
            )
            return False

    async def close(self) -> None:
        """Close underlying REST, WebSocket, and HTTP async clients."""
        if hasattr(self._rest, "close"):
            await self._rest.close()
        if self._ws is not None and hasattr(self._ws, "close"):
            await self._ws.close()
        if self._owns_http_client:
            await self._http_client.aclose()

