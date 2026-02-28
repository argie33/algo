#!/usr/bin/env python3
"""
yfinance Helper Functions
Provides utilities for fetching ticker data with retry logic
"""

import logging
import time
from functools import wraps
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries=10, base_delay=0.5, verbose=True):
    """
    Retry decorator with exponential backoff for API calls - RESILIENT to HTTP 500 errors.

    Enhanced to handle yfinance HTTP 500 errors more effectively:
    - Increased max_retries from 4 to 10
    - Longer exponential backoff (0.5s, 1s, 2s, 4s, 8s, 16s, 32s, 64s, 120s, 120s)
    - Retries ALL transient errors (HTTP 500, 503, timeouts, connection errors)
    - Rate limit errors trigger main loop backoff
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()
                    # Retry on transient errors: HTTP 500, 503, timeouts, connection errors
                    is_transient = any(x in error_str for x in ['500', '503', 'timeout', 'connection', 'temporarily unavailable', 'remote end closed', 'http error'])
                    # Rate limit errors should trigger main loop backoff
                    is_rate_limit = any(x in error_str for x in ['rate limit', '429'])

                    if is_rate_limit:
                        # Log rate limit and fail - main loop will space requests
                        if verbose:
                            logging.warning(f"⚠️ RATE LIMITED on {func.__name__} (attempt {attempt + 1}/{max_retries}). Main loop will add spacing.")
                        raise  # Fail immediately so main loop can add delay before retry
                    elif is_transient:
                        # RESILIENT: Exponential backoff with longer delays (0.5, 1, 2, 4, 8, 16, 32, 64, 120, 120)
                        delay = base_delay * (2 ** attempt)
                        delay = min(delay, 120)  # Cap at 2 minutes for extreme cases

                        if attempt < max_retries - 1:
                            # Retry transient errors with exponential backoff
                            if verbose:
                                logging.warning(f"⚠️ Transient error in {func.__name__} (attempt {attempt + 1}/{max_retries}), retrying in {delay:.1f}s: {str(e)[:80]}")
                            time.sleep(delay)
                        else:
                            if verbose:
                                logging.error(f"❌ All {max_retries} retry attempts exhausted for {func.__name__}: {e}")
                            raise
                    else:
                        # Unknown error - log and fail
                        if verbose:
                            logging.error(f"Non-retriable error in {func.__name__}: {e}")
                        raise
        return wrapper
    return decorator


@retry_with_backoff(max_retries=3, base_delay=1)
def _fetch_from_yfinance(ticker, period, start, end, interval):
    """Internal function to fetch from yfinance with retry logic"""
    return yf.Ticker(ticker).history(
        period=period if period else None,
        start=start if start else None,
        end=end if end else None,
        interval=interval,
        progress=False
    )


def fetch_ticker_history(symbol, period='max', start=None, end=None, interval='1d',
                        max_retries=3, min_rows=1):
    """
    Fetch ticker history from yfinance with built-in retry and error handling.

    Args:
        symbol: Stock ticker symbol
        period: Period string (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        start: Start date (YYYY-MM-DD format)
        end: End date (YYYY-MM-DD format)
        interval: Data interval (1m, 5m, 15m, 30m, 60m, 1d, 1wk, 1mo)
        max_retries: Number of retries
        min_rows: Minimum rows required (return None if fewer)

    Returns:
        DataFrame with OHLCV data or None if fetch fails
    """
    try:
        # Use retry-enabled function
        @retry_with_backoff(max_retries=max_retries, base_delay=0.5, verbose=True)
        def _fetch():
            return _fetch_from_yfinance(symbol, period, start, end, interval)

        hist = _fetch()

        if hist is None or hist.empty:
            logger.warning(f"⚠️ Empty data for {symbol}")
            return None

        if len(hist) < min_rows:
            logger.warning(f"⚠️ Insufficient data for {symbol}: {len(hist)} rows < {min_rows}")
            return None

        return hist

    except Exception as e:
        logger.error(f"❌ Failed to fetch {symbol}: {e}")
        return None
