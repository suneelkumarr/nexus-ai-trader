"""Deterministic TTL + LRU cache for validated AI market analyses."""

import asyncio
import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from nexus.domain.models import MarketAnalysisInput, MarketAnalysisOutput


@dataclass
class _CacheEntry:
    output: MarketAnalysisOutput
    expires_at: datetime


class AnalysisCache:
    """Thread/async-safe bounded LRU+TTL cache keyed on canonical input features."""

    def __init__(self, *, ttl_seconds: int = 300, max_entries: int = 256) -> None:
        self._ttl = timedelta(seconds=max(0, ttl_seconds))
        self._max_entries = max(1, max_entries)
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def build_key(analysis_input: MarketAnalysisInput, *, model_tag: str) -> str:
        """Compute deterministic SHA-256 digest over canonical validated features."""
        payload = {
            "model_tag": model_tag,
            "input": analysis_input.model_dump(mode="json"),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def get(
        self, key: str, *, now_utc: datetime | None = None
    ) -> MarketAnalysisOutput | None:
        """Return cached validated output if present and unexpired."""
        if self._ttl.total_seconds() <= 0:
            async with self._lock:
                self._misses += 1
            return None

        now = (now_utc or datetime.now(UTC)).astimezone(UTC)
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if now >= entry.expires_at:
                del self._store[key]
                self._misses += 1
                return None
            self._store.move_to_end(key)
            self._hits += 1
            return entry.output

    async def set(
        self,
        key: str,
        output: MarketAnalysisOutput,
        *,
        now_utc: datetime | None = None,
    ) -> None:
        """Insert validated analysis output into bounded LRU cache."""
        if self._ttl.total_seconds() <= 0:
            return

        now = (now_utc or datetime.now(UTC)).astimezone(UTC)
        async with self._lock:
            self._store[key] = _CacheEntry(output=output, expires_at=now + self._ttl)
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    async def clear(self) -> None:
        """Purge all cached analyses."""
        async with self._lock:
            self._store.clear()

    @property
    def stats(self) -> dict[str, int]:
        """Return cache utilization counters for diagnostics."""
        return {
            "hits": self._hits,
            "misses": self._misses,
            "entries": len(self._store),
        }
