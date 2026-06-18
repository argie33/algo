#!/usr/bin/env python3
"""
Query Result Caching Layer - Reduces Database Load and API Calls

Currently only credentials are cached. This module provides a general-purpose
caching system for expensive queries and API calls.

CACHING STRATEGY:

1. In-Process Cache (RAM):
   - Fast: no serialization overhead
   - Limited: only for current process (not shared across Lambda invocations)
   - TTL-based: configurable per-query-type
   - Best for: frequently-accessed, slow-to-compute values

2. Database-Based Cache (if needed in future):
   - Shared: accessible from multiple processes/Lambda invocations
   - Slower: requires DB round-trip
   - Permanent: survives process restart
   - Best for: expensive computations needed across invocations

CURRENT SCOPE:
- Technical indicators (SMA, EMA, RSI, ATR) - expensive to compute
- Market aggregates (breadth, up/down volume) - queried many times per page load
- Company fundamentals (PE ratio, market cap) - rarely changes, high query cost
- Sector rankings - updated daily, queried often
- Earnings dates - static until earnings announcement

CACHE INVALIDATION:
- Time-based: TTL expiration (e.g., 60 seconds for market data)
- Event-based: manual invalidation on data update
- Dependency-based: invalidate related caches when source changes

METRICS TRACKED:
- cache_hits: successful cache lookups
- cache_misses: cache misses (forced recompute/refetch)
- cache_stale: hits on expired entries (fallback used)
- evictions: entries removed due to size/TTL

MONITORING:
All cache operations should track hit rates. Low hit rates indicate:
- TTL too short (invalidating too often)
- Key patterns not matching (queries using different parameters)
- Cache too small (entries evicted before reuse)
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Generic, Optional, Tuple, TypeVar


logger = logging.getLogger(__name__)

T = TypeVar("T")


class CacheStrategy(Enum):
    """When to invalidate cache entries."""

    TIME_BASED = "ttl"  # Expire after N seconds
    ON_DEMAND = "manual"  # Never expire, invalidate manually
    LRU = "lru"  # Evict least-recently-used when full


@dataclass
class CacheStats:
    """Cache performance statistics."""

    hits: int = 0
    misses: int = 0
    stale_hits: int = 0
    evictions: int = 0
    avg_hit_time_ms: float = 0.0
    avg_miss_time_ms: float = 0.0

    def hit_rate(self) -> float:
        """Percentage of lookups that hit cache."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0


