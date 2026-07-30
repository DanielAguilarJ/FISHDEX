"""
FishDex AI Server - Identification result cache
===============================================
Short-lived, in-process cache for completed identification results.

Motivation
----------
The mobile client polls ``GET /api/v1/jobs/{id}/result`` every two seconds while
it waits for a capture to finish, and keeps polling after completion while the
result screen is open. Each poll previously re-read the job row, the sighting
row, the previous catch and the matched reference catch, and re-parsed two JSON
columns. Caching the assembled document removes that repeated work.

Design
------
Thread-safe TTL cache with LRU eviction, using only the standard library. Entries
are invalidated explicitly whenever a job is re-processed, so a forced rerun never
serves a stale document.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TTLCache(Generic[T]):
    """
    A bounded, thread-safe cache whose entries expire after a fixed TTL.

    Attributes:
        ttl_seconds: Lifetime of each entry. Zero disables caching entirely.
        max_entries: Hard cap; the least recently used entry is evicted first.
    """

    def __init__(self, ttl_seconds: int, max_entries: int) -> None:
        """
        Initialise the cache.

        Args:
            ttl_seconds: Entry lifetime in seconds; 0 disables the cache.
            max_entries: Maximum number of retained entries.
        """
        self.ttl_seconds = max(0, ttl_seconds)
        self.max_entries = max(1, max_entries)
        self._entries: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @property
    def enabled(self) -> bool:
        """True when the cache will retain anything."""
        return self.ttl_seconds > 0

    def get(self, key: str) -> Optional[T]:
        """
        Look up a key.

        Args:
            key: Cache key.

        Returns:
            The cached value, or None when absent or expired.
        """
        if not self.enabled:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            expires_at, value = entry
            if expires_at <= now:
                del self._entries[key]
                self._misses += 1
                return None
            # Refresh recency for LRU ordering.
            self._entries.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: T) -> None:
        """
        Store a value, evicting the least recently used entry when full.

        Args:
            key: Cache key.
            value: Value to retain.
        """
        if not self.enabled:
            return
        expires_at = time.monotonic() + self.ttl_seconds
        with self._lock:
            self._entries[key] = (expires_at, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                evicted_key, _ = self._entries.popitem(last=False)
                logger.debug("Evicted cache entry %s (capacity)", evicted_key)

    def invalidate(self, key: str) -> None:
        """
        Drop a single entry.

        Args:
            key: Cache key to remove. Missing keys are ignored.
        """
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        """Drop every entry."""
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict[str, Any]:
        """
        Report cache effectiveness.

        Returns:
            Dict with ``entries``, ``hits``, ``misses`` and ``hit_rate``.
        """
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
                "ttl_seconds": self.ttl_seconds,
                "max_entries": self.max_entries,
            }


_result_cache: Optional[TTLCache[dict[str, Any]]] = None
_result_cache_lock = threading.Lock()


def get_result_cache() -> TTLCache[dict[str, Any]]:
    """
    Return the process-wide identification result cache.

    Returns:
        The shared :class:`TTLCache`, configured from settings on first use.
    """
    global _result_cache
    if _result_cache is None:
        with _result_cache_lock:
            if _result_cache is None:
                from app.config import settings

                ttl = (
                    settings.result_cache_ttl_seconds
                    if settings.result_cache_enabled
                    else 0
                )
                _result_cache = TTLCache(
                    ttl_seconds=ttl, max_entries=settings.result_cache_max_entries
                )
                logger.info(
                    "Identification result cache initialised (ttl=%ds, max=%d)",
                    ttl,
                    settings.result_cache_max_entries,
                )
    return _result_cache


def invalidate_job_result(job_id: str) -> None:
    """
    Invalidate the cached result for a job.

    Must be called whenever a job is (re)processed so a forced rerun cannot serve
    the previous document.

    Args:
        job_id: Job whose cached result should be dropped.
    """
    get_result_cache().invalidate(f"job_result:{job_id}")
