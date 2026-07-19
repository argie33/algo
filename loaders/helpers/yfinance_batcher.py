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
import os
import signal
import time
from collections.abc import Generator
from typing import Any

logger = logging.getLogger(__name__)


def batch_tickers(symbols: list[str], batch_size: int = 50) -> Generator[dict[str, Any], None, None]:
    """Batch yfinance.Ticker() fetches to reduce API calls.

    Yields dicts mapping symbols to fetched Ticker objects.

    Args:
        symbols: List of stock symbols to fetch
        batch_size: Number of symbols per yfinance call (50 is reasonable)

    Yields:
        Dict mapping each symbol to its Ticker object (or None if unavailable)
    """
    # Delegate each symbol to YFinanceWrapper.get_ticker rather than calling
    # yf.Ticker() directly. Confirmed live 2026-07-13: the previous inner
    # try/except caught every per-symbol exception (including 401 "Invalid
    # Crumb" bursts) and silently set result[symbol] = None with zero backoff,
    # zero rate limiting, and zero participation in the shared cross-ECS-task
    # circuit breaker every other yfinance call site uses -- which also made
    # the outer retry_attempt loop dead code, since no exception ever escaped
    # the inner loop to trigger it. This let yfinance_snapshot hammer Yahoo
    # Finance unthrottled across 8000+ symbols, the likely actual driver of
    # the shared-IP rate-limit storm that was starving every other loader.
    from utils.external.yfinance import YFinanceWrapper

    start_time = time.time()
    max_batch_time_sec = int(os.getenv("YFINANCE_BATCH_MAX_TIME_SEC", "120"))
    max_elapsed_sec = int(os.getenv("YFINANCE_TOTAL_MAX_TIME_SEC", "3600"))

    for batch_idx in range(0, len(symbols), batch_size):
        elapsed = time.time() - start_time
        if elapsed > max_elapsed_sec:
            logger.warning(
                f"[YFINANCE_BATCHER] Total time budget exceeded ({elapsed:.0f}s > {max_elapsed_sec}s), "
                f"stopping early at batch {batch_idx // batch_size}/{len(symbols) // batch_size}"
            )
            break

        batch = symbols[batch_idx : batch_idx + batch_size]
        batch_start = time.time()
        logger.info(f"[YFINANCE_BATCHER] Fetching batch {batch_idx // batch_size + 1}: {len(batch)} symbols")

        result: dict[str, Any] = {}
        for symbol in batch:
            try:
                result[symbol] = YFinanceWrapper.get_ticker(symbol)
                batch_elapsed = time.time() - batch_start
                if batch_elapsed > max_batch_time_sec:
                    logger.warning(
                        f"[YFINANCE_BATCHER] Batch time budget exceeded ({batch_elapsed:.0f}s > {max_batch_time_sec}s), "
                        f"stopping batch early at {len(result)}/{len(batch)} symbols"
                    )
                    break
            except Exception as e:
                logger.debug(f"[YFINANCE_BATCHER] {symbol}: {e}")
                result[symbol] = None

        yield result


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