class QueryCache(Generic[T]):
    """In-process cache for expensive queries/computations.

    Features:
    - TTL-based expiration
    - Automatic metrics tracking
    - Context-aware logging
    - Automatic stale-entry fallback

    Usage:
        cache = QueryCache('technical_indicators', ttl_seconds=300)

        # First call - computes and caches
        result = cache.get_or_compute(
            key=('AAPL', 'SMA50'),
            compute_fn=lambda: expensive_sma_calculation('AAPL', 50),
            context="computing SMA50 for AAPL"
        )

        # Second call within 300s - returns cached value
        result = cache.get_or_compute(
            key=('AAPL', 'SMA50'),
            compute_fn=lambda: expensive_sma_calculation('AAPL', 50),
        )
    """

    def __init__(
        self,
        cache_name: str,
        ttl_seconds: int = 300,
        max_entries: int = 10000,
        strategy: CacheStrategy = CacheStrategy.TIME_BASED,
    ):
        """Initialize cache.

        Args:
            cache_name: Name for logging (e.g., 'technical_indicators')
            ttl_seconds: Time-to-live for entries (seconds)
            max_entries: Maximum cache size before LRU eviction
            strategy: Invalidation strategy (TIME_BASED, ON_DEMAND, LRU)
        """
        self.cache_name = cache_name
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.strategy = strategy

        self._cache: Dict[Any, Tuple[T, float]] = {}  # key -> (value, timestamp)
        self._access_order: Dict[Any, float] = {}  # key -> last_access_time (for LRU)
        self._stats = CacheStats()

    def get_or_compute(
        self,
        key: Any,
        compute_fn: Callable[[], T],
        context: str = "",
        allow_stale: bool = False,
    ) -> T:
        """Get value from cache or compute if missing/expired.

        Args:
            key: Cache key (usually tuple of parameters)
            compute_fn: Function to call if cache miss
            context: Context for logging (e.g., "AAPL price")
            allow_stale: If True, return stale entry on compute error

        Returns:
            Cached or freshly-computed value
        """
        t0 = time.time()

        # Check if in cache and not expired
        if key in self._cache:
            value, timestamp = self._cache[key]
            age = time.time() - timestamp

            if age <= self.ttl_seconds:
                # Cache hit
                self._stats.hits += 1
                elapsed_ms = (time.time() - t0) * 1000
                self._stats.avg_hit_time_ms = (
                    self._stats.avg_hit_time_ms * 0.9 + elapsed_ms * 0.1
                )
                logger.debug(f"[{self.cache_name}] HIT: {key} {context}")
                self._access_order[key] = time.time()  # Update LRU
                return value
            else:
                # Cache expired
                if allow_stale:
                    # Return stale entry and log warning
                    logger.warning(
                        f"[{self.cache_name}] STALE HIT: {key} age={age:.0f}s ttl={self.ttl_seconds}s {context}"
                    )
                    self._stats.stale_hits += 1
                    self._access_order[key] = time.time()
                    return value
                else:
                    # Remove expired entry
                    del self._cache[key]
                    del self._access_order[key]

        # Cache miss - compute value
        try:
            t1 = time.time()
            value = compute_fn()
            elapsed_ms = (time.time() - t1) * 1000

            self._stats.misses += 1
            self._stats.avg_miss_time_ms = (
                self._stats.avg_miss_time_ms * 0.9 + elapsed_ms * 0.1
            )

            # Store in cache
            self._cache[key] = (value, time.time())
            self._access_order[key] = time.time()

            # Evict old entries if over capacity
            if (
                len(self._cache) > self.max_entries
                and self.strategy == CacheStrategy.LRU
            ):
                self._evict_lru()

            logger.debug(
                f"[{self.cache_name}] MISS+COMPUTE: {key} "
                f"compute_time={elapsed_ms:.0f}ms {context}"
            )
            return value

        except Exception as e:
            logger.error(f"[{self.cache_name}] Compute failed for {key}: {e} {context}")
            if allow_stale and key in self._cache:
                # Return stale entry as fallback
                logger.warning(f"[{self.cache_name}] Returning stale entry for {key}")
                self._stats.stale_hits += 1
                return self._cache[key][0]
            raise

    def invalidate(self, key: Optional[Any] = None) -> None:
        """Invalidate cache entry or entire cache.

        Args:
            key: Specific key to invalidate, or None to clear all
        """
        if key is None:
            self._cache.clear()
            self._access_order.clear()
            logger.info(f"[{self.cache_name}] Cleared all {self.cache_name} cache")
        else:
            if key in self._cache:
                del self._cache[key]
                del self._access_order[key]
                logger.debug(f"[{self.cache_name}] Invalidated {key}")

    def _evict_lru(self) -> None:
        """Remove least-recently-used entry."""
        if not self._access_order:
            return

        # Find oldest access time
        lru_key = min(self._access_order, key=self._access_order.get)  # type: ignore[arg-type]
        del self._cache[lru_key]
        del self._access_order[lru_key]
        self._stats.evictions += 1
        logger.debug(f"[{self.cache_name}] LRU eviction: {lru_key}")

    def stats(self) -> CacheStats:
        """Get cache performance statistics."""
        stats = CacheStats(
            hits=self._stats.hits,
            misses=self._stats.misses,
            stale_hits=self._stats.stale_hits,
            evictions=self._stats.evictions,
            avg_hit_time_ms=self._stats.avg_hit_time_ms,
            avg_miss_time_ms=self._stats.avg_miss_time_ms,
        )
        return stats

    def report_stats(self) -> str:
        """Get human-readable statistics."""
        stats = self.stats()
        return (
            f"[{self.cache_name}] "
            f"hits={stats.hits} "
            f"misses={stats.misses} "
            f"stale={stats.stale_hits} "
            f"hit_rate={stats.hit_rate():.1f}% "
            f"size={len(self._cache)} "
            f"avg_hit={stats.avg_hit_time_ms:.1f}ms "
            f"avg_miss={stats.avg_miss_time_ms:.1f}ms"
        )


# Global cache instances - one per expensive query type
_GLOBAL_CACHES: Dict[str, QueryCache] = {}


def get_or_create_cache(
    cache_name: str,
    ttl_seconds: int = 300,
    max_entries: int = 10000,
) -> QueryCache:
    """Get or create global cache instance.

    Useful for caches that should persist across function calls
    within a Lambda warm invocation.

    Args:
        cache_name: Cache identifier (e.g., 'technical_indicators')
        ttl_seconds: Time-to-live for entries
        max_entries: Maximum cache size

    Returns:
        QueryCache instance
    """
    if cache_name not in _GLOBAL_CACHES:
        _GLOBAL_CACHES[cache_name] = QueryCache(cache_name, ttl_seconds, max_entries)
    return _GLOBAL_CACHES[cache_name]


def report_all_caches() -> str:
    """Get statistics for all active caches."""
    if not _GLOBAL_CACHES:
        return "[CACHE] No active caches"

    reports = [f"[CACHE] Statistics for {len(_GLOBAL_CACHES)} active caches:"]
    for cache in _GLOBAL_CACHES.values():
        reports.append("  " + cache.report_stats())
    return "\n".join(reports)


if __name__ == "__main__":
    # Example usage
    print("Query Cache Example")

    cache: QueryCache[int] = QueryCache("test_cache", ttl_seconds=5, max_entries=100)

    def expensive_computation(x: int) -> int:
        print(f"  [EXPENSIVE] Computing {x}^2...")
        time.sleep(0.1)
        return x * x

    print("\n1. First call (cache miss)")
    result = cache.get_or_compute(("test", 5), lambda: expensive_computation(5))
    print(f"   Result: {result}, {cache.report_stats()}")

    print("\n2. Second call (cache hit)")
    result = cache.get_or_compute(("test", 5), lambda: expensive_computation(5))
    print(f"   Result: {result}, {cache.report_stats()}")

    print("\n3. Different key (cache miss)")
    result = cache.get_or_compute(("test", 10), lambda: expensive_computation(10))
    print(f"   Result: {result}, {cache.report_stats()}")

    print("\n4. Wait for TTL expiration...")
    time.sleep(6)
    result = cache.get_or_compute(("test", 5), lambda: expensive_computation(5))
    print(f"   Result: {result}, {cache.report_stats()}")
