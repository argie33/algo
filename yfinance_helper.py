#!/usr/bin/env python3
"""
yfinance Rate Limiting Helper
Provides smart retry logic with exponential backoff for yfinance API calls
Helps prevent hitting rate limits and improves success rates
"""

import time
import logging
import yfinance as yf
from functools import wraps
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_MAX_RETRIES = 5
DEFAULT_INITIAL_DELAY = 1  # seconds
DEFAULT_MAX_DELAY = 300  # 5 minutes
EXPONENTIAL_BASE = 2

class RateLimitError(Exception):
    """Raised when rate limit is exceeded after all retries"""
    pass

def is_rate_limit_error(exception: Exception) -> bool:
    """Check if an exception is related to rate limiting"""
    error_str = str(exception).lower()
    error_type = type(exception).__name__

    rate_limit_keywords = [
        "too many requests",
        "rate limit",
        "rate-limit",
        "yfratelimit",
        "429",
        "http error 429",
    ]

    return any(keyword in error_str for keyword in rate_limit_keywords) or \
           "YFRateLimit" in error_type or \
           "http error 429" in error_str

def retry_with_backoff(
    max_retries: int = DEFAULT_MAX_RETRIES,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    exponential_base: float = EXPONENTIAL_BASE,
    verbose: bool = True
):
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff calculation
        verbose: Whether to log detailed retry information

    Example:
        @retry_with_backoff(max_retries=5)
        def fetch_data(symbol):
            return yf.Ticker(symbol).history(period="1y")
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_retries + 1):
                try:
                    if verbose and attempt > 1:
                        logger.info(f"Attempt {attempt}/{max_retries} for {func.__name__}...")
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    if attempt >= max_retries:
                        if verbose:
                            logger.error(f"❌ {func.__name__} failed after {max_retries} attempts: {e}")
                        raise

                    # Check if it's a rate limit error
                    if is_rate_limit_error(e):
                        delay = min(
                            initial_delay * (exponential_base ** (attempt - 1)),
                            max_delay
                        )
                        if verbose:
                            logger.warning(
                                f"⚠️  Rate limited (attempt {attempt}/{max_retries}): {type(e).__name__}. "
                                f"Waiting {delay:.1f}s before retry..."
                            )
                        time.sleep(delay)
                    else:
                        # Non-rate-limit errors: shorter backoff
                        delay = min(2.0 * attempt, 10.0)  # Max 10 seconds
                        if verbose:
                            logger.warning(
                                f"⚠️  Error (attempt {attempt}/{max_retries}): {type(e).__name__}. "
                                f"Waiting {delay:.1f}s before retry..."
                            )
                        time.sleep(delay)

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator

def fetch_ticker_history(
    symbol: str,
    period: str = "1y",
    max_retries: int = DEFAULT_MAX_RETRIES,
    min_rows: int = 0
) -> Optional[Any]:
    """
    Fetch ticker history with automatic retry on rate limits.

    Args:
        symbol: Stock ticker symbol
        period: Period for history (e.g., "1y", "5y")
        max_retries: Maximum number of retry attempts
        min_rows: Minimum number of rows expected (check for empty results)

    Returns:
        DataFrame of historical data, or None if failed

    Raises:
        RateLimitError: If rate limit is hit too many times
    """

    @retry_with_backoff(max_retries=max_retries, verbose=False)
    def _fetch():
        return yf.Ticker(symbol).history(period=period)

    try:
        df = _fetch()

        if df.empty or (min_rows > 0 and len(df) < min_rows):
            logger.warning(f"No data returned for {symbol} (got {len(df)} rows, expected >= {min_rows})")
            return None

        return df

    except Exception as e:
        if is_rate_limit_error(e):
            logger.error(f"❌ Rate limit exceeded for {symbol}: {e}")
            raise RateLimitError(f"Rate limit for {symbol}")
        else:
            logger.error(f"❌ Failed to fetch {symbol}: {e}")
            return None

def fetch_financials(
    symbol: str,
    financial_type: str = "quarterly_financials",
    max_retries: int = DEFAULT_MAX_RETRIES
) -> Optional[Dict]:
    """
    Fetch financial data (income statement, balance sheet, cash flow) with retries.

    Args:
        symbol: Stock ticker symbol
        financial_type: Type of financial data (e.g., "quarterly_financials", "quarterly_balance_sheet")
        max_retries: Maximum number of retry attempts

    Returns:
        Financial data, or None if failed
    """

    @retry_with_backoff(max_retries=max_retries, verbose=False)
    def _fetch():
        ticker = yf.Ticker(symbol)
        if hasattr(ticker, financial_type):
            return getattr(ticker, financial_type)
        return None

    try:
        return _fetch()
    except Exception as e:
        if not is_rate_limit_error(e):
            logger.debug(f"Failed to fetch {financial_type} for {symbol}: {e}")
        return None

def batch_fetch(
    symbols: list,
    fetch_func,
    batch_size: int = 5,
    delay_between_batches: float = 2.0,
    max_retries: int = DEFAULT_MAX_RETRIES
) -> Dict[str, Any]:
    """
    Fetch data for multiple symbols with batching to reduce rate limit issues.

    Args:
        symbols: List of ticker symbols
        fetch_func: Function to call for each symbol (should accept symbol as first arg)
        batch_size: Number of symbols to process before delaying
        delay_between_batches: Delay in seconds between batches
        max_retries: Max retries per symbol

    Returns:
        Dictionary mapping symbols to their fetched data (None if fetch failed)

    Example:
        results = batch_fetch(
            ['AAPL', 'MSFT', 'GOOGL'],
            fetch_func=lambda s: yf.Ticker(s).history(period='1y'),
            batch_size=3,
            delay_between_batches=2.0
        )
    """
    results = {}
    processed = 0
    failed = 0

    for i, symbol in enumerate(symbols):
        try:
            # Add delay between batches
            if i > 0 and i % batch_size == 0:
                logger.info(f"Batch of {batch_size} complete. Waiting {delay_between_batches}s...")
                time.sleep(delay_between_batches)

            data = fetch_func(symbol, max_retries=max_retries)
            results[symbol] = data

            if data is not None:
                processed += 1
            else:
                failed += 1

        except RateLimitError:
            results[symbol] = None
            failed += 1
            logger.error(f"❌ {symbol}: Rate limit exceeded, skipping")
        except Exception as e:
            results[symbol] = None
            failed += 1
            logger.error(f"❌ {symbol}: {e}")

    logger.info(f"Batch fetch complete: {processed} succeeded, {failed} failed")
    return results

