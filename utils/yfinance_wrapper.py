#!/usr/bin/env python3
"""yfinance wrapper with AWS VPC compatibility and retry logic.

Handles 'Invalid Crumb' errors common in AWS Lambda/ECS environments.
"""
import time
import logging
from typing import Optional
import requests

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger(__name__)


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
                # Add headers to mimic browser request
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                logger.info(f"Created yfinance session (attempt {attempt + 1})")
                return session
            except Exception as e:
                logger.warning(f"Failed to create session (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

        return None

    @classmethod
    def get_ticker(cls, symbol: str, max_retries: int = 3):
        """Get yfinance Ticker with retry logic for Invalid Crumb errors."""
        if not yf:
            logger.error("yfinance not installed")
            return None

        for attempt in range(max_retries):
            try:
                session = cls.get_session()
                if session:
                    ticker = yf.Ticker(symbol, session=session)
                else:
                    ticker = yf.Ticker(symbol)

                # Try to access data to trigger auth error early
                _ = ticker.info
                logger.debug(f"Successfully created ticker for {symbol}")
                return ticker

            except Exception as e:
                error_str = str(e).lower()

                # Check for auth/crumb errors
                if 'invalid crumb' in error_str or '401' in error_str or 'unauthorized' in error_str:
                    logger.warning(f"Auth error for {symbol} (attempt {attempt + 1}): {e}")

                    # Reset session on auth error
                    cls._session = None
                    cls._last_session_time = 0

                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        logger.info(f"Retrying {symbol} in {wait_time}s...")
                        time.sleep(wait_time)
                    continue
                else:
                    # Other errors (data not available, etc.) - return None
                    logger.debug(f"Data not available for {symbol}: {e}")
                    return None

        logger.error(f"Failed to get ticker for {symbol} after {max_retries} attempts")
        return None


def get_ticker(symbol: str) -> Optional[object]:
    """Convenience function to get yfinance ticker with retry logic."""
    return YFinanceWrapper.get_ticker(symbol)
