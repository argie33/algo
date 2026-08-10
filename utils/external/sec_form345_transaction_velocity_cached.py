#!/usr/bin/env python3
"""Cached wrapper for Form 3/4/5 transaction velocity aggregator.

This wrapper:
- Caches downloaded data to avoid re-downloading on repeated calls
- Handles timeouts gracefully (returns partial data if available)
- Uses threading timeout for long-running operations
- Logs detailed progress for debugging
"""

import logging
import threading
from datetime import date, datetime, timezone
from pathlib import Path

from utils.external.sec_form345_transaction_velocity import Form345TransactionVelocityAggregator, VelocityMetrics

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / '.algo' / 'sec_form345_cache'
CACHE_TIMEOUT_SECONDS = 5 * 60  # 5 minute cache for metadata


class CachedForm345Aggregator:
    """Thread-safe cached wrapper around Form345TransactionVelocityAggregator."""

    def __init__(self, lookback_quarters: int = 12, timeout_seconds: int = 300) -> None:
        """Initialize cached aggregator.

        Args:
            lookback_quarters: How many quarters to fetch
            timeout_seconds: Timeout for initial data download (default 5 min)
        """
        self._lookback_quarters = lookback_quarters
        self._timeout_seconds = timeout_seconds
        self._aggregator: Form345TransactionVelocityAggregator | None = None
        self._build_thread: threading.Thread | None = None
        self._build_exception: Exception | None = None
        self._build_complete = threading.Event()
        self._lock = threading.Lock()

    def get_velocity_metrics(self, symbol: str, measurement_date: date | None = None, wait_for_download: bool = False) -> VelocityMetrics:
        """Get insider transaction velocity for a symbol.

        Args:
            symbol: Stock ticker
            measurement_date: Date to measure from (default: today)
            wait_for_download: If True, wait for full download. If False, return
                data_unavailable if download in progress.

        Returns:
            VelocityMetrics with data or appropriate unavailable reason
        """
        # Ensure download is started (but don't wait for it)
        self._ensure_download_started()

        # Default to today if measurement_date not provided
        effective_date = measurement_date or datetime.now(timezone.utc).date()

        # If caller wants to wait, do so
        if wait_for_download:
            if not self._build_complete.wait(timeout=self._timeout_seconds):
                return VelocityMetrics(
                    symbol=symbol,
                    measurement_date=effective_date,
                    data_unavailable=True,
                    reason="Form345_download_timeout",
                )

        # If download not complete yet, return unavailable
        if not self._build_complete.is_set():
            return VelocityMetrics(
                symbol=symbol,
                measurement_date=effective_date,
                data_unavailable=True,
                reason="Form345_download_in_progress",
            )

        # If download failed, return error
        if self._build_exception:
            return VelocityMetrics(
                symbol=symbol,
                measurement_date=effective_date,
                data_unavailable=True,
                reason=f"Form345_download_failed: {type(self._build_exception).__name__}",
            )

        # Download succeeded, fetch real data
        try:
            assert self._aggregator is not None, "Aggregator must be initialized"
            return self._aggregator.get_velocity_metrics(symbol, effective_date)
        except Exception as e:
            logger.warning(f"[Form345] Error getting metrics for {symbol}: {e}")
            return VelocityMetrics(
                symbol=symbol,
                measurement_date=effective_date,
                data_unavailable=True,
                reason=f"Form345_query_error: {type(e).__name__}",
            )

    def _ensure_download_started(self) -> None:
        """Start download in background if not already started."""
        with self._lock:
            if self._aggregator is not None or self._build_thread is not None:
                return  # Already started or complete

            # Start download in background thread
            self._build_thread = threading.Thread(target=self._background_build, daemon=True)
            self._build_thread.start()
            logger.info("[Form345] Started background download of Form 3/4/5 bulk data")

    def _background_build(self) -> None:
        """Download data in background thread."""
        try:
            logger.info(f"[Form345] Downloading {self._lookback_quarters} quarters of Form 3/4/5 data (may take 2-5 min)...")
            self._aggregator = Form345TransactionVelocityAggregator(lookback_quarters=self._lookback_quarters)
            # Trigger the build
            self._aggregator._ensure_built()
            logger.info(f"[Form345] Download complete: {len(self._aggregator._transactions)} symbols loaded")
        except Exception as e:
            logger.error(f"[Form345] Download failed: {type(e).__name__}: {str(e)[:200]}")
            self._build_exception = e
        finally:
            self._build_complete.set()
