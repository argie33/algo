#!/usr/bin/env python3
"""
Retry and rate-limiting utilities for the algo data pipeline.

Usage — decorator:
    from algo_retry import retry, RateLimiter

    @retry(max_attempts=3, exceptions=(requests.HTTPError, ConnectionError))
    def fetch_price(symbol):
        return requests.get(f"https://api/price/{symbol}").json()

Usage — rate limiter (shared across threads):
    limiter = RateLimiter(calls_per_minute=200)   # Alpaca limit

    for symbol in symbols:
        limiter.wait()
        data = fetch_price(symbol)
"""

import functools
import logging
import random
import time
from typing import Callable, Tuple, Type

log = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """
    Exponential backoff retry decorator.

    Args:
        max_attempts: Total tries including the first. 3 = 1 try + 2 retries.
        base_delay:   Seconds to wait before first retry.
        max_delay:    Cap on sleep time regardless of backoff factor.
        backoff:      Multiplier applied to delay after each failure.
        jitter:       Add ±25% random spread to avoid thundering-herd.
        exceptions:   Only retry on these exception types.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        log.error(
                            "retry.exhausted fn=%s attempts=%d error=%s",
                            fn.__qualname__, max_attempts, exc,
                        )
                        raise
                    sleep = min(delay, max_delay)
                    if jitter:
                        sleep *= 0.75 + random.random() * 0.5
                    log.warning(
                        "retry.will_retry fn=%s attempt=%d/%d error=%s sleep=%.1fs",
                        fn.__qualname__, attempt, max_attempts, exc, sleep,
                    )
                    time.sleep(sleep)
                    delay *= backoff
        return wrapper
    return decorator


class RateLimiter:
    """
    Token-bucket rate limiter — thread-safe.

    Sleeps just enough so callers never exceed calls_per_minute.

    Example:
        limiter = RateLimiter(calls_per_minute=200)
        for symbol in symbols:
            limiter.wait()
            result = api.get(symbol)
    """

    def __init__(self, calls_per_minute: float):
        import threading
        self._min_interval = 60.0 / calls_per_minute
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.monotonic()


# ── Pre-built limiters for known providers ────────────────────────────────────
# Alpaca: 200 req/min data API, 10,000 req/min broker API
ALPACA_DATA_LIMITER = RateLimiter(calls_per_minute=180)   # 10% headroom

# Alpha Vantage free tier: 5 req/min, 500/day
ALPHA_VANTAGE_LIMITER = RateLimiter(calls_per_minute=4)   # 20% headroom

# Yahoo Finance: undocumented, ~2000/hr; be conservative
YFINANCE_LIMITER = RateLimiter(calls_per_minute=60)

# Generic conservative fallback
DEFAULT_LIMITER = RateLimiter(calls_per_minute=30)
