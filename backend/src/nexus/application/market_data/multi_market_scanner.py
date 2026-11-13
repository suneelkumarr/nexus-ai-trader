"""High-throughput multi-market scanner monitoring 50+ spot markets and cross pairs."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from nexus.core.logging import get_logger
from nexus.domain.arbitrage import MarketSector, MarketTickerItem

logger = get_logger(__name__)

# Curated 115+ Binance spot & futures markets grouped by quantitative sector
SECTOR_MAPPING: dict[str, MarketSector] = {
    # Layer 1 & Major
    "BTC/USDT": "LAYER_1",
    "ETH/USDT": "LAYER_1",
    "SOL/USDT": "LAYER_1",
    "BNB/USDT": "LAYER_1",
    "ADA/USDT": "LAYER_1",
    "AVAX/USDT": "LAYER_1",
    "SUI/USDT": "LAYER_1",
    "NEAR/USDT": "LAYER_1",
    "APT/USDT": "LAYER_1",
    "DOT/USDT": "LAYER_1",
    "SEI/USDT": "LAYER_1",
    "ATOM/USDT": "LAYER_1",
    "ALGO/USDT": "LAYER_1",
    "FTM/USDT": "LAYER_1",
    "ETC/USDT": "LAYER_1",
    "TON/USDT": "LAYER_1",
    "KAVA/USDT": "LAYER_1",
    "EOS/USDT": "LAYER_1",
    "FLOW/USDT": "LAYER_1",
    "EGLD/USDT": "LAYER_1",
    "ROSE/USDT": "LAYER_1",
    "CFX/USDT": "LAYER_1",
    "ZEC/USDT": "LAYER_1",
    "DASH/USDT": "LAYER_1",
    "NEO/USDT": "LAYER_1",
    "IOTA/USDT": "LAYER_1",
    "VET/USDT": "LAYER_1",
    "HBAR/USDT": "LAYER_1",
    # DeFi
    "LINK/USDT": "DEFI",
    "UNI/USDT": "DEFI",
    "AAVE/USDT": "DEFI",
    "MKR/USDT": "DEFI",
    "CRV/USDT": "DEFI",
    "LDO/USDT": "DEFI",
    "PENDLE/USDT": "DEFI",
    "JUP/USDT": "DEFI",
    "ONDO/USDT": "DEFI",
    "INJ/USDT": "DEFI",
    "RUNE/USDT": "DEFI",
    "SNX/USDT": "DEFI",
    "DYDX/USDT": "DEFI",
    "COMP/USDT": "DEFI",
    "1INCH/USDT": "DEFI",
    "SUSHI/USDT": "DEFI",
    "CAKE/USDT": "DEFI",
    "ENA/USDT": "DEFI",
    "ETHFI/USDT": "DEFI",
    "GMX/USDT": "DEFI",
    "PYTH/USDT": "DEFI",
    "JTO/USDT": "DEFI",
    # AI & Decentralized Compute
    "FET/USDT": "AI_COMPUTE",
    "RENDER/USDT": "AI_COMPUTE",
    "TAO/USDT": "AI_COMPUTE",
    "ICP/USDT": "AI_COMPUTE",
    "THETA/USDT": "AI_COMPUTE",
    "FIL/USDT": "AI_COMPUTE",
    "TIA/USDT": "AI_COMPUTE",
    "WLD/USDT": "AI_COMPUTE",
    "AR/USDT": "AI_COMPUTE",
    "GRT/USDT": "AI_COMPUTE",
    "IO/USDT": "AI_COMPUTE",
    "VIRTUAL/USDT": "AI_COMPUTE",
    "AIXBT/USDT": "AI_COMPUTE",
    # High-Velocity Memes
    "DOGE/USDT": "MEMES",
    "SHIB/USDT": "MEMES",
    "PEPE/USDT": "MEMES",
    "WIF/USDT": "MEMES",
    "BONK/USDT": "MEMES",
    "FLOKI/USDT": "MEMES",
    "BOME/USDT": "MEMES",
    "MEME/USDT": "MEMES",
    "NOT/USDT": "MEMES",
    "NEIRO/USDT": "MEMES",
    "1000SATS/USDT": "MEMES",
    "TURBO/USDT": "MEMES",
    "PNUT/USDT": "MEMES",
    "ACT/USDT": "MEMES",
    "PENGU/USDT": "MEMES",
    # Infrastructure, Scaling & Payments
    "XRP/USDT": "INFRASTRUCTURE",
    "LTC/USDT": "INFRASTRUCTURE",
    "BCH/USDT": "INFRASTRUCTURE",
    "TRX/USDT": "INFRASTRUCTURE",
    "ARB/USDT": "INFRASTRUCTURE",
    "OP/USDT": "INFRASTRUCTURE",
    "STX/USDT": "INFRASTRUCTURE",
    "POL/USDT": "INFRASTRUCTURE",
    "IMX/USDT": "INFRASTRUCTURE",
    "MANTA/USDT": "INFRASTRUCTURE",
    "STRK/USDT": "INFRASTRUCTURE",
    "ZK/USDT": "INFRASTRUCTURE",
    "BLUR/USDT": "INFRASTRUCTURE",
    "ENS/USDT": "INFRASTRUCTURE",
    "DYM/USDT": "INFRASTRUCTURE",
    "MOVE/USDT": "INFRASTRUCTURE",
    "ME/USDT": "INFRASTRUCTURE",
    "XLM/USDT": "INFRASTRUCTURE",
    # Gaming & Metaverse
    "GALA/USDT": "GAMING_METAVERSE",
    "SAND/USDT": "GAMING_METAVERSE",
    "MANA/USDT": "GAMING_METAVERSE",
    "AXS/USDT": "GAMING_METAVERSE",
    "BEAM/USDT": "GAMING_METAVERSE",
    "PIXEL/USDT": "GAMING_METAVERSE",
    "RONIN/USDT": "GAMING_METAVERSE",
    "YGG/USDT": "GAMING_METAVERSE",
    "ILV/USDT": "GAMING_METAVERSE",
    "ENJ/USDT": "GAMING_METAVERSE",
    "CHZ/USDT": "GAMING_METAVERSE",
    "APE/USDT": "GAMING_METAVERSE",
    "GMT/USDT": "GAMING_METAVERSE",
    # Major Arbitrage Cross Pairs
    "ETH/BTC": "LAYER_1",
    "SOL/BTC": "LAYER_1",
    "BNB/BTC": "LAYER_1",
    "SOL/ETH": "LAYER_1",
}

DEFAULT_SCAN_UNIVERSE = list(SECTOR_MAPPING.keys())


class MultiMarketScanner:
    """Scans 50+ cryptocurrency markets concurrently with sub-second caching."""

    def __init__(
        self,
        symbols: list[str] | None = None,
        cache_ttl_seconds: float = 10.0,
    ) -> None:
        self._symbols = symbols or list(DEFAULT_SCAN_UNIVERSE)
        self._cache_ttl_s = cache_ttl_seconds
        self._last_fetch_ts: float = 0.0
        self._banned_until_monotonic: float = 0.0
        self._cached_tickers: dict[str, MarketTickerItem] = {}
        self._lock = asyncio.Lock()
        self._total_ticks_processed: int = 0
        self._exchange_client: Any | None = None

    def _get_exchange(self) -> Any:
        if self._exchange_client is None:
            import ccxt.async_support as ccxt

            self._exchange_client = ccxt.binance(
                {
                    "enableRateLimit": True,
                    "timeout": 10000,
                    "options": {"defaultType": "spot"},
                    "urls": {
                        "api": {
                            "public": "https://data-api.binance.vision/api/v3",
                        }
                    },
                }
            )
        return self._exchange_client

    async def close(self) -> None:
        """Release CCXT exchange connection."""
        if self._exchange_client is not None:
            await self._exchange_client.close()
            self._exchange_client = None

    @property
    def total_ticks_processed(self) -> int:
        return self._total_ticks_processed

    def _generate_fallback_tickers(self) -> dict[str, MarketTickerItem]:
        """Generate baseline quotes when remote exchange API is temporarily throttled."""
        utc_now = datetime.now(UTC)
        baseline_prices: dict[str, Decimal] = {
            "BTC/USDT": Decimal("68700.00"),
            "ETH/USDT": Decimal("1930.00"),
            "SOL/USDT": Decimal("84.50"),
            "BNB/USDT": Decimal("634.00"),
            "ETH/BTC": Decimal("0.0280"),
            "SOL/BTC": Decimal("0.00123"),
            "BNB/BTC": Decimal("0.0092"),
            "SOL/ETH": Decimal("0.0438"),
        }
        res: dict[str, MarketTickerItem] = {}
        for sym in self._symbols:
            base_p = baseline_prices.get(sym, Decimal("1.00"))
            res[sym] = MarketTickerItem(
                symbol=sym,
                bid=base_p * Decimal("0.9999"),
                ask=base_p * Decimal("1.0001"),
                last=base_p,
                spread_bps=Decimal("2.0"),
                change_24h_pct=Decimal("0.0"),
                quote_volume_24h=Decimal("1000000.0"),
                sector=SECTOR_MAPPING.get(sym, "LAYER_1"),
                timestamp=utc_now,
                is_stale=True,
            )
        self._cached_tickers = res
        return dict(res)

    async def scan_markets(self, force_refresh: bool = False) -> dict[str, MarketTickerItem]:
        """Fetch quotes for all 54 symbols using batch CCXT query."""
        now = time.monotonic()
        if now < self._banned_until_monotonic:
            if self._cached_tickers:
                return {
                    k: v.model_copy(update={"is_stale": True})
                    for k, v in self._cached_tickers.items()
                }
            return self._generate_fallback_tickers()

        is_fresh = (now - self._last_fetch_ts) < self._cache_ttl_s
        if not force_refresh and self._cached_tickers and is_fresh:
            return dict(self._cached_tickers)

        async with self._lock:
            now = time.monotonic()
            if now < self._banned_until_monotonic:
                if self._cached_tickers:
                    return {
                        k: v.model_copy(update={"is_stale": True})
                        for k, v in self._cached_tickers.items()
                    }
                return self._generate_fallback_tickers()

            is_fresh = (now - self._last_fetch_ts) < self._cache_ttl_s
            if not force_refresh and self._cached_tickers and is_fresh:
                return dict(self._cached_tickers)

            exchange = self._get_exchange()
            try:
                raw_tickers: dict[str, dict[str, Any]] = await exchange.fetch_tickers(self._symbols)
                parsed: dict[str, MarketTickerItem] = {}
                utc_now = datetime.now(UTC)

                for symbol in self._symbols:
                    data = raw_tickers.get(symbol)
                    if not data:
                        continue

                    bid_val = data.get("bid") or data.get("last") or 0.0
                    ask_val = data.get("ask") or data.get("last") or 0.0
                    last_val = data.get("last") or bid_val or 0.0

                    if bid_val <= 0 or ask_val <= 0 or last_val <= 0:
                        continue

                    bid_dec = Decimal(str(bid_val))
                    ask_dec = Decimal(str(ask_val))
                    last_dec = Decimal(str(last_val))

                    # Spread in basis points
                    mid = (bid_dec + ask_dec) / Decimal("2.0")
                    spread_calc = (ask_dec - bid_dec) / mid * Decimal("10000")
                    spread_bps = spread_calc.quantize(Decimal("0.01"))

                    pct_val = data.get("percentage") or 0.0
                    change_pct = Decimal(str(pct_val)).quantize(Decimal("0.01"))

                    vol_val = data.get("quoteVolume") or 0.0
                    quote_vol = Decimal(str(vol_val)).quantize(Decimal("0.01"))

                    sector = SECTOR_MAPPING.get(symbol, "LAYER_1")

                    item = MarketTickerItem(
                        symbol=symbol,
                        bid=bid_dec,
                        ask=ask_dec,
                        last=last_dec,
                        spread_bps=spread_bps,
                        change_24h_pct=change_pct,
                        quote_volume_24h=quote_vol,
                        sector=sector,
                        timestamp=utc_now,
                        is_stale=False,
                    )
                    parsed[symbol] = item

                if parsed:
                    self._cached_tickers = parsed
                    self._last_fetch_ts = now
                    self._total_ticks_processed += len(parsed)

                return dict(self._cached_tickers)

            except Exception as exc:
                err_str = str(exc)
                if "418" in err_str or "-1003" in err_str or "banned" in err_str.lower():
                    self._banned_until_monotonic = now + 60.0
                    logger.warning(
                        "binance_rate_limit_backoff_engaged",
                        error=err_str,
                        cooldown_s=60,
                    )
                else:
                    logger.warning("multi_market_scanner_fetch_failed", error=err_str)

                if self._cached_tickers:
                    stale_dict = {
                        k: MarketTickerItem(
                            symbol=v.symbol,
                            bid=v.bid,
                            ask=v.ask,
                            last=v.last,
                            spread_bps=v.spread_bps,
                            change_24h_pct=v.change_24h_pct,
                            quote_volume_24h=v.quote_volume_24h,
                            sector=v.sector,
                            timestamp=v.timestamp,
                            is_stale=True,
                        )
                        for k, v in self._cached_tickers.items()
                    }
                    return stale_dict
                return self._generate_fallback_tickers()
