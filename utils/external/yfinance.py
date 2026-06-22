#!/usr/bin/env python3
"""yfinance wrapper with AWS VPC compatibility and shared IP circuit breaker.

Handles 'Invalid Crumb' errors common in AWS Lambda/ECS environments.

Rate limiting: 6 ECS tasks share the same NAT IP when accessing yfinance. To prevent
IP bans from overwhelming other tasks, this wrapper:
1. Uses a SHARED circuit breaker (in PostgreSQL) to coordinate across all ECS tasks
2. When any task detects 429/401, ALL tasks respect an exponential backoff
3. Falls back to process-local throttling if PostgreSQL is unavailable
"""

import logging
import threading
import time
from typing import Any

import requests
import yfinance as yf

from utils.external.yfinance_circuit_breaker import get_circuit_breaker

logger = logging.getLogger(__name__)

# Global per-process rate limiter: enforces minimum interval between requests
# This is a BACKUP to the shared circuit breaker (DynamoDB-based).
# CRITICAL: Each ECS task runs one loader with parallelism=2-8, so this per-process
# limit applies to all symbols processed in parallel.
#
# OPTIMIZATION: Reduced from 2.0s to 1.0s to improve throughput while staying within
# yfinance's documented rate limits (2000 requests per hour = 1.8 req/sec max).
# Circuit breaker handles IP-level coordination if we exceed limits.
_yf_semaphore = threading.Semaphore(1)  # Max 1 concurrent request
_yf_rate_lock = threading.Lock()
_yf_last_request_time = [0.0]  # list for mutable access across threads
_YF_MIN_INTERVAL_SECS = 2.0  # CRITICAL FIX: 1 req/2s = ~1800 req/hour per task. 6 tasks = 10.8k/hour max. Stays under shared IP limits when combined with circuit breaker


def _throttled_yf_request(fn):
    """Call fn() under shared IP circuit breaker + local rate limiting.

    First checks if the shared IP is banned (from any ECS task). If banned,
    waits for the exponential backoff period. Then applies per-process throttling.
    """
    # Check shared IP ban state (coordinates across all ECS tasks)
    circuit_breaker = get_circuit_breaker()
    if circuit_breaker.is_banned():
        backoff = circuit_breaker.get_backoff_seconds()
        logger.warning(f"Shared IP banned across all ECS tasks. Waiting {backoff:.0f}s before retry...")
        time.sleep(backoff)

    # Apply per-process rate limiting (throttles this specific task)
    with _yf_semaphore:
        with _yf_rate_lock:
            elapsed = time.time() - _yf_last_request_time[0]
            if elapsed < _YF_MIN_INTERVAL_SECS:
                time.sleep(_YF_MIN_INTERVAL_SECS - elapsed)
            _yf_last_request_time[0] = time.time()
        return fn()


class YFinanceWrapper:
    """Wrapper for yfinance with AWS VPC compatibility."""

    _session = None
    _last_session_time: float = 0
    SESSION_TIMEOUT = 3600  # Refresh session every hour
    _ticker_cache: dict[str, Any] = {}  # Cache ticker objects to reduce API calls
    _ticker_cache_lock = threading.Lock()
    TICKER_CACHE_TTL = 86400  # CRITICAL FIX: Cache ticker objects for 24 hours (stable data) instead of 1 hour. Reduces yfinance API calls under rate limit stress

    @classmethod
    def get_session(cls):
        """Get or create a yfinance session with retries."""
        current_time = time.time()

        # Refresh session if expired
        if cls._session is None or (current_time - cls._last_session_time) > cls.SESSION_TIMEOUT:
            cls._session = cls._create_session()
            cls._last_session_time = current_time

        return cls._session

    @classmethod
    def _create_session(cls):
        """Create a new yfinance session with retries."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session = requests.Session()
                session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                logger.info(f"Created yfinance session (attempt {attempt + 1})")
                return session
            except (requests.RequestException, requests.Timeout) as e:
                logger.warning(f"Failed to create session (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)

        raise RuntimeError("Failed to create yfinance session after all retries")

    @classmethod
    def get_ticker(cls, symbol: str, max_retries: int = 5):
        """Get yfinance Ticker with retry logic, shared IP circuit breaker, and caching.

        Uses exponential backoff controlled by shared circuit breaker that coordinates
        across all ECS tasks (prevents IP ban cascades).

        Caches ticker objects for 1 hour to reduce API calls across parallel loaders.

        When 429/401 errors are detected:
        1. Report to shared circuit breaker (PostgreSQL)
        2. All ECS tasks automatically respect the exponential backoff
        3. Reduces per-task retries since the shared state handles coordination
        """
        if not yf:
            raise RuntimeError("yfinance not installed")

        # Check cache first (thread-safe)
        with cls._ticker_cache_lock:
            cached = cls._ticker_cache.get(symbol)
            if cached is not None:
                cached_ticker, cached_time = cached
                if time.time() - cached_time < cls.TICKER_CACHE_TTL:
                    logger.debug(f"Using cached ticker for {symbol}")
                    return cached_ticker

        import random

        circuit_breaker = get_circuit_breaker()

        for attempt in range(max_retries):
            try:

                def _make_ticker():
                    session = cls.get_session()
                    t = yf.Ticker(symbol, session=session) if session else yf.Ticker(symbol)
                    _ = t.info  # trigger auth check early
                    return t

                ticker = _throttled_yf_request(_make_ticker)
                logger.debug(f"Successfully created ticker for {symbol}")

                # Cache ticker object (thread-safe)
                with cls._ticker_cache_lock:
                    cls._ticker_cache[symbol] = (ticker, time.time())

                # Report success to shared circuit breaker (resets failure counter)
                circuit_breaker.report_success()
                return ticker

            except Exception as e:
                error_str = str(e).lower()

                is_rate_limit_error = (
                    "invalid crumb" in error_str
                    or "401" in error_str
                    or "429" in error_str
                    or "unauthorized" in error_str
                    or "too many requests" in error_str
                    or "rate" in error_str
                )

                if is_rate_limit_error:
                    logger.warning(f"Rate/auth error for {symbol} (attempt {attempt + 1}/{max_retries}): {e}")

                    # Report to shared circuit breaker (notifies all ECS tasks)
                    circuit_breaker.report_rate_limit_error()

                    # Reset session so next attempt gets a fresh crumb
                    cls._session = None
                    cls._last_session_time = 0

                    if attempt < max_retries - 1:
                        # Use shorter per-task backoff (shared circuit breaker handles IP-level coordination)
                        # Per-task backoff: 1s, 2s, 4s, 8s, 16s (quick per-symbol retries)
                        base_wait = 2**attempt
                        jitter = random.uniform(0, base_wait * 0.2)
                        wait_time = base_wait + jitter
                        logger.info(
                            f"Retrying {symbol} in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries}). "
                            f"Shared circuit breaker handling IP-level backoff."
                        )
                        time.sleep(wait_time)
                    else:
                        # Per-task retries exhausted. Circuit breaker continues managing IP-level backoff.
                        logger.warning(
                            f"[{symbol}] All per-task retries exhausted. "
                            f"Shared circuit breaker will manage IP recovery."
                        )
                    continue
                else:
                    logger.error(f"Failed to get ticker for {symbol}: {e}")
                    raise

        raise RuntimeError(f"Failed to get ticker for {symbol} after {max_retries} attempts")


def get_ticker(symbol: str):
    """Convenience function to get yfinance ticker with retry logic.

    Raises RuntimeError if yfinance is not installed, session creation fails,
    or all retry attempts are exhausted.
    """
    return YFinanceWrapper.get_ticker(symbol)
