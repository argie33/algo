#!/usr/bin/env python3
"""
Retry and rate-limiting utilities for the algo data pipeline.

Usage — decorator:
    from algo.infrastructure import retry, RateLimiter

    @retry(max_attempts=3, exceptions=(requests.HTTPError, ConnectionError))
    def fetch_price(symbol):
        # SECURITY FIX: Use a valid HTTPS URL (this was: https://api/price/{symbol})
        return requests.get(f"https://api.example.com/price/{symbol}", timeout=get_api_timeout()).json()

Usage — rate limiter (shared across threads):
    limiter = RateLimiter(calls_per_minute=200)   # Alpaca limit

    for symbol in symbols:
        limiter.wait()
        data = fetch_price(symbol)
"""

import functools
import logging
import random
import requests
import time
from collections.abc import Callable

from algo.infrastructure.constants import (
    ALPACA_DATA_RATE_LIMIT_CPM,
    ALPHA_VANTAGE_RATE_LIMIT_CPM,
    DEFAULT_RATE_LIMIT_CPM,
    RETRY_BACKOFF_MULTIPLIER,
    RETRY_BASE_DELAY_SEC,
    RETRY_JITTER_MAX_FACTOR,
    RETRY_JITTER_MIN_FACTOR,
    RETRY_MAX_DELAY_SEC,
    YFINANCE_RATE_LIMIT_CPM,
)


logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    base_delay: float = RETRY_BASE_DELAY_SEC,
    max_delay: float = RETRY_MAX_DELAY_SEC,
    backoff: float = RETRY_BACKOFF_MULTIPLIER,
    jitter: bool = True,
    exceptions: tuple[type[Exception], ...] = (Exception,),
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
                        logger.error(
                            "retry.exhausted fn=%s attempts=%d error=%s",
                            fn.__qualname__,
                            max_attempts,
                            exc,
                        )
                        raise
                    sleep = min(delay, max_delay)
                    if jitter:
                        sleep *= RETRY_JITTER_MIN_FACTOR + random.random() * (
                            RETRY_JITTER_MAX_FACTOR - RETRY_JITTER_MIN_FACTOR
                        )
                    logger.warning(
                        "retry.will_retry fn=%s attempt=%d/%d error=%s sleep=%.1fs",
                        fn.__qualname__,
                        attempt,
                        max_attempts,
                        exc,
                        sleep,
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
# See algo.infrastructure.constants for CPM values and rationale
ALPACA_DATA_LIMITER = RateLimiter(calls_per_minute=ALPACA_DATA_RATE_LIMIT_CPM)
ALPHA_VANTAGE_LIMITER = RateLimiter(calls_per_minute=ALPHA_VANTAGE_RATE_LIMIT_CPM)
YFINANCE_LIMITER = RateLimiter(calls_per_minute=YFINANCE_RATE_LIMIT_CPM)
DEFAULT_LIMITER = RateLimiter(calls_per_minute=DEFAULT_RATE_LIMIT_CPM)
