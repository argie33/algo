#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
UNIFIED Price Loader - loads all intervals (1d, 1wk, 1mo) and asset classes (stock, etf).

Environment variables (set by Terraform/ECS task definition):
  LOADER_INTERVALS: comma-separated intervals (default: "1d,1wk,1mo")
  LOADER_ASSET_CLASSES: comma-separated asset classes (default: "stock,etf")
  LOADER_SYMBOLS: optional comma-separated symbols; if blank, uses database active symbols
  LOADER_PARALLELISM: thread pool size (default: 2)

Runs each interval+asset_class combination sequentially, parallelizing symbol fetches within.
Tables: price_daily, price_weekly, price_monthly, etf_price_daily, etf_price_weekly, etf_price_monthly
"""

import argparse
import logging
import os
from datetime import date, timedelta
from typing import List, Optional

from config.env_loader import load_env
from utils.db_connection import get_db_connection
from utils.monitoring.loader_validation import validate_price_row, count_validation_errors
from utils.data_provenance_tracker import DataProvenanceTracker
from utils.data_tick_validator import validate_price_tick
from utils.data_watermark_manager import WatermarkManager
from utils.loader_helpers import get_active_symbols
from utils.structured_logger import get_logger
from utils.monitoring_context import TimeBlock
from utils.optimal_loader import OptimalLoader

logger = get_logger(__name__)


class PriceLoader(OptimalLoader):
    """Multi-timeframe price loader. Replaces 4 separate loaders."""

    def __init__(self, interval: str = "1d", asset_class: str = "stock", *args, **kwargs):
        """Initialize with interval (1d/1wk/1mo) and asset class (stock/etf)."""
        assert interval in ("1d", "1wk", "1mo"), f"Invalid interval: {interval}"
        assert asset_class in ("stock", "etf"), f"Invalid asset_class: {asset_class}"

        self.interval = interval
        self.asset_class = asset_class

        # Map interval + asset_class to table name
        if asset_class == "etf":
            if interval == "1d":
                self.table_name = "etf_price_daily"
            elif interval == "1wk":
                self.table_name = "etf_price_weekly"
            else:  # 1mo
                self.table_name = "etf_price_monthly"
        else:  # stock
            if interval == "1d":
                self.table_name = "price_daily"
            elif interval == "1wk":
                self.table_name = "price_weekly"
            else:  # 1mo
                self.table_name = "price_monthly"

        self.primary_key = ("symbol", "date")
        self.watermark_field = "date"
        super().__init__(*args, **kwargs)
        self.tracker = None
        self.watermark_mgr = None
        self.run_id = None

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch OHLCV from yfinance at specified interval."""
        end = date.today()
        if since is None:
            # First run: load 100 days instead of 5 years for speed
            # Technical indicators need ~60-100 days, full history can be backfilled later
            start = end - timedelta(days=100)
        else:
            start = since + timedelta(days=1)

        if start > end:
            return None

        # Try to fetch fresh data from live APIs
        rows = self._try_fetch(symbol, start, end)
        if rows:
            return rows

        return None

    def _try_fetch(self, symbol: str, start: date, end: date, max_retries: int = 3):
        """Try to fetch data from yfinance with retry logic for transient failures."""
        import time
        for attempt in range(max_retries):
            try:
                return self.router.fetch_ohlcv_interval(symbol, start, end, self.interval)
            except Exception as e:
                error_str = str(e).lower()
                # Rate limit errors - don't re-raise, just return None
                if "rate" in error_str or "429" in error_str or "too many" in error_str:
                    logger.debug(f"[{symbol}] Rate limited: {e}")
                    return None
                # Network/timeout errors in AWS - retry with backoff
                if any(x in error_str for x in ["timeout", "json", "parse", "connection", "reset"]):
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # 1s, 2s, 4s
                        logger.warning(f"[{symbol}] Transient error (attempt {attempt + 1}/{max_retries}): {e}, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    logger.warning(f"[{symbol}] Transient error after {max_retries} attempts: {e}")
                    return None
                # Auth errors - log but don't crash
                if "403" in error_str or "401" in error_str or "unauthorized" in error_str:
                    logger.warning(f"[{symbol}] Auth error: {e}")
                    return None
                # Other errors - log and re-raise
                logger.error(f"[{symbol}] Unexpected error: {e}")
                raise
        return None

    def transform(self, rows):
        """Validate and filter rows. Phase 1: Reject invalid ticks. Integrated validation framework."""
        if not rows:
            return []

        # TIER 2: Use loader_validation framework for comprehensive validation
        validated, validation_errors = count_validation_errors(
            rows,
            validate_price_row,
            logger_name="loadpricedaily"
        )

        if validation_errors > 0 and self.tracker:
            self.tracker.record_error(
                symbol='[batch]',
                error_type='VALIDATION_FAILED',
                error_message=f'{validation_errors} rows failed validation',
                resolution='filtered',
            )

        # PHASE 1: Secondary validation via existing tick validator for provenance tracking
        final_validated = []
        prior_close = None

        for row in validated:
            is_valid, errors = validate_price_tick(
                symbol=row.get('symbol'),
                open_price=row.get('open'),
                high=row.get('high'),
                low=row.get('low'),
                close=row.get('close'),
                volume=row.get('volume'),
                prior_close=prior_close,
            )

            if not is_valid:
                if self.tracker:
                    self.tracker.record_error(
                        symbol=row.get('symbol'),
                        error_type='DATA_INVALID',
                        error_message=', '.join(errors),
                        resolution='skipped',
                    )
                logger.warning(f"[{row.get('symbol')}] {row.get('date')}: {errors[0]}")
                continue

            # Track provenance for each valid tick
            if self.tracker:
                self.tracker.record_tick(
                    symbol=row.get('symbol'),
                    tick_date=row.get('date'),
                    data=row,
                    source_api='yfinance',  # Could detect from router later
                )

            final_validated.append(row)
            prior_close = row.get('close')

        return final_validated

    def _validate_row(self, row: dict) -> bool:
        """Add price-range sanity check on top of default PK check."""
        if not super()._validate_row(row):
            return False
        try:
            return (
                row["high"] >= row["low"]
                and row["close"] > 0
                and row["open"] > 0
            )
        except (KeyError, TypeError):
            return False

    def start_provenance_tracking(self):
        """Initialize Phase 1 data integrity components."""
        db_conn = get_db_connection()
        self.tracker = DataProvenanceTracker(
            loader_name="loadpricedaily",
            table_name="price_daily",
            db_conn=db_conn,
        )
        self.watermark_mgr = WatermarkManager(
            loader_name="loadpricedaily",
            table_name="price_daily",
            db_conn=db_conn,
            granularity="symbol",
        )
        self.run_id = self.tracker.start_run(source_api="yfinance")
        logger.info(f"[Phase 1] Started provenance tracking: run_id={self.run_id}")

    def end_provenance_tracking(self, success: bool = True):
        """Finalize Phase 1 data integrity tracking."""
        if self.tracker and self.run_id:
            self.tracker.end_run(success=success)
            logger.info(f"[Phase 1] Ended provenance tracking: run_id={self.run_id}")



def main():
    """Read config from environment variables (set by ECS task definition)."""
    try:
        load_env()
        logger.info("[MAIN] Environment loaded successfully")
    except Exception as e:
        logger.error(f"[MAIN] Failed to load environment: {e}", exc_info=True)
        return 1

    # Read from environment variables (no CLI args, cleaner for containerized execution)
    intervals_str = os.getenv("LOADER_INTERVALS", "1d,1wk,1mo")
    asset_classes_str = os.getenv("LOADER_ASSET_CLASSES", "stock,etf")
    symbols_str = os.getenv("LOADER_SYMBOLS", "")
    parallelism = int(os.getenv("LOADER_PARALLELISM", "2"))

    # Parse comma-separated values
    intervals = [x.strip() for x in intervals_str.split(",")]
    asset_classes = [x.strip() for x in asset_classes_str.split(",")]

    # Validate
    valid_intervals = {"1d", "1wk", "1mo"}
    valid_classes = {"stock", "etf"}
    for i in intervals:
        if i not in valid_intervals:
            logger.error(f"Invalid interval: {i}. Must be one of: {valid_intervals}")
            return 1
    for a in asset_classes:
        if a not in valid_classes:
            logger.error(f"Invalid asset class: {a}. Must be one of: {valid_classes}")
            return 1

    try:
        if symbols_str:
            symbols = [s.strip().upper() for s in symbols_str.split(",")]
            logger.info(f"[MAIN] Loaded {len(symbols)} symbols from environment")
        else:
            # On first run with many symbols, limit to prevent timeout
            # Watermark system ensures we process all symbols eventually
            symbols = get_active_symbols(max_symbols=100, timeout_secs=30)
            logger.info(f"[MAIN] Loaded {len(symbols)} symbols from database (max 100 for timeout protection)")
            if len(symbols) == 0:
                logger.warning("[MAIN] No symbols found in stock_symbols table - exiting")
                return 1
    except Exception as e:
        logger.error(f"[MAIN] Failed to get symbols: {e}", exc_info=True)
        return 1

    # Run price loader for each interval + asset_class combination
    total_stats = {"symbols_loaded": 0, "symbols_failed": 0, "rows_inserted": 0}
    fail_count = 0

    for asset_class in asset_classes:
        for interval in intervals:
            try:
                loader = PriceLoader(interval=interval, asset_class=asset_class)
                logger.info(f"[MAIN] Starting: interval={interval}, asset_class={asset_class}, parallelism={parallelism}")
                with TimeBlock(f"loadpricedaily_{asset_class}_{interval}"):
                    stats = loader.run(symbols, parallelism=parallelism)

                logger.info(f"[MAIN] Completed {asset_class}/{interval}: {stats}")
                total_stats["symbols_loaded"] += stats.get("symbols_loaded", 0)
                total_stats["symbols_failed"] += stats.get("symbols_failed", 0)
                total_stats["rows_inserted"] += stats.get("rows_inserted", 0)

                fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
                if fail_rate > 0.05:
                    logger.error(f"Too many failures for {asset_class}/{interval}: {stats['symbols_failed']}/{len(symbols)}")
                    fail_count += 1

                loader.close()
            except Exception as e:
                logger.error(f"[MAIN] Loader failed for {asset_class}/{interval}: {e}", exc_info=True)
                fail_count += 1
                return 1

    logger.info(f"[MAIN] All intervals completed. Total: {total_stats}")
    if fail_count > 0:
        logger.error(f"[MAIN] {fail_count} interval(s) had too many failures")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
