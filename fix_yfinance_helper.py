#!/usr/bin/env python3
"""Fixed yfinance helper without progress parameter"""
import yfinance as yf
import time
from functools import wraps
import logging

logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries=3, base_delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Retry {attempt+1}/{max_retries} in {delay}s: {str(e)[:50]}")
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator

@retry_with_backoff(max_retries=3)
def _fetch_from_yfinance(ticker, period, start, end, interval):
    """Fetch without progress parameter"""
    return yf.Ticker(ticker).history(
        period=period if period else None,
        start=start if start else None,
        end=end if end else None,
        interval=interval
    )

def fetch_ticker_history(symbol, period='max', start=None, end=None, interval='1d',
                        max_retries=3, min_rows=1):
    """Fetch ticker history with retry logic"""
    try:
        hist = _fetch_from_yfinance(symbol, period, start, end, interval)
        
        if hist is None or hist.empty:
            logger.warning(f"Empty data for {symbol}")
            return None
        
        if len(hist) < min_rows:
            logger.warning(f"Insufficient data for {symbol}: {len(hist)} < {min_rows}")
            return None
        
        return hist
    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {e}")
        return None
