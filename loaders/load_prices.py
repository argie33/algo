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
        self.batch_size = 100  # Batch 100 symbols per API call: 5000 symbols = 50 calls (2x faster)

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

        # Proactive rate limiter for yfinance (global 30 calls/min limit)
        # Use token bucket to pace requests, avoid hitting limit
        self._rate_limit_tokens = 30  # Initial tokens (30 requests)
        self._rate_limit_last_refill = time.time()
        self._rate_limit_refill_rate = 30 / 60  # 30 tokens per 60 seconds = 0.5 per second

        # Market close detection for EOD pipeline (4:05 PM ET start)
        # At 4:05 PM, market just closed at 4:00 PM. yfinance API can lag 5-10 minutes.
        # If running 1d interval at market close, wait for SPY close data before proceeding.
        self._market_close_detected = False

    def _check_market_close_data_available(self, max_wait_sec: int = 600) -> bool:
        """Check if SPY close data is available (within 10 minutes after market close at 4 PM ET).

        EOD pipeline starts at 4:05 PM ET. yfinance API can lag 5-10 minutes. Verify SPY 1d
        close data is available before spending 1-2 hours loading 5000+ symbols.

        Args:
            max_wait_sec: Max seconds to wait for data availability (default 10 min)

        Returns: True if SPY close data available (or not near market close), False if timeout
        """
        from datetime import datetime, timezone, timedelta
        from algo.algo_market_calendar import MarketCalendar
        today = date.today()

        # Check if today is a trading day
        if not MarketCalendar.is_trading_day(today):
            logger.info("[MARKET_CLOSE] Today is not a trading day, skipping close data check")
            return True

        # Check if we're within 30 minutes after market close (4:00 PM ET ± 30 min = 3:30 PM - 4:30 PM)
        now_et = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-5)))
        market_close_et = now_et.replace(hour=16, minute=0, second=0, microsecond=0)  # 4 PM ET
        minutes_after_close = (now_et - market_close_et).total_seconds() / 60

        # If we're more than 30 minutes after market close, assume data is available
        if minutes_after_close > 30:
            logger.info(f"[MARKET_CLOSE] {minutes_after_close:.0f}min after market close, skipping check")
            return True

        # If we're before market close, skip (early run or different time zone)
        if minutes_after_close < 0:
            logger.info(f"[MARKET_CLOSE] Before market close ({minutes_after_close:.0f}min), data will be available soon")
            return True

        # We're 0-30 minutes after market close - verify SPY data
        logger.info(f"[MARKET_CLOSE] {minutes_after_close:.1f}min after close, checking if SPY data available...")

        start_time = time.time()
        attempt = 0
        max_attempts = int(max_wait_sec / 5)  # Try every 5 seconds

        while time.time() - start_time < max_wait_sec:
            attempt += 1
            try:
                # Try to fetch SPY 1d data from yfinance
                spy_data = self.router.fetch_ohlcv_interval('SPY', today, today + timedelta(days=1), '1d')
                if spy_data:
                    latest_row = spy_data[-1] if spy_data else None
                    if latest_row and latest_row.get('close'):
                        elapsed = time.time() - start_time
                        logger.info(f"[MARKET_CLOSE] ✓ SPY close data available after {elapsed:.1f}s (attempt {attempt})")
                        return True
            except Exception as e:
                logger.debug(f"[MARKET_CLOSE] Attempt {attempt}: SPY fetch failed ({e})")

            # Wait 5 seconds before retrying
            wait_remaining = max_wait_sec - (time.time() - start_time)
            if wait_remaining > 0:
                wait_time = min(5, wait_remaining)
                if attempt < max_attempts:
                    logger.debug(f"[MARKET_CLOSE] Waiting {wait_time:.1f}s before retry...")
                    time.sleep(wait_time)

        # Timeout - data not available
        elapsed = time.time() - start_time
        logger.warning(
            f"[MARKET_CLOSE] SPY close data NOT available after {elapsed:.0f}s ({attempt} attempts). "
            f"yfinance API lag may cause incomplete data. Proceeding with caution."
        )
        return False

    def _rate_limit_wait(self, tokens_needed: int = 1) -> None:
        """Apply token bucket rate limiting to avoid yfinance 429 errors.

        Tokens refill at 30 per minute (0.5 per second). Before fetching,
        wait if necessary to stay under the limit.
        """
        import time

        while True:
            now = time.time()
            elapsed = now - self._rate_limit_last_refill
            # Refill tokens based on elapsed time
            self._rate_limit_tokens += elapsed * self._rate_limit_refill_rate
            self._rate_limit_last_refill = now

            if self._rate_limit_tokens >= tokens_needed:
                # Sufficient tokens, consume and return
                self._rate_limit_tokens -= tokens_needed
                return
            else:
                # Wait for token refill (calculate how long to wait)
                tokens_short = tokens_needed - self._rate_limit_tokens
                wait_sec = tokens_short / self._rate_limit_refill_rate
                if wait_sec > 0.1:  # Only log if waiting >100ms
                    logger.debug(f"Rate limit: waiting {wait_sec:.2f}s for {tokens_needed} tokens")
                time.sleep(min(wait_sec, 0.5))  # Wait up to 500ms before re-checking

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch OHLCV from yfinance at specified interval."""
        from algo.algo_market_calendar import MarketCalendar

        # yfinance end date is EXCLUSIVE: pass today+1 so today's trading data is always fetchable
        end = date.today() + timedelta(days=1)

        if since is None:
            # First run: load 100 days instead of 5 years for speed
            # Technical indicators need ~60-100 days, full history can be backfilled later
            start = end - timedelta(days=101)
        else:
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

        Fallback: If batch API fails, fall back to per-symbol fetching to ensure
        we don't lose an entire batch of symbols to a transient API error.
        """
        from algo.algo_market_calendar import MarketCalendar

        # yfinance end date is EXCLUSIVE: to fetch May 29 data we must pass end=May 30.
        # Use today+1 so today's data (if it's a trading day) is always included.
        end = date.today() + timedelta(days=1)

        if since is None:
            start = end - timedelta(days=101)
        else:
            start = since

        if start >= end:
            return {s: None for s in symbols}

        # Batch fetch from router
        try:
            # Apply rate limiting before batch fetch (batch = 1 API call)
            self._rate_limit_wait(tokens_needed=1)
            return self.router.fetch_ohlcv_batch(symbols, start, end, interval=self.interval)
        except Exception as e:
            # Fallback: If batch fails, fetch per-symbol to avoid losing entire batch
            logger.warning(f"Batch fetch failed ({len(symbols)} symbols): {e}. Falling back to per-symbol fetch.")
            results = {}
            for symbol in symbols:
                try:
                    # Rate limit each per-symbol fetch too
                    self._rate_limit_wait(tokens_needed=1)
                    rows = self._try_fetch(symbol, start, end)
                    results[symbol] = rows
                except Exception as sym_err:
                    logger.warning(f"Per-symbol fallback for {symbol} also failed: {sym_err}")
                    results[symbol] = None
            return results

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
                is_etf=(self.asset_class == 'etf'),
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
        """Override to use batch fetching (50x faster than per-symbol) + concurrent batches."""
        if backfill_days is not None:
            self._backfill_days = backfill_days

        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        start = time.time()
        symbols = list(symbols)
        mode = f" (backfill {self._backfill_days}d)" if self._backfill_days > 0 else ""
        logger.info(
            "[%s] Starting batch load: %d symbols (batch_size=%d, concurrency=%d)%s",
            self.table_name, len(symbols), self.batch_size, parallelism, mode,
        )

        # Market close detection: For 1d interval near 4 PM ET, ensure yfinance has close data
        if self.interval == "1d":
            if not self._check_market_close_data_available(max_wait_sec=600):
                logger.warning(
                    "[%s] yfinance close data not available yet (API lag). "
                    "Proceeding with load but data may be incomplete. "
                    "If all symbols return empty, failsafe will trigger retry.",
                    self.table_name
                )

        # Timeout guardrails: ECS task timeout is 25200s (7h), Step Functions is 27000s (7.5h)
        # At 50% of timeout (12600s), if < 10% complete, trigger emergency mode
        TASK_TIMEOUT_SEC = 25200
        EMERGENCY_MODE_THRESHOLD = TASK_TIMEOUT_SEC * 0.5  # 12600s = 3.5h
        COMPLETION_THRESHOLD_PCT = 0.10  # 10% complete
        emergency_mode_enabled = False

        # Split into batches
        batches = [symbols[i:i + self.batch_size] for i in range(0, len(symbols), self.batch_size)]
        processed = 0
        batch_times = []  # Track batch execution times for monitoring

        # Process batches with concurrency (increase max to 8 for better throughput on larger batches)
        max_concurrent = min(parallelism, 8)  # Allow up to 8 concurrent batches for faster loading
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {executor.submit(self._load_batch, batch): batch for batch in batches}
            for future in as_completed(futures):
                batch = futures[future]
                batch_start = time.time()
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Batch failed: {e}")

                batch_elapsed = time.time() - batch_start
                batch_times.append(batch_elapsed)
                processed += len(batch)

                # Progress reporting with rate estimation
                elapsed = time.time() - start
                avg_batch_time = sum(batch_times) / len(batch_times) if batch_times else 0
                remaining_batches = len(batches) - (processed // self.batch_size)
                estimated_remaining_sec = remaining_batches * avg_batch_time
                completion_pct = processed / len(symbols) if symbols else 0

                logger.info(
                    "  Progress: %d/%d symbols (%.0f%%) — batch: %.1fs, avg: %.1fs, est. %d more min",
                    processed, len(symbols), (completion_pct * 100),
                    batch_elapsed, avg_batch_time, estimated_remaining_sec / 60
                )

                # TIMEOUT GUARDRAIL: Check if ETA exceeds task timeout
                total_estimated_sec = elapsed + estimated_remaining_sec
                if total_estimated_sec > TASK_TIMEOUT_SEC:
                    logger.error(
                        f"[TIMEOUT_ALERT] ETA ({total_estimated_sec:.0f}s) exceeds task timeout ({TASK_TIMEOUT_SEC}s). "
                        f"Currently at {completion_pct*100:.1f}% completion. Triggering emergency mode."
                    )
                    try:
                        from algo.algo_metrics import MetricsPublisher
                        m = MetricsPublisher()
                        m.put_metric('LoaderTimeoutAlert', 1, unit='Count', dimensions={
                            'table': self.table_name,
                            'progress_pct': f'{completion_pct*100:.0f}',
                            'eta_sec': f'{total_estimated_sec:.0f}',
                        })
                        m.flush()
                    except Exception as metric_err:
                        logger.debug(f"Could not publish timeout metric: {metric_err}")

                    # EMERGENCY MODE: Reduce concurrency and skip lower-priority intervals
                    if not emergency_mode_enabled:
                        emergency_mode_enabled = True
                        logger.warning(
                            f"[EMERGENCY] Reducing parallelism from {max_concurrent} to 1 to finish before timeout"
                        )
                        # Note: Can't dynamically reduce ThreadPoolExecutor workers, but rate limiter
                        # will slow down naturally; next phase should only load 1d prices if available

                # WARN if any batch takes >120s (indicates heavy rate limiting)
                if batch_elapsed > 120:
                    logger.warning(
                        f"  [SLOW BATCH] {len(batch)} symbols took {batch_elapsed:.0f}s — "
                        f"likely yfinance rate limiting. Consider reducing parallelism or checking API status."
                    )

                # EARLY WARNING: At 50% of timeout, ensure we're at least 10% complete
                if elapsed > EMERGENCY_MODE_THRESHOLD and completion_pct < COMPLETION_THRESHOLD_PCT and not emergency_mode_enabled:
                    logger.error(
                        f"[TIMEOUT_WARNING] At {elapsed/60:.1f}min, only {completion_pct*100:.1f}% complete "
                        f"(need {COMPLETION_THRESHOLD_PCT*100:.1f}% by {EMERGENCY_MODE_THRESHOLD/60:.1f}min). "
                        f"Will timeout if pace doesn't improve."
                    )

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
    # CRITICAL: Use higher parallelism for stock_prices_daily to complete in reasonable time
    # Loading 5000 symbols × 3 intervals = 15000+ records; parallelism=2 takes 6+ hours
    # parallelism=8 reduces to ~2 hours while RDS Proxy handles connection pooling
    parallelism = int(os.getenv("LOADER_PARALLELISM", "8"))
    max_symbols_limit = int(os.getenv("LOADER_MAX_SYMBOLS", "0"))  # 0 = no limit (loads all symbols)

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

    # Advisory lock: only one price loader instance at a time.
    _lock_conn = None
    try:
        from utils.db_connection import get_db_connection
        _lock_conn = get_db_connection(timeout=30)
        _lock_conn.autocommit = True
        with _lock_conn.cursor() as _cur:
            _cur.execute("SELECT pg_try_advisory_lock(hashtext(%s)::bigint)", ("stock_prices_daily",))
            acquired = _cur.fetchone()[0]
        if not acquired:
            logger.warning("[MAIN] Skipping: another stock_prices_daily instance already running (advisory lock held)")
            try:
                _lock_conn.close()
            except Exception:
                pass
            _lock_conn = None
            return 0
    except Exception as _lock_err:
        logger.warning("[MAIN] Advisory lock check failed (%s) — proceeding without lock", _lock_err)
        _lock_conn = None

    try:
        if symbols_str:
            symbols = [s.strip().upper() for s in symbols_str.split(",")]
            logger.info(f"[MAIN] Loaded {len(symbols)} symbols from environment")
        else:
            # max_symbols_limit=0 means no limit (loads all ~5000 symbols).
            # ECS task timeout is 12h which is sufficient for all symbols across all intervals.
            limit = max_symbols_limit if max_symbols_limit > 0 else None
            # Use 300s timeout (5 min) for symbol list query under EOD pipeline load
            # Multiple loaders running concurrently can exhaust connection pool; allow extra time
            symbols = get_active_symbols(max_symbols=limit, timeout_secs=300)
            logger.info(f"[MAIN] Loaded {len(symbols)} symbols from database")
            if len(symbols) == 0:
                logger.warning("[MAIN] No symbols found in stock_symbols table - exiting")
                log_loader_execution('loadpricedaily', 'price_daily', 'failed', error_msg='No symbols found', duration_seconds=round(time.time() - start_time, 2))
                return 1
    except Exception as e:
        logger.error(f"[MAIN] Failed to get symbols: {e}", exc_info=True)
        log_loader_execution('loadpricedaily', 'price_daily', 'failed', error_msg=str(e), duration_seconds=round(time.time() - start_time, 2))
        return 1

    # Essential symbols that must be present in price_daily regardless of what stock_symbols contains.
    # stock_symbols excludes ETFs, so these never appear via get_active_symbols().
    # SPY is required by: load_technical_data_daily (Mansfield RS), load_seasonality,
    #   load_market_health_daily breadth check, and algo_market_exposure yield-curve factor.
    # GLD/TLT are used by the correlation matrix endpoint and macro regime logic.
    ESSENTIAL_STOCK_PRICE_DAILY = ['SPY', 'QQQ', 'IWM', 'DIA', 'GLD', 'TLT']

    # Sector ETFs: required by load_sector_performance (YTD returns), SectorHeatMap,
    # and the prices route /api/prices/history/{etf} called by the frontend.
    # These land in etf_price_daily (the prices route falls back to this table).
    ESSENTIAL_ETF_SYMBOLS = [
        'SPY', 'QQQ', 'IWM', 'DIA',            # Index ETFs — IndicesStrip sparklines
        'XLK', 'XLF', 'XLV', 'XLY', 'XLC',     # Sector ETFs — SectorHeatMap + sector_performance
        'XLI', 'XLP', 'XLE', 'XLU', 'XLRE', 'XLB',
        'GLD', 'TLT', 'IVV', 'VXX',             # Macro ETFs — correlation matrix
    ]

    # Run price loader for each interval + asset_class combination
    total_stats = {"symbols_loaded": 0, "symbols_failed": 0, "rows_inserted": 0}
    fail_count = 0

    for asset_class in asset_classes:
        for interval in intervals:
            try:
                # Build per-asset-class symbol list.
                # dict.fromkeys preserves insertion order and deduplicates.
                if asset_class == 'stock':
                    run_symbols = list(dict.fromkeys(symbols + ESSENTIAL_STOCK_PRICE_DAILY))
                    logger.info(f"[MAIN] stock symbols: {len(symbols)} from DB + {len(ESSENTIAL_STOCK_PRICE_DAILY)} essential ETFs = {len(run_symbols)} total")
                else:  # etf
                    # ETF tables (etf_price_daily/weekly/monthly) should only contain ETF symbols,
                    # not the 5000+ non-ETF stocks. Loading all non-ETF stocks into ETF tables
                    # was doubling the data load (~600 extra batches), causing the ECS task to
                    # time out before completing stock price updates for L-Z symbols.
                    run_symbols = list(dict.fromkeys(ESSENTIAL_ETF_SYMBOLS))
                    logger.info(f"[MAIN] etf symbols: {len(run_symbols)} essential ETFs only (sector, index, macro ETFs)")

                loader = PriceLoader(interval=interval, asset_class=asset_class)
                logger.info(f"[MAIN] Starting: interval={interval}, asset_class={asset_class}, parallelism={parallelism}")
                with TimeBlock(f"loadpricedaily_{asset_class}_{interval}"):
                    stats = loader.run(run_symbols, parallelism=parallelism)

                logger.info(f"[MAIN] Completed {asset_class}/{interval}: {stats}")
                total_stats["symbols_loaded"] += stats.get("symbols_processed", 0)
                total_stats["symbols_failed"] += stats.get("symbols_failed", 0)
                total_stats["rows_inserted"] += stats.get("rows_inserted", 0)

                fail_rate = stats.get("symbols_failed", 0) / max(len(run_symbols), 1)
                if fail_rate > 0.10:
                    logger.error(f"Too many failures for {asset_class}/{interval}: {stats['symbols_failed']}/{len(run_symbols)} ({fail_rate*100:.1f}%)")
                    fail_count += 1
                else:
                    logger.info(f"Acceptable failure rate for {asset_class}/{interval}: {stats['symbols_failed']}/{len(run_symbols)} ({fail_rate*100:.1f}%)")

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
    if _lock_conn:
        try:
            _lock_conn.close()
        except Exception:
            pass
    return 0

if __name__ == "__main__":
    sys.exit(main())

