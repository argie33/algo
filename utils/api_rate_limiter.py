#!/usr/bin/env python3
"""M5: Global API Rate Limiter for Concurrent Loaders

Prevents hammering external APIs when 40+ loaders run in parallel.
Uses token bucket algorithm with configurable refill rates per API.
"""

import time
import threading
from typing import Dict, Optional
from datetime import datetime

_LOGGER_NAME = "api_rate_limiter"
try:
    from utils.logging_setup import get_logger
    logger = get_logger(_LOGGER_NAME)
except ImportError:
    import logging
    logger = logging.getLogger(_LOGGER_NAME)


class RateLimiter:
    """Token bucket rate limiter for API calls.

    Default limits:
    - yfinance: 2 calls/sec (120/min) — standard API quota
    - alpaca: 1 call/sec (60/min) — paper trading API quota
    - sec-edgar: 10 calls/sec (unlimited, self-throttles)
    - finnhub: 1 call/sec (60/min) — free plan
    """

    def __init__(self, api_name: str, calls_per_second: float = 1.0):
        """Initialize rate limiter for an API.

        Args:
            api_name: Name of API (yfinance, alpaca, etc.)
            calls_per_second: Calls allowed per second
        """
        self.api_name = api_name
        self.calls_per_second = calls_per_second
        self.tokens = calls_per_second  # Start with full bucket
        self.last_refill = time.time()
        self.lock = threading.Lock()

    def wait_if_needed(self) -> float:
        """Wait if needed, then consume one token. Returns wait time in ms."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_refill
            # Refill tokens based on elapsed time
            self.tokens = min(
                self.calls_per_second,
                self.tokens + (elapsed * self.calls_per_second)
            )
            self.last_refill = now

            if self.tokens >= 1.0:
                # Token available, consume it
                self.tokens -= 1.0
                return 0.0
            else:
                # Wait for next token
                wait_time = (1.0 - self.tokens) / self.calls_per_second
                self.tokens = 0.0
                return wait_time

    def acquire(self) -> float:
        """Acquire permission to make API call. Blocks if needed.

        Returns: Time waited in seconds
        """
        wait_time_sec = self.wait_if_needed()
        if wait_time_sec > 0:
            time.sleep(wait_time_sec)
        return wait_time_sec


class GlobalRateLimiterPool:
    """Global singleton pool of rate limiters for all APIs."""

    _instance = None
    _lock = threading.Lock()

    # Default API rate limits (conservative for production)
    DEFAULT_LIMITS: Dict[str, float] = {
        'yfinance': 2.0,        # 2 calls/sec (120/min)
        'alpaca': 1.0,          # 1 call/sec (60/min)
        'sec-edgar': 10.0,      # 10 calls/sec (SEC is generous)
        'finnhub': 1.0,         # 1 call/sec (60/min free plan)
        'alpha-vantage': 0.5,   # 0.5 calls/sec (30/min free)
        'iex': 1.0,             # 1 call/sec (60/min)
        'default': 1.0,         # 1 call/sec fallback
    }

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._limiters: Dict[str, RateLimiter] = {}
        return cls._instance

    def get_limiter(self, api_name: str) -> RateLimiter:
        """Get or create rate limiter for an API."""
        with self._lock:
            if api_name not in self._limiters:
                limit = self.DEFAULT_LIMITS.get(api_name, self.DEFAULT_LIMITS['default'])
                self._limiters[api_name] = RateLimiter(api_name, limit)
                logger.debug(f"Created rate limiter for {api_name}: {limit:.1f} calls/sec")
            return self._limiters[api_name]

    def wait_for_api(self, api_name: str) -> float:
        """Convenience method: get limiter and wait if needed.

        Returns: Time waited in seconds
        """
        limiter = self.get_limiter(api_name)
        return limiter.acquire()


# Global instance for use by loaders
_pool = GlobalRateLimiterPool()


def wait_for_api(api_name: str) -> float:
    """M5: Global function for loaders to throttle API calls.

    Usage in loaders:
        from utils.api_rate_limiter import wait_for_api
        ...
        for symbol in symbols:
            wait_for_api('yfinance')  # Wait if needed
            data = yf.Ticker(symbol).info  # Now safe to call
    """
    return _pool.wait_for_api(api_name)


def set_rate_limit(api_name: str, calls_per_second: float) -> None:
    """Override default rate limit for an API.

    Usage:
        set_rate_limit('yfinance', 5.0)  # Allow 5 calls/sec instead of default 2
    """
    with _pool._lock:
        _pool._limiters[api_name] = RateLimiter(api_name, calls_per_second)
        logger.info(f"Set {api_name} rate limit to {calls_per_second:.1f} calls/sec")


# Test code moved to tests/unit/test_api_rate_limiter.py
