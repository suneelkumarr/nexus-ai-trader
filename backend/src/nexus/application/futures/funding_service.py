"""Public funding rate telemetry service for USDT-M perpetual contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from nexus.core.logging import get_logger
from nexus.domain.futures import FundingRateInfo

logger = get_logger(__name__)

_BINANCE_FUTURES_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
_DEFAULT_FUNDING_RATE = Decimal("0.0001")  # +0.01% standard 8-hour rate


class FuturesFundingService:
    """Fetches public funding rates from Binance USDT-M Perpetuals without private credentials."""

    def __init__(self, cache_ttl_seconds: int = 30) -> None:
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: dict[str, FundingRateInfo] = {}
        self._last_fetched_all: datetime | None = None
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=8.0)
        return self._client

    @staticmethod
    def _normalize_to_fapi_symbol(symbol: str) -> str:
        """Convert 'BTC/USDT' or 'BTC/USDT:USDT' to 'BTCUSDT'."""
        cleaned = symbol.split(":")[0]
        return cleaned.replace("/", "").upper()

    @staticmethod
    def _normalize_from_fapi_symbol(fapi_sym: str) -> str:
        """Convert 'BTCUSDT' to 'BTC/USDT'."""
        if fapi_sym.endswith("USDT"):
            base = fapi_sym[:-4]
            return f"{base}/USDT"
        return fapi_sym

    async def fetch_funding_rates(
        self, symbols: list[str] | None = None
    ) -> dict[str, FundingRateInfo]:
        """Fetch latest funding rates for requested symbols or default universe."""
        now = datetime.now(UTC)
        is_cache_fresh = bool(
            self._last_fetched_all
            and (now - self._last_fetched_all) < self._cache_ttl
            and self._cache
        )
        if is_cache_fresh:
            if symbols:
                return {s: self._cache[s] for s in symbols if s in self._cache}
            return dict(self._cache)

        try:
            client = await self._get_client()
            resp = await client.get(_BINANCE_FUTURES_URL)
            if resp.status_code == 200:
                data: list[dict[str, Any]] = resp.json()
                for item in data:
                    fapi_sym = item.get("symbol", "")
                    std_sym = self._normalize_from_fapi_symbol(fapi_sym)
                    rate_raw = Decimal(str(item.get("lastFundingRate", "0.0001")))
                    mark_raw = Decimal(str(item.get("markPrice", "0")))
                    index_raw = Decimal(str(item.get("indexPrice", "0")))
                    funding_time_ms = item.get("nextFundingTime", 0)
                    next_time = (
                        datetime.fromtimestamp(funding_time_ms / 1000.0, tz=UTC)
                        if funding_time_ms
                        else now + timedelta(hours=8)
                    )

                    info = FundingRateInfo(
                        symbol=std_sym,
                        funding_rate=rate_raw,
                        funding_rate_pct=rate_raw * Decimal("100"),
                        mark_price=mark_raw,
                        index_price=index_raw,
                        funding_time=now,
                        next_funding_time=next_time,
                    )
                    self._cache[std_sym] = info

                self._last_fetched_all = now
            else:
                logger.warning(
                    "futures_funding_fetch_non_200",
                    status_code=resp.status_code,
                    body=resp.text[:200],
                )
        except Exception as exc:
            logger.warning("futures_funding_fetch_failed", error=str(exc))
            # Populate fallback if empty
            if not self._cache and symbols:
                for sym in symbols:
                    self._cache[sym] = FundingRateInfo(
                        symbol=sym,
                        funding_rate=_DEFAULT_FUNDING_RATE,
                        funding_rate_pct=_DEFAULT_FUNDING_RATE * Decimal("100"),
                        mark_price=Decimal("100.0"),
                        index_price=Decimal("100.0"),
                        funding_time=now,
                        next_funding_time=now + timedelta(hours=4),
                    )

        if symbols:
            result: dict[str, FundingRateInfo] = {}
            for sym in symbols:
                if sym in self._cache:
                    result[sym] = self._cache[sym]
                else:
                    result[sym] = FundingRateInfo(
                        symbol=sym,
                        funding_rate=_DEFAULT_FUNDING_RATE,
                        funding_rate_pct=_DEFAULT_FUNDING_RATE * Decimal("100"),
                        mark_price=Decimal("100.0"),
                        index_price=Decimal("100.0"),
                        funding_time=now,
                        next_funding_time=now + timedelta(hours=4),
                    )
            return result

        return dict(self._cache)

    async def get_funding_rate(self, symbol: str) -> FundingRateInfo:
        """Fetch funding rate for a single symbol."""
        rates = await self.fetch_funding_rates([symbol])
        return rates[symbol]

    async def close(self) -> None:
        """Gracefully close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
