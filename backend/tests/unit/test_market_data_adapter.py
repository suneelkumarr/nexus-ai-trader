"""Unit tests for CCXTMarketDataProvider ensuring real validation and zero fake data."""

from decimal import Decimal
from typing import Any

import httpx
import pytest

from nexus.core.exceptions import MarketDataUnavailableError, RiskViolationError
from nexus.infrastructure.exchange.ccxt_market_data import CCXTMarketDataProvider


class _StubExchange:
    def __init__(
        self,
        ticker_payload: Any = None,
        ohlcv_payload: Any = None,
        raise_on_fetch: Exception | None = None,
        time_ok: bool = True,
    ) -> None:
        self._ticker_payload = ticker_payload
        self._ohlcv_payload = ohlcv_payload
        self._raise_on_fetch = raise_on_fetch
        self._time_ok = time_ok
        self.closed = False

    async def fetch_ticker(self, symbol: str) -> Any:
        if self._raise_on_fetch is not None:
            raise self._raise_on_fetch
        return self._ticker_payload

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "15m", limit: int = 100) -> Any:
        if self._raise_on_fetch is not None:
            raise self._raise_on_fetch
        return self._ohlcv_payload

    async def fetch_time(self) -> int:
        if not self._time_ok:
            raise RuntimeError("Exchange unreachable")
        return 1700000000000

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_ccxt_adapter_enforces_spot_config_and_parses_real_ticker() -> None:
    captured_config: dict[str, Any] = {}

    def factory(_exchange_id: str, config: dict[str, Any]) -> _StubExchange:
        captured_config.update(config)
        return _StubExchange(
            ticker_payload={
                "bid": 90000.0,
                "ask": 90020.0,
                "last": 90010.0,
                "timestamp": 1700000000000,
            }
        )

    provider = CCXTMarketDataProvider(
        exchange_id="binance",
        allowed_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        exchange_factory=factory,
    )
    assert captured_config["options"]["defaultType"] == "spot"

    quote = await provider.fetch_ticker("BTC/USDT")
    assert quote.symbol == "BTC/USDT"
    assert quote.bid == Decimal("90000.0")
    assert quote.ask == Decimal("90020.0")
    await provider.close()


@pytest.mark.asyncio
async def test_ccxt_adapter_never_returns_fake_data_on_failure() -> None:
    provider = CCXTMarketDataProvider(
        exchange_id="binance",
        allowed_symbols=["BTC/USDT"],
        exchange_factory=lambda _id, _cfg: _StubExchange(
            raise_on_fetch=RuntimeError("Network timeout")
        ),
    )
    with pytest.raises(MarketDataUnavailableError):
        await provider.fetch_ticker("BTC/USDT")

    with pytest.raises(MarketDataUnavailableError):
        await provider.fetch_ohlcv("BTC/USDT")

    await provider.close()


@pytest.mark.asyncio
async def test_ccxt_adapter_rejects_empty_ohlcv_and_disallowed_symbol() -> None:
    provider = CCXTMarketDataProvider(
        exchange_id="binance",
        allowed_symbols=["BTC/USDT"],
        exchange_factory=lambda _id, _cfg: _StubExchange(ohlcv_payload=[]),
    )
    with pytest.raises(RiskViolationError):
        await provider.fetch_ticker("XRP/USDT")

    with pytest.raises(MarketDataUnavailableError):
        await provider.fetch_ohlcv("BTC/USDT")

    await provider.close()


@pytest.mark.asyncio
async def test_ccxt_adapter_fx_raises_without_hardcoded_fallback() -> None:
    transport = httpx.MockTransport(lambda _req: httpx.Response(503, json={"error": "down"}))
    async with httpx.AsyncClient(transport=transport) as client:
        provider = CCXTMarketDataProvider(
            exchange_id="binance",
            allowed_symbols=["BTC/USDT"],
            exchange_factory=lambda _id, _cfg: _StubExchange(
                raise_on_fetch=RuntimeError("No USDT/INR pair")
            ),
            http_client=client,
        )
        with pytest.raises(MarketDataUnavailableError):
            await provider.fetch_inr_per_usdt()
        await provider.close()

