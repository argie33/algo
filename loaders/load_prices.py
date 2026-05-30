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
import time
from datetime import date, datetime, timedelta
from typing import List, Optional

from utils.database_context import DatabaseContext
from utils.data_provenance_tracker import DataProvenanceTracker
from utils.data_tick_validator import validate_price_tick
from utils.data_watermark_manager import WatermarkManager
from utils.loader_helpers import get_active_symbols
import logging
from monitoring.metrics_context import TimeBlock
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

class PriceLoader(OptimalLoader):
    """Multi-timeframe price loader. Replaces 4 separate loaders."""

    def __init__(self, interval: str = "1d", asset_class: str = "stock", *args, **kwargs):
        """Initialize with interval (1d/1wk/1mo) and asset class (stock/etf)."""
        assert interval in ("1d", "1wk", "1mo"), f"Invalid interval: {interval}"
        assert asset_class in ("stock", "etf"), f"Invalid asset_class: {asset_class}"

        self.interval = interval
        self.asset_class = asset_class
        self.batch_size = 50  # Batch 50 symbols per API call: 5000 symbols = 100 calls

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
        from algo.algo_market_calendar import MarketCalendar

        end = date.today()
        # If today is not a trading day, fetch through yesterday instead
        # (prevents fetching on non-trading days when no data will be published)
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        if since is None:
            # First run: load 100 days instead of 5 years for speed
            # Technical indicators need ~60-100 days, full history can be backfilled later
            start = end - timedelta(days=100)
        else:
            # BUG FIX: Calculate start before comparing to end
            # If watermark is Friday and today is Monday, since=Friday, start=Saturday
            # After adjusting end to Friday (last trading day), start > end causes return None
            # Solution: Always fetch at least the watermark date again (in case of partial updates)
            start = since

        if start > end:
            return None

        # Try to fetch fresh data from live APIs
        rows = self._try_fetch(symbol, start, end)
        if rows:
            return rows

        return None

    def fetch_batch_incremental(self, symbols: List[str], since: Optional[date]):
        """Fetch OHLCV for multiple symbols at once (50x faster than per-symbol).

        Returns: dict[symbol] -> rows or None
        """
        from algo.algo_market_calendar import MarketCalendar

        end = date.today()
        # If today is not a trading day, fetch through yesterday instead
        # (prevents fetching on non-trading days when no data will be published)
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        if since is None:
            start = end - timedelta(days=100)
        else:
            # BUG FIX: Same as fetch_incremental - use since directly, not since+1day
            # Allows refetch of watermark date for partial updates
            start = since

        if start > end:
            return {s: None for s in symbols}

        # Batch fetch from router
        return self.router.fetch_ohlcv_batch(symbols, start, end, interval=self.interval)

    def _try_fetch(self, symbol: str, start: date, end: date, max_retries: int = 5):
        """Try to fetch data from yfinance with retry logic for transient failures."""
        import time
        for attempt in range(max_retries):
            try:
                return self.router.fetch_ohlcv_interval(symbol, start, end, self.interval)
            except Exception as e:
                error_str = str(e).lower()
                # Rate limit errors - retry with exponential backoff
                if "rate" in error_str or "429" in error_str or "too many" in error_str:
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) * 5  # 5s, 10s, 20s, 40s, 80s
                        logger.warning(f"[{symbol}] Rate limited (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    logger.warning(f"[{symbol}] Rate limited after {max_retries} attempts, giving up")
                    return None
                # Network/timeout errors - retry with backoff
                if any(x in error_str for x in ["timeout", "json", "parse", "connection", "reset"]):
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
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

        from algo.algo_market_calendar import MarketCalendar

        # PHASE 1: Validation via tick validator for provenance tracking
        final_validated = []
        prior_close = None

        for row in rows:
            # CRITICAL: Filter out weekend/holiday data before any other validation
            # yfinance occasionally returns non-trading-day rows; we must reject them
            row_date_str = row.get('date')
            try:
                row_date = datetime.fromisoformat(row_date_str).date()
                if not MarketCalendar.is_trading_day(row_date):
                    if self.tracker:
                        self.tracker.record_error(
                            symbol=row.get('symbol'),
                            error_type='NON_TRADING_DAY',
                            error_message=f'Data for non-trading day (weekend/holiday)',
                            resolution='rejected',
                        )
                    logger.debug(f"[{row.get('symbol')}] {row_date}: Non-trading day, rejecting")
                    continue
            except (ValueError, TypeError) as e:
                logger.warning(f"[{row.get('symbol')}] Could not parse date {row_date_str}: {e}")
                continue

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
        with DatabaseContext() as cur:
            db_conn = cur.connection
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

    def run(self, symbols: list, parallelism: int = 1, backfill_days: Optional[int] = None) -> dict:
        """Override to use batch fetching (50x faster than per-symbol)."""
        if backfill_days is not None:
            self._backfill_days = backfill_days

        import time
        start = time.time()
        symbols = list(symbols)
        mode = f" (backfill {self._backfill_days}d)" if self._backfill_days > 0 else ""
        logger.info(
            "[%s] Starting batch load: %d symbols (batch_size=%d)%s",
            self.table_name, len(symbols), self.batch_size, mode,
        )

        # Process symbols in batches
        for i in range(0, len(symbols), self.batch_size):
            batch = symbols[i:i + self.batch_size]
            self._load_batch(batch)
            progress = min(i + self.batch_size, len(symbols))
            logger.info("  Progress: %d/%d", progress, len(symbols))

        self._stats["duration_sec"] = round(time.time() - start, 2)
        logger.info(
            "[%s] Done. fetched=%d dedup_skip=%d quality_drop=%d inserted=%d "
            "(processed=%d skipped_wm=%d failed=%d) %.1fs sources=%s",
            self.table_name,
            self._stats["rows_fetched"],
            self._stats["rows_dedup_skipped"],
            self._stats["rows_quality_dropped"],
            self._stats["rows_inserted"],
            self._stats["symbols_processed"],
            self._stats["symbols_skipped_by_watermark"],
            self._stats["symbols_failed"],
            self._stats["duration_sec"],
            self._stats["source_distribution"],
        )

        try:
            from algo.algo_metrics import MetricsPublisher
            with MetricsPublisher() as m:
                m.put_loader_result(self.table_name, self._stats)
        except Exception as e:
            logger.debug("metrics unavailable: %s", e)

        try:
            from utils.database_context import DatabaseContext

            with DatabaseContext('read') as cur:
                cur.execute(
                    f"SELECT COUNT(*), MAX(date) FROM {self.table_name}"
                )
                result = cur.fetchone()
                total_rows = result[0] if result else 0
                latest_date = result[1] if result else None

            with DatabaseContext('write') as cur:
                cur.execute("""
                    INSERT INTO data_loader_status (table_name, row_count, latest_date, last_updated)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (table_name) DO UPDATE SET
                      row_count = EXCLUDED.row_count,
                      latest_date = EXCLUDED.latest_date,
                      last_updated = NOW()
                """, (self.table_name, total_rows, latest_date))
        except Exception as e:
            logger.warning(f"Failed to update data_loader_status for {self.table_name}: {e}")

        return self._stats

    def _load_batch(self, symbols: List[str]) -> None:
        """Load a batch of symbols using batch API fetch (50x reduction in API calls)."""
        wm_store = self._get_watermark()

        # Determine the watermark date for all symbols in batch
        # (simplified: use same date for all, finest-grained would be per-symbol)
        if self._backfill_days > 0:
            previous_date = (datetime.now().date() - timedelta(days=self._backfill_days))
        else:
            # Use earliest watermark from batch
            watermarks = [wm_store.get(s) if wm_store else None for s in symbols]
            previous_dates = [self._parse_watermark_date(w) for w in watermarks]
            previous_date = min(d for d in previous_dates if d) if any(previous_dates) else None

        # Batch fetch all symbols at once
        batch_results = self.fetch_batch_incremental(symbols, previous_date)

        # Process each symbol's results
        for symbol in symbols:
            rows = batch_results.get(symbol) if batch_results else None
            if not rows:
                logger.debug(f"[{self.table_name}] {symbol}: No rows fetched, skipping")
                self._stats["symbols_skipped_by_watermark"] += 1
                continue

            logger.debug(f"[{self.table_name}] {symbol}: Fetched {len(rows)} rows from batch")
            self._stats["rows_fetched"] += len(rows)

            if self.router and self.router.last_source:
                src = self.router.last_source
                self._stats["source_distribution"][src] = (
                    self._stats["source_distribution"].get(src, 0) + 1
                )

            rows = self.transform(rows)
            before_quality = len(rows)
            rows = [r for r in rows if self._validate_row(r)]
            self._stats["rows_quality_dropped"] += before_quality - len(rows)

            # Bloom dedup (cheap pre-filter)
            # SKIP for price_daily: EOD price data is immutable, dedup not needed
            # Prevents filtering out fresh May 23 data that yfinance returns with May 22 date
            dedup = None  # self._get_dedup()
            if dedup and self.primary_key:
                before_dedup = len(rows)
                rows = self._dedup_filter(dedup, rows)
                self._stats["rows_dedup_skipped"] += before_dedup - len(rows)

            if not rows:
                self._stats["symbols_processed"] += 1
                continue

            # Calculate new watermark BEFORE insert
            new_wm = self.watermark_from_rows(rows)

            # Bulk insert in chunks
            inserted = 0
            for chunk_start in range(0, len(rows), self.chunk_size):
                chunk = rows[chunk_start:chunk_start + self.chunk_size]
                is_final_chunk = (chunk_start + self.chunk_size >= len(rows))
                chunk_wm = new_wm if is_final_chunk else None
                inserted += self._bulk_insert(chunk, symbol=symbol if is_final_chunk else None, new_watermark=chunk_wm)

            if dedup and self.primary_key:
                for row in rows:
                    key = ":".join(str(row.get(c, "")) for c in self.primary_key)
                    dedup.add(key)

            self._stats["rows_inserted"] += inserted
            self._stats["symbols_processed"] += 1

def log_loader_execution(loader_name, table_name, status, records_loaded=0, records_updated=0, error_msg=None, duration_seconds=0):
    """Log loader execution to data_loader_runs table for monitoring."""
    try:
        with DatabaseContext('write') as cur:
            cur.execute("""
                INSERT INTO data_loader_runs (
                    loader_name, table_name, run_date, status, records_loaded, records_updated,
                    error_message, duration_seconds, started_at, completed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                )
            """, (
                loader_name,
                table_name,
                date.today(),
                status,
                records_loaded,
                records_updated,
                error_msg,
                duration_seconds
            ))
    except Exception as e:
        logger.warning(f"Failed to log execution to data_loader_runs: {e}")

def main():
    """Read config from environment variables (set by ECS task definition)."""
    import time
    start_time = time.time()

    try:
        logger.info("[MAIN] Environment loaded successfully")
    except Exception as e:
        logger.error(f"[MAIN] Failed to load environment: {e}", exc_info=True)
        log_loader_execution('loadpricedaily', 'price_daily', 'failed', error_msg=str(e), duration_seconds=round(time.time() - start_time, 2))
        return 1

    # Read from environment variables (no CLI args, cleaner for containerized execution)
    intervals_str = os.getenv("LOADER_INTERVALS", "1d,1wk,1mo")
    asset_classes_str = os.getenv("LOADER_ASSET_CLASSES", "stock,etf")
    symbols_str = os.getenv("LOADER_SYMBOLS", "")
    parallelism = int(os.getenv("LOADER_PARALLELISM", "2"))
    max_symbols_limit = int(os.getenv("LOADER_MAX_SYMBOLS", "500"))  # Configurable; default 500 symbols per run

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
            # Limit symbols per run to prevent timeout, but configurable via LOADER_MAX_SYMBOLS
            # Watermark system ensures all symbols are processed across multiple runs
            symbols = get_active_symbols(max_symbols=max_symbols_limit, timeout_secs=60)
            logger.info(f"[MAIN] Loaded {len(symbols)} symbols from database (max {max_symbols_limit} for timeout protection)")
            if len(symbols) == 0:
                logger.warning("[MAIN] No symbols found in stock_symbols table - exiting")
                log_loader_execution('loadpricedaily', 'price_daily', 'failed', error_msg='No symbols found', duration_seconds=round(time.time() - start_time, 2))
                return 1
    except Exception as e:
        logger.error(f"[MAIN] Failed to get symbols: {e}", exc_info=True)
        log_loader_execution('loadpricedaily', 'price_daily', 'failed', error_msg=str(e), duration_seconds=round(time.time() - start_time, 2))
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
                # Increased threshold to 10% - with small batches (30 symbols), transient API failures are common
                # 5% threshold meant even 2-3 transient failures would fail the entire loader
                if fail_rate > 0.10:
                    logger.error(f"Too many failures for {asset_class}/{interval}: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")
                    fail_count += 1
                else:
                    logger.info(f"Acceptable failure rate for {asset_class}/{interval}: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")

                loader.close()
            except Exception as e:
                logger.error(f"[MAIN] Loader failed for {asset_class}/{interval}: {e}", exc_info=True)
                fail_count += 1
                return 1

    logger.info(f"[MAIN] All intervals completed. Total: {total_stats}")

    duration_seconds = round(time.time() - start_time, 2)
    if fail_count > 0:
        logger.error(f"[MAIN] {fail_count} interval(s) had too many failures")
        log_loader_execution(
            'loadpricedaily',
            'price_daily',
            'failed',
            records_loaded=total_stats.get('rows_inserted', 0),
            error_msg=f"{fail_count} interval(s) failed",
            duration_seconds=duration_seconds
        )
        return 1

    log_loader_execution(
        'loadpricedaily',
        'price_daily',
        'completed',
        records_loaded=total_stats.get('rows_inserted', 0),
        duration_seconds=duration_seconds
    )
    return 0

if __name__ == "__main__":
    sys.exit(main())

