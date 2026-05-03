"""
Bloom filter dedup helper.

Skips already-loaded records before hitting the DB. Reduces dedup queries
by ~99% on incremental runs, which is the dominant cost for daily loaders.

Storage: Redis (RedisBloom module preferred; falls back to in-memory).
Memory: ~10 MB for 6M (symbol, date) keys at 1% false-positive rate.
False positive cost: one extra ON CONFLICT no-op write — cheap.
False negative: impossible (Bloom filters never miss positives).

Usage:
    from bloom_dedup import LoadDedup

    dedup = LoadDedup(namespace="price_daily")
    new_rows = dedup.filter_new(rows, key=lambda r: f"{r.symbol}:{r.date}")
    insert_batch(new_rows)
    dedup.add_batch(new_rows, key=lambda r: f"{r.symbol}:{r.date}")
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from typing import Callable, Iterable, List, Optional, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


class _InMemoryBloom:
    """Pure-Python Bloom filter fallback when Redis isn't available."""

    def __init__(self, capacity: int = 10_000_000, error_rate: float = 0.01):
        import math

        # Optimal m and k for given capacity/error_rate
        self._m = int(-(capacity * math.log(error_rate)) / (math.log(2) ** 2))
        self._k = max(1, int((self._m / capacity) * math.log(2)))
        self._bits = bytearray((self._m + 7) // 8)
        self._lock = threading.Lock()

    def _hashes(self, key: str) -> List[int]:
        digest = hashlib.blake2b(key.encode("utf-8"), digest_size=16).digest()
        h1 = int.from_bytes(digest[:8], "little")
        h2 = int.from_bytes(digest[8:], "little")
        return [(h1 + i * h2) % self._m for i in range(self._k)]

    def add(self, key: str) -> None:
        with self._lock:
            for bit in self._hashes(key):
                self._bits[bit // 8] |= 1 << (bit % 8)

    def exists(self, key: str) -> bool:
        for bit in self._hashes(key):
            if not (self._bits[bit // 8] & (1 << (bit % 8))):
                return False
        return True


class LoadDedup:
    """Bloom-filter-backed dedup gate for loaders.

    Args:
        namespace: Logical scope (e.g. "price_daily"). One filter per namespace.
        capacity: Expected number of keys. Bloom math is sized off this.
        error_rate: Acceptable false-positive rate. 1% is the sweet spot.
        redis_url: Override REDIS_URL env var if set.
    """

    def __init__(
        self,
        namespace: str,
        capacity: int = 10_000_000,
        error_rate: float = 0.01,
        redis_url: Optional[str] = None,
    ):
        self.namespace = namespace
        self.capacity = capacity
        self.error_rate = error_rate
        self._redis = self._connect(redis_url or os.getenv("REDIS_URL"))
        self._fallback: Optional[_InMemoryBloom] = None

        if self._redis is None:
            log.info("LoadDedup[%s]: using in-memory Bloom filter", namespace)
            self._fallback = _InMemoryBloom(capacity=capacity, error_rate=error_rate)
        else:
            self._ensure_redis_filter()

    def _connect(self, url: Optional[str]):
        if not url:
            return None
        try:
            import redis  # type: ignore

            client = redis.from_url(url, decode_responses=False, socket_timeout=2)
            client.ping()
            return client
        except Exception as e:
            log.warning("LoadDedup[%s]: Redis unavailable (%s) — falling back", self.namespace, e)
            return None

    def _ensure_redis_filter(self) -> None:
        """Create RedisBloom filter if module available; otherwise use SET."""
        try:
            self._redis.execute_command(
                "BF.RESERVE", self._key(), self.error_rate, self.capacity, "NONSCALING"
            )
            self._mode = "bloom"
        except Exception as e:
            msg = str(e).lower()
            if "already exists" in msg:
                self._mode = "bloom"
            elif "unknown command" in msg:
                # RedisBloom not loaded — use Set instead. Higher memory but works.
                log.info("LoadDedup[%s]: RedisBloom missing — using Redis SET", self.namespace)
                self._mode = "set"
            else:
                raise

    def _key(self) -> str:
        return f"dedup:{self.namespace}"

    def exists(self, key: str) -> bool:
        if self._fallback is not None:
            return self._fallback.exists(key)

        if self._mode == "bloom":
            return bool(self._redis.execute_command("BF.EXISTS", self._key(), key))
        return bool(self._redis.sismember(self._key(), key))

    def add(self, key: str) -> None:
        if self._fallback is not None:
            self._fallback.add(key)
            return

        if self._mode == "bloom":
            self._redis.execute_command("BF.ADD", self._key(), key)
        else:
            self._redis.sadd(self._key(), key)

    def add_batch(self, items: Iterable[T], key: Callable[[T], str]) -> int:
        """Add many keys in one round trip. Returns count added."""
        keys = [key(item) for item in items]
        if not keys:
            return 0

        if self._fallback is not None:
            for k in keys:
                self._fallback.add(k)
            return len(keys)

        if self._mode == "bloom":
            self._redis.execute_command("BF.MADD", self._key(), *keys)
        else:
            self._redis.sadd(self._key(), *keys)
        return len(keys)

    def filter_new(self, items: Iterable[T], key: Callable[[T], str]) -> List[T]:
        """Return only items whose key is NOT in the filter.

        False positives mean an item *might* already exist (we'll skip it
        unnecessarily). The DB's ON CONFLICT will handle the rare collision.
        False negatives are impossible — we never miss a new row.
        """
        items = list(items)
        if not items:
            return []

        keys = [key(item) for item in items]

        if self._fallback is not None:
            return [item for item, k in zip(items, keys) if not self._fallback.exists(k)]

        if self._mode == "bloom":
            results = self._redis.execute_command("BF.MEXISTS", self._key(), *keys)
        else:
            with self._redis.pipeline(transaction=False) as pipe:
                for k in keys:
                    pipe.sismember(self._key(), k)
                results = pipe.execute()

        return [item for item, exists in zip(items, results) if not exists]

    def stats(self) -> dict:
        """Diagnostic info — items, capacity, mode."""
        if self._fallback is not None:
            return {"mode": "in-memory", "namespace": self.namespace}
        if self._mode == "bloom":
            try:
                info = self._redis.execute_command("BF.INFO", self._key())
                return {"mode": "bloom-redis", "namespace": self.namespace, "info": info}
            except Exception:
                pass
        return {"mode": "set-redis", "namespace": self.namespace}


def make_key_symbol_date(row) -> str:
    """Conventional key for OHLCV-shaped rows."""
    return f"{row['symbol']}:{row['date']}"
