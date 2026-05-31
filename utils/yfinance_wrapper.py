#!/usr/bin/env python3
"""yfinance wrapper with AWS VPC compatibility and retry logic.

Handles 'Invalid Crumb' errors common in AWS Lambda/ECS environments.

Rate limiting: All yfinance requests from this process share a global throttle
(max 2 concurrent, 500ms minimum between requests) to avoid Yahoo Finance banning
the shared NAT gateway IP used by all ECS tasks.
"""
import time
import threading
import logging
from typing import Optional
import requests

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger(__name__)

# Global per-process rate limiter: prevents >2 concurrent requests and enforces
# a minimum interval between consecutive requests. This reduces Yahoo Finance
# crumb invalidation when multiple threads share the same ECS task.
_yf_semaphore = threading.Semaphore(2)
_yf_rate_lock = threading.Lock()
_yf_last_request_time = [0.0]  # list for mutable access across threads
_YF_MIN_INTERVAL_SECS = 0.5    # 500ms between requests

# When Yahoo bans this process (all retries exhausted with 401), pause the
# entire process briefly so the shared IP can cool down before next attempt.
_yf_ban_lock = threading.Lock()
_yf_ban_until = [0.0]
_YF_BAN_COOLDOWN_SECS = 30  # pause 30s when Yahoo bans our IP


def _throttled_yf_request(fn):
    """Call fn() under global rate limiting (semaphore + min interval)."""
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
    _last_session_time = 0
    SESSION_TIMEOUT = 3600  # Refresh session every hour

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
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                logger.info(f"Created yfinance session (attempt {attempt + 1})")
                return session
            except Exception as e:
                logger.warning(f"Failed to create session (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

        return None

    @classmethod
    def get_ticker(cls, symbol: str, max_retries: int = 5):
        """Get yfinance Ticker with retry logic for Invalid Crumb/401 errors.

        Uses longer exponential backoff for 401 auth errors (2s, 4s, 8s, 16s, 32s).
        All requests go through the global rate limiter to stay within Yahoo's limits.
        """
        if not yf:
            logger.error("yfinance not installed")
            return None

        import random

        # Respect IP-level ban cooldown set by a previous exhausted caller
        ban_until = _yf_ban_until[0]
        if ban_until > time.time():
            wait = ban_until - time.time()
            logger.info(f"[{symbol}] Yahoo IP cooldown active, waiting {wait:.0f}s...")
            time.sleep(wait)

        for attempt in range(max_retries):
            try:
                def _make_ticker():
                    session = cls.get_session()
                    t = yf.Ticker(symbol, session=session) if session else yf.Ticker(symbol)
                    _ = t.info  # trigger auth check early
                    return t

                ticker = _throttled_yf_request(_make_ticker)
                logger.debug(f"Successfully created ticker for {symbol}")
                return ticker

            except Exception as e:
                error_str = str(e).lower()

                if 'invalid crumb' in error_str or '401' in error_str or 'unauthorized' in error_str or 'too many requests' in error_str:
                    logger.warning(f"Auth error for {symbol} (attempt {attempt + 1}): {e}")

                    # Reset session so next attempt gets a fresh crumb
                    cls._session = None
                    cls._last_session_time = 0

                    if attempt < max_retries - 1:
                        base_wait = 2 * (2 ** attempt)  # 2s, 4s, 8s, 16s, 32s
                        jitter = random.uniform(0, base_wait * 0.2)
                        wait_time = base_wait + jitter
                        logger.info(f"Retrying {symbol} in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                    else:
                        # All retries exhausted — set process-level ban cooldown so other
                        # threads back off and give Yahoo's per-IP limit time to reset.
                        with _yf_ban_lock:
                            _yf_ban_until[0] = time.time() + _YF_BAN_COOLDOWN_SECS
                        logger.warning(f"[{symbol}] All retries exhausted; setting {_YF_BAN_COOLDOWN_SECS}s IP cooldown")
                    continue
                else:
                    logger.debug(f"Data not available for {symbol}: {e}")
                    return None

        logger.error(f"Failed to get ticker for {symbol} after {max_retries} attempts")
        return None


def get_ticker(symbol: str) -> Optional[object]:
    """Convenience function to get yfinance ticker with retry logic."""
    return YFinanceWrapper.get_ticker(symbol)
