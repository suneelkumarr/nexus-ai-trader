"""Compatibility wrapper exposing MarketDataProvider via CCXTPublicExchangeClient."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx

from nexus.domain.models import OHLCVBar, TickerQuote
from nexus.infrastructure.exchange.ccxt_client import CCXTPublicExchangeClient


class CCXTMarketDataProvider(CCXTPublicExchangeClient):
    """Public spot MarketDataProvider backed by CCXTPublicExchangeClient."""

    def __init__(
        self,
        *,
        exchange_id: str,
        allowed_symbols: list[str],
        supported_timeframes: list[str] | None = None,
        timeout_ms: int = 10000,
        max_retries: int = 3,
        backoff_base_s: float = 0.5,
        exchange_factory: Callable[[str, dict[str, Any]], Any] | None = None,
        ws_factory: Callable[[str, dict[str, Any]], Any] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            exchange_id=exchange_id,
            allowed_symbols=allowed_symbols,
            supported_timeframes=supported_timeframes,
            timeout_ms=timeout_ms,
            max_retries=max_retries,
            backoff_base_s=backoff_base_s,
            rest_factory=exchange_factory,
            ws_factory=ws_factory,
            http_client=http_client,
        )

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        since_ms: int | None = None,
        limit: int = 100,
    ) -> list[OHLCVBar]:
        """Fetch public spot OHLCV bars in UTC."""
        return await super().fetch_ohlcv(
            symbol=symbol, timeframe=timeframe, since_ms=since_ms, limit=limit
        )

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        """Fetch public spot ticker quote."""
        return await super().fetch_ticker(symbol)

    async def fetch_inr_per_usdt(self) -> Decimal:
        """Fetch live INR per 1 USDT rate."""
        return await super().fetch_inr_per_usdt()
