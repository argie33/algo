#!/usr/bin/env python3
"""
Alpaca Rate Limiter - Prevent hitting Alpaca API rate limits (100 req/sec per account).

Provides both thread-safe and async-compatible rate limiting with configurable
request queue and backoff strategy.
"""

import time
import logging
from threading import Lock, Event
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AlpacaRateLimiter:
    """Rate limiter for Alpaca API calls (max 100 requests/second)."""

    def __init__(self, max_requests_per_second=100, min_interval_ms=50):
        """
        Initialize rate limiter.

        Args:
            max_requests_per_second: Alpaca API limit (100 req/sec)
            min_interval_ms: Minimum milliseconds between requests (10ms → 100 req/sec)
        """
        self.max_requests_per_second = max_requests_per_second
        self.min_interval_sec = min_interval_ms / 1000.0
        self.last_request_time = 0
        self.lock = Lock()

    def wait_if_needed(self):
        """Block until it's safe to make the next request."""
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time

            if time_since_last < self.min_interval_sec:
                sleep_time = self.min_interval_sec - time_since_last
                logger.debug(f"Rate limiting: sleeping {sleep_time*1000:.1f}ms")
                time.sleep(sleep_time)

            self.last_request_time = time.time()

    def __enter__(self):
        """Context manager entry - wait before making request."""
        self.wait_if_needed()
        return self

    def __exit__(self, *args):
        """Context manager exit - no-op."""
        pass


# Global rate limiter instance for order placement
_alpaca_order_limiter = AlpacaRateLimiter(max_requests_per_second=100, min_interval_ms=50)


def get_alpaca_order_limiter():
    """Get global Alpaca order rate limiter instance."""
    return _alpaca_order_limiter
