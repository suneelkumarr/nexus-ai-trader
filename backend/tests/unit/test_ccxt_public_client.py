"""Unit tests for CCXTPublicExchangeClient (public-only, retry/backoff, WebSocket)."""

from decimal import Decimal
from typing import Any

import ccxt.async_support as ccxt_async
import pytest

from nexus.core.exceptions import MarketDataUnavailableError, RateLimitError, RiskViolationError
from nexus.infrastructure.exchange.ccxt_client import CCXTPublicExchangeClient


class _FlakyRestExchange:
    def __init__(self, failures_before_ok: int = 0, error_cls: type[Exception] = Exception) -> None:
        self.failures_before_ok = failures_before_ok
        self.error_cls = error_cls
        self.calls = 0

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "15m", since: int | None = None, limit: int = 100
    ) -> list[list[Any]]:
        self.calls += 1
        if self.calls <= self.failures_before_ok:
            raise self.error_cls("transient error")
        return [[1700000000000, 90000.0, 90100.0, 89900.0, 90050.0, 10.0]]

    async def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        return {"bid": 90000.0, "ask": 90010.0, "last": 90005.0, "timestamp": 1700000000000}

    async def fetch_time(self) -> int:
        return 1700000000000

    async def close(self) -> None:
        return None


class _StubWsExchange:
    has = {"watchOHLCV": True, "watchTicker": True}

    async def watch_ohlcv(self, symbol: str, timeframe: str = "15m") -> list[list[Any]]:
        return [[1700000000000, 3000.0, 3020.0, 2990.0, 3010.0, 25.0]]

    async def watch_ticker(self, symbol: str) -> dict[str, Any]:
        return {"bid": 3009.0, "ask": 3011.0, "last": 3010.0, "timestamp": 1700000000000}

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_public_client_never_sets_private_keys_and_enforces_spot() -> None:
    captured_rest_cfg: dict[str, Any] = {}
    captured_ws_cfg: dict[str, Any] = {}

    def rest_factory(_id: str, cfg: dict[str, Any]) -> _FlakyRestExchange:
        captured_rest_cfg.update(cfg)
        return _FlakyRestExchange()

    def ws_factory(_id: str, cfg: dict[str, Any]) -> _StubWsExchange:
        captured_ws_cfg.update(cfg)
        return _StubWsExchange()

    client = CCXTPublicExchangeClient(
        exchange_id="binance",
        allowed_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        supported_timeframes=["5m", "15m", "1h", "4h"],
        rest_factory=rest_factory,
        ws_factory=ws_factory,
    )

    assert "apiKey" not in captured_rest_cfg
    assert "secret" not in captured_rest_cfg
    assert "apiKey" not in captured_ws_cfg
    assert captured_rest_cfg["options"]["defaultType"] == "spot"
    assert captured_rest_cfg["enableRateLimit"] is True
    assert client.supports_websocket is True

    bars = await client.watch_ohlcv("ETH/USDT", timeframe="15m")
    assert bars[0].close == Decimal("3010.0")
    assert bars[0].timestamp.tzinfo is not None

    quote = await client.watch_ticker("ETH/USDT")
    assert quote.last == Decimal("3010.0")
    await client.close()


@pytest.mark.asyncio
async def test_public_client_retries_rate_limits_and_raises_after_exhaustion() -> None:
    rest = _FlakyRestExchange(failures_before_ok=2, error_cls=ccxt_async.RateLimitExceeded)
    client = CCXTPublicExchangeClient(
        exchange_id="binance",
        allowed_symbols=["BTC/USDT"],
        max_retries=2,
        backoff_base_s=0.01,
        rest_factory=lambda _id, _cfg: rest,
        ws_factory=lambda _id, _cfg: _StubWsExchange(),
    )
    bars = await client.fetch_ohlcv("BTC/USDT", timeframe="5m")
    assert len(bars) == 1
    assert rest.calls == 3

    always_limited = _FlakyRestExchange(
        failures_before_ok=10, error_cls=ccxt_async.RateLimitExceeded
    )
    client_limited = CCXTPublicExchangeClient(
        exchange_id="binance",
        allowed_symbols=["BTC/USDT"],
        max_retries=1,
        backoff_base_s=0.01,
        rest_factory=lambda _id, _cfg: always_limited,
        ws_factory=lambda _id, _cfg: _StubWsExchange(),
    )
    with pytest.raises(RateLimitError):
        await client_limited.fetch_ohlcv("BTC/USDT", timeframe="5m")
    await client.close()
    await client_limited.close()


@pytest.mark.asyncio
async def test_public_client_rejects_unsupported_symbol_and_timeframe() -> None:
    client = CCXTPublicExchangeClient(
        exchange_id="binance",
        allowed_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        supported_timeframes=["5m", "15m", "1h", "4h"],
        rest_factory=lambda _id, _cfg: _FlakyRestExchange(),
        ws_factory=lambda _id, _cfg: _StubWsExchange(),
    )
    with pytest.raises(RiskViolationError):
        await client.fetch_ohlcv("DOGE/USDT", timeframe="15m")

    with pytest.raises(RiskViolationError):
        await client.fetch_ohlcv("BTC/USDT", timeframe="1m")

    await client.close()


@pytest.mark.asyncio
async def test_public_client_raises_when_websocket_unsupported() -> None:
    client = CCXTPublicExchangeClient(
        exchange_id="binance",
        allowed_symbols=["BTC/USDT"],
        rest_factory=lambda _id, _cfg: _FlakyRestExchange(),
        ws_factory=lambda _id, _cfg: None,
    )
    assert client.supports_websocket is False
    with pytest.raises(MarketDataUnavailableError):
        await client.watch_ohlcv("BTC/USDT", timeframe="15m")
    await client.close()


def test_parse_ticker_payload_requires_verified_timestamp() -> None:
    from nexus.infrastructure.exchange.ccxt_client import parse_ticker_payload

    with pytest.raises(MarketDataUnavailableError, match="missing verified timestamp"):
        parse_ticker_payload(
            symbol="BTC/USDT",
            exchange_id="binance",
            raw={"bid": 90000.0, "ask": 90010.0, "last": 90005.0, "timestamp": None},
        )

    with pytest.raises(MarketDataUnavailableError, match="missing verified timestamp"):
        parse_ticker_payload(
            symbol="BTC/USDT",
            exchange_id="binance",
            raw={"bid": 90000.0, "ask": 90010.0, "last": 90005.0, "timestamp": -1},
        )
