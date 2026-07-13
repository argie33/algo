#!/usr/bin/env python3
"""Batch yfinance API calls to reduce rate limiting and improve performance.

Consolidates multiple symbol fetches into single batch API calls.
Implements exponential backoff for rate limit (429) responses.

Usage:
    from loaders.helpers.yfinance_batcher import batch_tickers, batch_download

    # Batch yfinance.Ticker() calls
    for batch in batch_tickers(symbols, batch_size=50):
        for symbol, ticker in batch.items():
            if ticker:
                info = ticker.info
            else:
                # Handle unavailable ticker

    # Batch yfinance.download() calls
    for batch_symbols in batch_download(symbols, batch_size=50, start_date, end_date):
        df = yf.download(batch_symbols, start=start_date, end=end_date)
"""

import logging
import time
from collections.abc import Generator
from typing import Any

logger = logging.getLogger(__name__)


def batch_tickers(symbols: list[str], batch_size: int = 50) -> Generator[dict[str, Any], None, None]:
    """Batch yfinance.Ticker() fetches to reduce API calls.

    Yields dicts mapping symbols to fetched Ticker objects.
    Implements exponential backoff for rate limiting.

    Args:
        symbols: List of stock symbols to fetch
        batch_size: Number of symbols per yfinance call (50 is reasonable)

    Yields:
        Dict mapping each symbol to its Ticker object (or None if unavailable)
    """
    import yfinance as yf

    max_retries = 3
    backoff_base = 2

    for batch_idx in range(0, len(symbols), batch_size):
        batch = symbols[batch_idx : batch_idx + batch_size]
        logger.info(f"[YFINANCE_BATCHER] Fetching batch {batch_idx // batch_size + 1}: {len(batch)} symbols")

        for retry_attempt in range(max_retries):
            try:
                # Fetch all symbols in batch
                result = {}
                for symbol in batch:
                    try:
                        ticker = yf.Ticker(symbol)
                        # Test that ticker is valid by accessing info
                        _ = ticker.info
                        result[symbol] = ticker
                    except Exception as e:
                        logger.debug(f"[YFINANCE_BATCHER] {symbol}: {e}")
                        result[symbol] = None

                yield result
                break  # Success, don't retry

            except Exception as e:
                # Rate limit or network error
                if "429" in str(e) or "Too Many Requests" in str(e):
                    if retry_attempt < max_retries - 1:
                        wait_time = backoff_base**retry_attempt
                        logger.warning(
                            f"[YFINANCE_BATCHER] Rate limited. "
                            f"Retrying batch {batch_idx // batch_size + 1} after {wait_time}s "
                            f"(attempt {retry_attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error("[YFINANCE_BATCHER] Rate limited, max retries exceeded. Skipping batch.")
                        yield dict.fromkeys(batch)
                        break
                else:
                    logger.error(f"[YFINANCE_BATCHER] Unexpected error: {e}")
                    yield dict.fromkeys(batch)
                    break


def batch_download(
    symbols: list[str], batch_size: int = 50, start_date: str | None = None, end_date: str | None = None
) -> Generator[list[str], None, None]:
    """Batch yfinance.download() calls.

    Yields lists of symbols for batched downloads.
    Caller is responsible for calling yf.download(batch_symbols, ...).

    Args:
        symbols: List of stock symbols to fetch
        batch_size: Number of symbols per yfinance.download() call
        start_date: Start date for download (optional)
        end_date: End date for download (optional)

    Yields:
        Lists of symbols (ready to pass to yf.download())

    Example:
        for batch_symbols in batch_download(symbols, batch_size=50):
            df = yf.download(batch_symbols, start=start_date, end=end_date)
            # Process df
    """
    for batch_idx in range(0, len(symbols), batch_size):
        batch = symbols[batch_idx : batch_idx + batch_size]
        logger.debug(f"[YFINANCE_BATCHER] Yield batch {batch_idx // batch_size + 1}: {len(batch)} symbols")
        yield batch


def split_batches(symbols: list[str], batch_size: int = 50) -> list[list[str]]:
    """Split symbols into batches (non-generator version).

    Args:
        symbols: List of stock symbols
        batch_size: Size of each batch

    Returns:
        List of symbol batches
    """
    batches = []
    for i in range(0, len(symbols), batch_size):
        batches.append(symbols[i : i + batch_size])
    return batches
