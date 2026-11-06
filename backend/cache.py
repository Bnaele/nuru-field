"""In-process TTL cache for upstream data sources.

Why this exists
---------------
The hackathon build had no cache at all, and called the weather provider twice
per field selection: once from /api/field-profile and again from inside /api/crops,
each of which issued eleven sequential requests (one live plus ten historical).
A single map click therefore produced roughly 22 upstream calls, burning quota
and adding seconds of latency.

This module caches by rounded coordinate, so a grower moving the pin a few metres
or switching between the field view and the crops view reuses one result.

The cache is deliberately in-process and per-worker: it is enough to protect free
tiers, and it costs nothing to operate. If the app ever runs many workers, swap
the store for Redis without touching call sites.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Hashable

# Keep memory bounded; this is a cache, not a database.
MAX_ENTRIES = 512

# 3 decimal places is about 110 m, which is well below the resolution of every
# source we query (weather grids run to ~1-11 km, SoilGrids is 250 m).
COORD_PRECISION = 3


def coord_key(latitude: float, longitude: float) -> str:
    """Stable cache key for a coordinate pair, rounded to ~110 m."""
    return f"{round(latitude, COORD_PRECISION)},{round(longitude, COORD_PRECISION)}"


class TTLCache:
    def __init__(self, max_entries: int = MAX_ENTRIES) -> None:
        self._store: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._locks: dict[Hashable, asyncio.Lock] = {}
        self._max_entries = max_entries
        self.hits = 0
        self.misses = 0

    def _get(self, key: Hashable, now: float) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= now:
            self._store.pop(key, None)
            return None
        # Refresh recency for LRU eviction.
        self._store.move_to_end(key)
        return value

    def get(self, key: Hashable) -> Any | None:
        """Return a cached value, or None when absent or expired."""
        value = self._get(key, time.monotonic())
        if value is None:
            self.misses += 1
        else:
            self.hits += 1
        return value

    def peek(self, key: Hashable) -> Any | None:
        """Return a cached value without affecting hit/miss counters."""
        return self._get(key, time.monotonic())

    def set(self, key: Hashable, value: Any, ttl: float) -> None:
        self._store[key] = (time.monotonic() + ttl, value)
        self._store.move_to_end(key)
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        return len(self._store)


class Served:
    """Wrap a cached payload so responses can state where the data came from."""

    __slots__ = ("value", "cached")

    def __init__(self, value: Any, cached: bool) -> None:
        self.value = value
        self.cached = cached


async def cached_call(
    cache: TTLCache,
    *,
    namespace: str,
    key: Hashable,
    ttl: float,
    producer: Callable[[], Awaitable[Any]],
) -> Served:
    """Return a cached value, or compute it once.

    Concurrent callers for the same key share a single upstream request rather
    than stampeding it, which matters because the dashboard fires several
    requests at once when a field is chosen.
    """
    full_key = (namespace, key)
    hit = cache.peek(full_key)
    if hit is not None:
        return Served(hit, cached=True)

    lock = cache._locks.setdefault(full_key, asyncio.Lock())
    async with lock:
        # Another coroutine may have filled it while we waited.
        hit = cache.peek(full_key)
        if hit is not None:
            return Served(hit, cached=True)

        value = await producer()
        cache.set(full_key, value, ttl)
        return Served(value, cached=False)


# Shared instances, imported by the source modules.
weather_cache = TTLCache()
soil_cache = TTLCache()
geo_cache = TTLCache()
market_cache = TTLCache()
