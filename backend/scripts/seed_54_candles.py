"""Batch script to seed closed 15m OHLCV candles from Binance public REST into PostgreSQL."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from nexus.application.market_data.multi_market_scanner import SECTOR_MAPPING
from nexus.core.config import get_settings
from nexus.core.logging import get_logger
from nexus.domain.models import OHLCVBar
from nexus.infrastructure.db.candle_repository import SqlAlchemyCandleRepository
from nexus.infrastructure.db.session import DatabaseManager

logger = get_logger("seed_54_candles")

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


async def fetch_binance_klines(
    client: httpx.AsyncClient, symbol: str, timeframe: str = "15m", limit: int = 120
) -> list[OHLCVBar]:
    """Fetch closed klines directly from Binance public API."""
    formatted_symbol = symbol.replace("/", "")
    params = {
        "symbol": formatted_symbol,
        "interval": timeframe,
        "limit": limit,
    }
    resp = await client.get(BINANCE_KLINES_URL, params=params, timeout=10.0)
    if resp.status_code != 200:
        logger.warning(
            "seed_klines_failed",
            symbol=symbol,
            status=resp.status_code,
            body=resp.text[:100],
        )
        return []

    raw = resp.json()
    if not isinstance(raw, list):
        return []

    bars: list[OHLCVBar] = []
    # Drop the last candle as it may still be forming/open
    closed_rows = raw[:-1] if len(raw) > 1 else raw

    for r in closed_rows:
        try:
            ts_ms = int(r[0])
            open_p = Decimal(str(r[1]))
            high_p = Decimal(str(r[2]))
            low_p = Decimal(str(r[3]))
            close_p = Decimal(str(r[4]))
            volume = Decimal(str(r[5]))
            bar_ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)

            bars.append(
                OHLCVBar(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=bar_ts,
                    open=open_p,
                    high=high_p,
                    low=low_p,
                    close=close_p,
                    volume=volume,
                    is_closed=True,
                )
            )
        except Exception:
            continue

    return bars


async def main() -> None:
    settings = get_settings()
    db = DatabaseManager(settings)
    repo = SqlAlchemyCandleRepository(db.session_factory)

    symbols = list(SECTOR_MAPPING.keys())
    print(f"[*] Starting candle sync for {len(symbols)} spot pairs (15m timeframe)...")

    success_count = 0
    total_bars_inserted = 0

    async with httpx.AsyncClient(headers={"User-Agent": "NexusAI/1.0"}) as client:
        # Run in small concurrency batches of 5 to respect Binance public IP limits
        batch_size = 5
        for i in range(0, len(symbols), batch_size):
            chunk = symbols[i : i + batch_size]
            tasks = [fetch_binance_klines(client, sym, "15m", 120) for sym in chunk]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for sym, res in zip(chunk, results, strict=False):
                if isinstance(res, list) and res:
                    inserted = await repo.upsert_candles(settings.exchange_id, res)
                    total_bars_inserted += inserted
                    success_count += 1
                    print(f"  [+] {sym:<10} synced {len(res)} bars into PostgreSQL.")
                else:
                    print(f"  [-] {sym:<10} failed or empty: {res}")

            await asyncio.sleep(0.3)

    print(
        f"[*] Completed! Successfully seeded {success_count}/{len(symbols)} pairs. "
        f"Total bars upserted: {total_bars_inserted}."
    )
    await db.dispose()


if __name__ == "__main__":
    asyncio.run(main())

