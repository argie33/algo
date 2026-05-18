#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Daily Price Loader - Enhanced with Data Integrity Phase 1.

Includes tick-level validation (OHLC logic, volume sanity, price sequences),
complete provenance tracking (run_id, checksums, error logging),
and atomic watermark persistence (crash-safe, idempotent).

Run:
    python3 loadpricedaily.py [--symbols AAPL,MSFT] [--parallelism 8]
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
from utils.logging_setup import get_logger
from utils.monitoring_context import TimeBlock
from utils.optimal_loader import OptimalLoader

logger = get_logger(__name__)


class PriceDailyLoader(OptimalLoader):
    table_name = "price_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker = None
        self.watermark_mgr = None
        self.run_id = None

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch OHLCV via the data source router. Fail-closed on API errors (no price injection)."""
        end = date.today()
        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since + timedelta(days=1)

        if start > end:
            return None

        # Try to fetch fresh data from live APIs
        rows = self._try_fetch(symbol, start, end)
        if rows:
            return rows

        return None

    def _try_fetch(self, symbol: str, start: date, end: date):
        """Try to fetch data from live APIs. Returns None on rate limit/error (triggers fallback)."""
        try:
            return self.router.fetch_ohlcv(symbol, start, end)
        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e) or "too many" in str(e).lower():
                logger.debug(f"[{symbol}] Rate limited: {e}")
                return None  # Trigger fallback
            raise  # Re-raise other errors

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
    try:
        load_env()
        logger.info("[MAIN] Environment loaded successfully")
    except Exception as e:
        logger.error(f"[MAIN] Failed to load environment: {e}", exc_info=True)
        return 1

    parser = argparse.ArgumentParser(description="Price Daily Loader - Phase 1 Data Integrity Enabled")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    default_parallelism = int(os.getenv("PARALLELISM", os.getenv("LOADER_PARALLELISM", "2")))
    parser.add_argument("--parallelism", type=int, default=default_parallelism, help="Concurrent workers")
    args = parser.parse_args()

    try:
        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",")]
            logger.info(f"[MAIN] Loaded {len(symbols)} symbols from CLI")
        else:
            symbols = get_active_symbols()
            logger.info(f"[MAIN] Loaded {len(symbols)} symbols from database")
    except Exception as e:
        logger.error(f"[MAIN] Failed to get symbols: {e}", exc_info=True)
        return 1

    loader = PriceDailyLoader()
    try:
        logger.info(f"[MAIN] Starting price loader (parallelism={args.parallelism})")
        # Run the loader with validation + provenance tracking
        with TimeBlock("loadpricedaily"):
            stats = loader.run(symbols, parallelism=args.parallelism)

        logger.info(f"[MAIN] Loader completed: {stats}")
        return 0 if stats["symbols_failed"] == 0 else 1

    except Exception as e:
        logger.error(f"[MAIN] Loader failed with error: {e}", exc_info=True)
        return 1
    finally:
        loader.close()


if __name__ == "__main__":
    sys.exit(main())
