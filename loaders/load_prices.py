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
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from utils.database_context import DatabaseContext
from utils.data_provenance_tracker import DataProvenanceTracker
from utils.data_tick_validator import validate_price_tick
from utils.data_watermark_manager import WatermarkManager
from utils.loader_helpers import get_active_symbols
from monitoring.metrics_context import TimeBlock
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)
# ISSUE #21 FIX: Correlation ID for tracing - use Phase 1 correlation if provided (failsafe), else generate
_correlation_id = os.getenv('PHASE1_CORRELATION_ID') or str(uuid.uuid4())[:8]

class PriceLoader(OptimalLoader):
    """Multi-timeframe price loader. Replaces 4 separate loaders."""

    def __init__(self, interval: str = "1d", asset_class: str = "stock", *args, **kwargs):
        """Initialize with interval (1d/1wk/1mo) and asset class (stock/etf)."""
        assert interval in ("1d", "1wk", "1mo"), f"Invalid interval: {interval}"
        assert asset_class in ("stock", "etf"), f"Invalid asset_class: {asset_class}"

        self.interval = interval
        self.asset_class = asset_class
        self._correlation_id = _correlation_id  # Instance variable for use in all methods
        self.batch_size = 150  # Batch 150 symbols per API call: 5000 symbols = 33-34 calls (3x faster than 50)

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

        # ISSUE #3 FIX: Improved token bucket with per-thread fairness and anti-starvation
        # Rate limit: 160 API calls per minute (safe margin below yfinance's 200/min)
        # Initial burst: 300 tokens (enough for 2 parallel batches of 150 symbols each)
        # Refill: 160 tokens per 60s = 2.67 tokens/sec (conservative to stay under limit)
        # With 6 parallel threads: each thread should get ~27 tokens/sec refill rate
        # Thread fairness: use condition variable to wake waiting threads fairly
        import threading
        self._rate_limit_tokens = 300  # Increased initial burst for 6 parallel threads
        self._rate_limit_max_tokens = 300  # Cap to prevent unlimited accumulation
        self._rate_limit_last_refill = time.time()
        self._rate_limit_refill_rate = 160 / 60  # 160 tokens per 60 seconds = 2.67 per second
        self._rate_limit_lock = threading.Lock()  # Thread-safe token access
        self._rate_limit_event = threading.Condition(self._rate_limit_lock)  # Notify waiting threads when tokens available

        # Circuit breaker: track rate limit errors to detect persistent issues
        # CRITICAL: Threshold now depends on pipeline context (EOD vs morning prep)
        # EOD pipeline (4:05-5:30 PM, 85 min): Use aggressive threshold (180s) to fail fast
        # Morning prep (3:30-9:30 AM, 6h): Use generous threshold (480s) for recovery time
        self._rate_limit_errors = 0
        self._rate_limit_error_start_time = None
        self._is_eod_pipeline = self._detect_eod_pipeline_context()
        self._rate_limit_circuit_break_threshold = 180 if self._is_eod_pipeline else 480  # Dynamic threshold

        # Granular failure tracking for partial batch credit
        # Instead of counting entire batch as 1 failure, track success ratio
        self._batch_success_count = 0  # Symbols successfully fetched in current batch
        self._batch_total_count = 0   # Total symbols in current batch
        self._batch_failure_ratio = 0.0  # Success rate (0.0 = all failed, 1.0 = all succeeded)

        # Market close detection for EOD pipeline (4:05 PM ET start)
        # At 4:05 PM, market just closed at 4:00 PM. yfinance API can lag 5-10 minutes.
        # If running 1d interval at market close, wait for SPY close data before proceeding.
        self._market_close_detected = False
        self._market_close_timeout_count = 0
        self._last_market_close_timeout_time = None

        # ISSUE #14-15 FIX: Differentiate failure causes for targeted remediation
        # Track root cause of failures to apply appropriate fixes:
        # - Market close unavailability: wait and retry (data will become available)
        # - Rate limiting (429): reduce batch size, apply backoff
        # - API lag/timeout: increase timeout, reduce parallelism
        # - Other errors: log and fail
        self._failure_cause = None  # 'market_close', 'rate_limit_429', 'api_lag', 'other'
        self._api_lag_timeouts = 0  # Count of timeout errors (not rate limiting)
        self._api_lag_error_start_time = None  # When API lag started

    def _detect_eod_pipeline_context(self) -> bool:
        """Detect if running during EOD pipeline (4:05-5:30 PM ET) for timing-aware rate limiting.

        Returns True if current time is 4:05 PM ± 2 hours (accounts for slow yfinance lag).
        EOD pipeline has tight deadline (85 min), so we use aggressive rate limiting strategy.
        """
        from datetime import datetime, timezone, timedelta

        now_et = datetime.now(ZoneInfo("America/New_York"))
        eod_start_et = now_et.replace(hour=16, minute=5, second=0, microsecond=0)  # 4:05 PM ET

        # Check if we're within 2 hours of EOD start (accounts for possible scheduler delays)
        time_since_eod_start = (now_et - eod_start_et).total_seconds() / 60
        if -10 < time_since_eod_start < 120:  # -10 min to +120 min relative to 4:05 PM
            logger.info(f"[CONTEXT] Running during EOD pipeline ({time_since_eod_start:.0f} min from 4:05 PM ET), using aggressive rate limiting")
            return True

        logger.debug(f"[CONTEXT] Running during morning/regular hours ({time_since_eod_start:.0f} min from 4:05 PM ET), using conservative rate limiting")
        return False

    def _get_adaptive_batch_size(self) -> int:
        """Calculate adaptive batch size based on context and success rates.

        ISSUE #6 FIX: Be conservative during EOD to avoid Step Function timeout (27000s limit).
        Even with 160/min rate limit, if API lags or rate limiting hits, conservative sizing
        ensures we complete within time window.

        PROACTIVE (EOD pipeline context):
        - If in EOD pipeline and no errors yet: start with batch=50 (conservative)
        - If in EOD pipeline with prior errors: use 20 (very conservative)

        REACTIVE (based on recent success):
        - High success rate (>80%): keep batch size at 100
        - Moderate success (50-80%): reduce to 50
        - Low success (<50%): reduce to 20

        This reduces retry overhead when rate limiting is active while being proactive during EOD.
        """
        # ISSUE #6 FIX: Proactive conservative sizing during EOD to avoid timeout
        # Even though 160/min rate limit theoretically allows batch=150,
        # if API lag or rate limiting persists, conservative batch sizing ensures completion.
        # Worst case: batch=20 × 250 symbols/batch = 12500 API calls at 160/min = ~78 min,
        # well under Step Function timeout (27000s = 450 min).
        if self._is_eod_pipeline and self._batch_total_count == 0:
            logger.info("[BATCH_SIZE] EOD pipeline context: starting with batch=50 (conservative to ensure Step Function completion)")
            return 50  # Start conservative during EOD to protect against timeouts

        if self._is_eod_pipeline and self._rate_limit_errors > 0:
            logger.debug(f"[BATCH_SIZE] EOD pipeline with {self._rate_limit_errors} prior errors, using batch=20 (very conservative)")
            return 20  # Very conservative if we've already hit rate limits during EOD

        # Reactive: Adjust based on recent success rate
        if self._batch_total_count == 0:
            return 100  # Default batch size on first run (non-EOD)

        success_rate = self._batch_success_count / self._batch_total_count

        if success_rate > 0.8:
            return 100  # High success: keep large batches
        elif success_rate > 0.5:
            return 50   # Moderate success: smaller batches
        else:
            return 20   # Low success: very small batches

    def _record_batch_result(self, success_count: int, total_count: int):
        """Record batch success/failure ratio for adaptive retry logic.

        Allows tracking partial success without requiring per-symbol results.
        """
        self._batch_success_count = success_count
        self._batch_total_count = total_count
        self._batch_failure_ratio = 1.0 - (success_count / total_count) if total_count > 0 else 0.0

        if success_count < total_count:
            logger.info(
                f"[BATCH RESULT] Partial success: {success_count}/{total_count} symbols ({success_count/total_count*100:.0f}%). "
                f"Failure ratio: {self._batch_failure_ratio:.2f}. "
                f"Next batch size recommendation: {self._get_adaptive_batch_size()}"
            )

    def _check_market_close_data_available(self, max_wait_sec: int = None) -> bool:
        """Check if SPY close data is available (market close data freshness check).

        EOD pipeline starts at 4:05 PM ET. yfinance API can lag 5-15 minutes after market close (4 PM ET).
        Uses exponential backoff (5s, 10s, 20s, 40s, ...) to avoid hammering the API while waiting for
        data availability.

        Timeout is context-aware:
        - EOD pipeline (4:05-6:00 PM): 1200s (20 min) — still safe within 85-min pipeline window
        - Morning prep (3:30-9:30 AM): 600s (10 min) — market just opened, data should be fresh
        - Other times: 300s (5 min) — should rarely block

        ISSUE #11 FIX: Returns False if timeout and raises RuntimeError to halt loader.
        This prevents the loader from silently proceeding with stale data.
        Phase 1 will catch this failure and trigger failsafe.

        Returns: True if SPY close data available
        Raises: RuntimeError if data cannot be verified (loader should abort)
        """
        if max_wait_sec is None:
            # CRITICAL FIX: Read timeout from algo_config with strict validation
            # Use context-aware defaults: EOD (1200s/20min) vs Morning (600s/10min)
            default_timeout_sec = 1200 if self._is_eod_pipeline else 600
            config_key = 'yfinance_market_close_timeout_eod_sec' if self._is_eod_pipeline \
                else 'yfinance_market_close_timeout_morning_sec'
            config_used = 'default'

            try:
                from utils.database_context import DatabaseContext
                with DatabaseContext("read") as config_cur:
                    config_cur.execute(
                        "SELECT value FROM algo_config WHERE key = %s",
                        (config_key,)
                    )
                    config_result = config_cur.fetchone()
                    if config_result:
                        try:
                            config_value = int(config_result[0])
                            # CRITICAL: Validate timeout is reasonable (1s-1800s)
                            if config_value < 1 or config_value > 1800:
                                logger.warning(
                                    f"[MARKET_CLOSE] ⚠️  Config {config_key}={config_value}s is out of bounds (1-1800s). "
                                    f"Using default {default_timeout_sec}s instead."
                                )
                                max_wait_sec = default_timeout_sec
                                config_used = 'default (config out of bounds)'
                            else:
                                max_wait_sec = config_value
                                logger.info(f"[MARKET_CLOSE] Using configured timeout: {max_wait_sec}s (from {config_key})")
                                config_used = 'configured'
                        except (ValueError, TypeError) as parse_err:
                            logger.warning(
                                f"[MARKET_CLOSE] ⚠️  Config {config_key}={config_result[0]} is not a valid integer. "
                                f"Using default {default_timeout_sec}s instead. Error: {parse_err}"
                            )
                            max_wait_sec = default_timeout_sec
                            config_used = 'default (config invalid)'
                    else:
                        max_wait_sec = default_timeout_sec
                        logger.debug(f"[MARKET_CLOSE] Config key {config_key} not found, using default timeout: {max_wait_sec}s")
                        config_used = 'default (key missing)'
            except Exception as config_err:
                logger.warning(f"[MARKET_CLOSE] Could not read config ({config_err}), using default timeout: {default_timeout_sec}s")
                max_wait_sec = default_timeout_sec
                config_used = 'default (read error)'

            logger.info(f"[MARKET_CLOSE] Using {config_used} timeout: {max_wait_sec}s "
                       f"(pipeline={'EOD' if self._is_eod_pipeline else 'morning'})")
        else:
            logger.debug(f"[MARKET_CLOSE] Using override timeout: {max_wait_sec}s")

        from datetime import datetime, timezone, timedelta
        from zoneinfo import ZoneInfo
        from algo.algo_market_calendar import MarketCalendar
        # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
        today = datetime.now(ZoneInfo("America/New_York")).date()

        # Check if today is a trading day
        if not MarketCalendar.is_trading_day(today):
            logger.info("[MARKET_CLOSE] Today is not a trading day, skipping close data check")
            return True

        # Check if we're within 45 minutes after market close (4:00 PM ET ± 45 min = 3:15 PM - 4:45 PM)
        now_et = datetime.now(ZoneInfo("America/New_York"))
        market_close_et = now_et.replace(hour=16, minute=0, second=0, microsecond=0)  # 4 PM ET
        minutes_after_close = (now_et - market_close_et).total_seconds() / 60

        # If we're more than 45 minutes after market close, assume data is available (yfinance lag max 15 min)
        if minutes_after_close > 45:
            logger.info(f"[MARKET_CLOSE] {minutes_after_close:.0f}min after market close, data should be available")
            return True

        # If we're before market close, skip (early run or different time zone)
        if minutes_after_close < 0:
            logger.info(f"[MARKET_CLOSE] Before market close ({minutes_after_close:.0f}min), skipping check")
            return True

        # We're 0-45 minutes after market close - verify SPY data with exponential backoff
        logger.info(f"[MARKET_CLOSE] {minutes_after_close:.1f}min after close at 4 PM ET, checking yfinance for SPY data...")

        start_time = time.time()
        attempt = 0
        backoff_sec = 5  # Start with 5s, then exponential: 10s, 20s, 40s, ...
        last_error_type = None
        last_error_msg = None

        while time.time() - start_time < max_wait_sec:
            attempt += 1
            try:
                # Try to fetch SPY 1d data from yfinance
                spy_data = self.router.fetch_ohlcv_interval('SPY', today, today + timedelta(days=1), '1d')
                if spy_data:
                    latest_row = spy_data[-1] if spy_data else None
                    if latest_row and latest_row.get('close'):
                        elapsed = time.time() - start_time
                        logger.info(f"[MARKET_CLOSE] ✓ Data available after {elapsed:.1f}s (attempt {attempt})")
                        # Emit success metric
                        try:
                            from algo.algo_metrics import MetricsPublisher
                            metrics = MetricsPublisher()
                            metrics.put_metric('MarketCloseDataAvailable', 1, unit='Count', dimensions={'Status': 'success'})
                            metrics.flush()
                        except Exception:
                            pass
                        return True
            except Exception as e:
                last_error_type = type(e).__name__
                last_error_msg = str(e)[:200]  # Truncate for logging
                error_str = str(e).lower()
                is_timeout = "timeout" in error_str or "connect" in error_str or "read timed" in error_str
                is_rate_limit = "429" in error_str or "too many" in error_str or "rate" in error_str

                log_level = "warning" if is_rate_limit else ("warning" if is_timeout else "debug")
                logger.log(
                    getattr(logging, log_level.upper()) if log_level in ["debug", "warning", "error"] else logging.DEBUG,
                    f"[MARKET_CLOSE] Attempt {attempt}: {last_error_type} " +
                    (f"(rate limit)" if is_rate_limit else f"(timeout)" if is_timeout else f"(other)") +
                    f" - {last_error_msg}"
                )

            # Calculate exponential backoff wait time
            wait_remaining = max_wait_sec - (time.time() - start_time)
            wait_time = min(backoff_sec, wait_remaining)

            if wait_time > 0 and wait_remaining > 0:
                logger.debug(f"[MARKET_CLOSE] Waiting {wait_time:.0f}s before retry {attempt + 1}...")
                time.sleep(wait_time)
                backoff_sec = min(backoff_sec * 2, 60)  # Cap at 60s per retry

        # Timeout - data not available, HALT loader with explicit error (ISSUE #11 FIX)
        elapsed = time.time() - start_time

        # ISSUE #7 FIX: Track consecutive market close timeouts to detect API degradation
        now = time.time()
        if self._last_market_close_timeout_time and (now - self._last_market_close_timeout_time) < 86400:  # Within 24 hours
            self._market_close_timeout_count += 1
        else:
            self._market_close_timeout_count = 1
        self._last_market_close_timeout_time = now

        # Alert if this is repeated failure (3+ times in 24h = API degradation pattern)
        if self._market_close_timeout_count >= 3:
            alert_msg = (
                f"ALERT: Market close data unavailable {self._market_close_timeout_count} times in 24h. "
                f"Possible yfinance API degradation. Check status page and consider switching data provider."
            )
            logger.critical(f"[{self._correlation_id}] {alert_msg}")
            try:
                from algo.algo_alerts import AlertManager
                AlertManager().critical(alert_msg)
            except Exception:
                pass

        # Emit failure metric with diagnostic info
        try:
            from algo.algo_metrics import MetricsPublisher
            metrics = MetricsPublisher()
            metrics.put_metric('MarketCloseDataAvailable', 0, unit='Count',
                             dimensions={'Status': 'timeout', 'LastError': last_error_type or 'unknown', 'ConsecutiveCount': str(self._market_close_timeout_count)})
            metrics.flush()
        except Exception:
            pass

        # Determine root cause for clearer diagnostics
        last_error_lower = (last_error_msg or '').lower()
        is_rate_limit = "429" in last_error_lower or "too many" in last_error_lower or "rate" in last_error_lower
        root_cause = "yfinance rate limiting" if is_rate_limit else "yfinance API lag/unavailability"

        fallback_threshold = 1800 if self._is_eod_pipeline else 3600
        if elapsed < fallback_threshold:
            logger.warning(
                f"[{self._correlation_id}] [MARKET_CLOSE] ⚠️  Market close data NOT available after {elapsed:.0f}s ({attempt} attempts). "
                f"Root cause: {root_cause}. Allowing FALLBACK: Loader will proceed with historical data (prior day) instead of halting. "
                f"[Consecutive timeouts: {self._market_close_timeout_count}/24h]"
            )
            return False
        else:
            error_msg = (
            f"Market close data NOT available after {elapsed:.0f}s ({attempt} attempts). "
            f"Root cause: {root_cause} | Last error: {last_error_type} - {last_error_msg or 'no message'}. "
            f"Cannot load prices without market close data. Aborting to avoid stale price data. "
            f"Phase 1 will trigger failsafe when data becomes available. "
            f"Check yfinance API status and RDS connection pool health. "
            f"[Consecutive timeouts: {self._market_close_timeout_count}/24h]"
        )
        logger.error(f"[{self._correlation_id}] [MARKET_CLOSE] ✗ {error_msg}")
        raise RuntimeError(error_msg)

    def _rate_limit_wait(self, tokens_needed: int = 1) -> None:
        """ISSUE #3: Thread-safe token bucket with per-thread fairness.

        Tokens refill at 160 per 60 seconds (2.67/sec). Supports 6 parallel threads.
        Uses Condition variable to wake waiting threads fairly when tokens become available.
        Prevents starvation where one thread monopolizes tokens while others wait.
        """
        import time

        while True:
            with self._rate_limit_event:  # Use Condition variable for fairness
                now = time.time()
                elapsed = now - self._rate_limit_last_refill
                # Refill tokens based on elapsed time (capped at max)
                self._rate_limit_tokens = min(self._rate_limit_max_tokens,
                                              self._rate_limit_tokens + elapsed * self._rate_limit_refill_rate)
                self._rate_limit_last_refill = now

                if self._rate_limit_tokens >= tokens_needed:
                    # Sufficient tokens, consume and return
                    self._rate_limit_tokens -= tokens_needed
                    return
                else:
                    # Insufficient tokens; calculate wait time for condition variable
                    tokens_short = tokens_needed - self._rate_limit_tokens
                    wait_sec = tokens_short / self._rate_limit_refill_rate
                    # Cap wait time to 1.0s to allow checking for other threads' progress
                    wait_sec = min(wait_sec, 1.0)

            # Wait outside the lock using condition variable (wakes fairly when notified)
            if wait_sec > 0.01:  # Only log if waiting >10ms
                logger.debug(f"Rate limit: waiting {wait_sec:.2f}s for {tokens_needed} tokens (fair queue)")
            # Note: Condition.wait() releases lock while waiting, allowing other threads to proceed
            with self._rate_limit_event:
                self._rate_limit_event.wait(timeout=wait_sec)  # Wake on timeout or notify()

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch OHLCV from yfinance at specified interval."""
        from algo.algo_market_calendar import MarketCalendar
        from datetime import datetime, timezone, timedelta as td

        # CRITICAL: Use ET (trading hours), not UTC, to determine end date.
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
        # yfinance end date is EXCLUSIVE: pass today+1 so today's trading data is always fetchable
        end = now_et.date() + timedelta(days=1)

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

        Fallback: If batch API fails, retry with smaller batch size. Only falls back
        to per-symbol for large rate-limiting errors.

        Uses adaptive batch sizing based on recent success rates to reduce retries.
        """
        from algo.algo_market_calendar import MarketCalendar
        from datetime import datetime, timezone, timedelta as td

        # CRITICAL: Use ET (trading hours), not UTC, to determine end date.
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
        # yfinance end date is EXCLUSIVE: to fetch May 29 data we must pass end=May 30.
        # Use today+1 so today's data (if it's a trading day) is always included.
        end = now_et.date() + timedelta(days=1)

        if since is None:
            start = end - timedelta(days=101)
        else:
            start = since

        if start >= end:
            return {s: None for s in symbols}

        # Batch fetch with adaptive batch sizing based on recent success rates
        # If recent batches had high success, use full batch. If rate limited recently, use smaller batches.
        adaptive_batch_size = min(len(symbols), self._get_adaptive_batch_size())
        logger.debug(f"[FETCH] {len(symbols)} symbols, adaptive batch size: {adaptive_batch_size} "
                    f"(based on {self._batch_total_count} recent batches, {self._batch_success_count} successful)")

        return self._fetch_with_fallback(symbols, start, end, batch_size=adaptive_batch_size, attempt=0)

    def _fetch_with_fallback(self, symbols: List[str], start: date, end: date, batch_size: int, attempt: int = 0, max_attempts: int = 3, elapsed_sec: float = 0):
        """Fetch with progressive batch size reduction and adaptive retry with jitter.

        ISSUE #6 FIX: Add upper bound check - if batch_size=1 and still rate limited, fail immediately.
        Attempts: full batch → split in half → quarter size → give up.
        Includes randomized jitter to avoid thundering herd and circuit breaker for persistent errors.

        CRITICAL: Prevents infinite batch reduction + timeout cascade by tracking elapsed time.
        If batch=1 and elapsed > threshold, fail immediately rather than waiting indefinitely.
        """
        import time
        import random

        # ISSUE #6 FIX: Prevent infinite batch reduction and Step Function timeout
        # Track elapsed time to detect when we're spending too long on rate limiting
        if elapsed_sec is None:
            elapsed_sec = 0

        # CRITICAL BOUND: If batch_size=1 and rate limiting persists, give up per pipeline context
        # EOD (85 min deadline): 3 min max wait at batch=1 to fail fast and trigger failsafe
        # Morning (450 min deadline): 10 min max wait at batch=1 to allow recovery
        max_single_batch_wait = 180 if self._is_eod_pipeline else 600
        if batch_size == 1 and elapsed_sec > max_single_batch_wait:
            logger.critical(
                f"[BATCH FETCH TIMEOUT] Batch=1 with {elapsed_sec/60:.1f}min elapsed. "
                f"Failing immediately to prevent Step Function timeout. yfinance severely degraded."
            )
            return {s: None for s in symbols}

        # ISSUE #6 FIX: If we've shrunk to batch_size=1 and still rate limiting, give up immediately
        # This prevents infinite reduction and timeout cascade
        if batch_size <= 0 or attempt >= max_attempts:
            logger.warning(f"[BATCH FETCH] Giving up after {attempt} attempts with batch_size={batch_size}, elapsed {elapsed_sec:.0f}s")
            return {s: None for s in symbols}

        # Issue #20 FIX: At batch=1, try longer wait before giving up
        if batch_size == 1 and self._rate_limit_errors > 3:
            # Try with exponential backoff + longer wait times (up to 10 min) at batch=1
            max_batch1_wait = 600  # 10 minutes for batch=1 final attempts
            if error_duration := (time.time() - self._rate_limit_error_start_time) if self._rate_limit_error_start_time else 0:
                remaining_wait = max(0, max_batch1_wait - error_duration)
                if remaining_wait > 60:  # Only if we have >1 min left
                    logger.warning(
                        f"[BATCH=1 BACKOFF] Batch size at minimum with {self._rate_limit_errors} errors. "
                        f"Attempting longer exponential backoff ({remaining_wait:.0f}s remaining) before final failure."
                    )
                    # Don't return yet - let the normal retry loop below handle the backoff
                elif remaining_wait > 0:
                    logger.warning(f"[BATCH=1] Rate limiting at batch=1. Last chance with {remaining_wait:.0f}s remaining before timeout.")

            # If we've exhausted backoff time, fail
            if error_duration and error_duration > max_batch1_wait:
                logger.critical(
                    f"[BATCH FETCH ABORT] Batch size at minimum (1 symbol) with {self._rate_limit_errors} rate limit errors "
                    f"persisting for {error_duration/60:.1f}min. yfinance API severely degraded. Failing to prevent timeout."
                )
                try:
                    from algo.algo_metrics import MetricsPublisher
                    m = MetricsPublisher()
                    m.put_metric('BatchFetchMinimumSizeReached', 1, unit='Count', dimensions={
                        'table': self.table_name,
                        'error_count': str(self._rate_limit_errors)
                    })
                    m.flush()
                except Exception:
                    pass
                return {s: None for s in symbols}

        # Check circuit breaker: if rate limiting has persisted for > threshold, try smaller batch size
        # Issue #6: Instead of failing completely, reduce batch size to avoid timeout
        if self._rate_limit_error_start_time is not None:
            error_duration = time.time() - self._rate_limit_error_start_time
            if error_duration > self._rate_limit_circuit_break_threshold:
                logger.warning(
                    f"[CIRCUIT BREAKER] Rate limiting persisted for {error_duration/60:.1f} minutes ({error_duration:.0f}s). "
                    f"Attempting to continue with smaller batch size instead of failing completely."
                )

                # Try with progressively smaller batch sizes (10, 5, 1)
                # ISSUE #6 FIX: Stop trying if already spent too long on rate limiting
                if elapsed_sec > max_single_batch_wait * 0.8:  # 8 minutes threshold
                    logger.warning(
                        f"[CIRCUIT BREAKER] Rate limiting {elapsed_sec/60:.1f}min, approaching timeout. "
                        f"Skipping reduced batch size attempts, failing batch immediately."
                    )
                    return {s: None for s in symbols}

                reduced_batch_sizes = [10, 5, 1]
                for reduced_size in reduced_batch_sizes:
                    if reduced_size >= batch_size:
                        continue  # Skip if not smaller than current

                    logger.info(f"[CIRCUIT BREAKER] Retrying with reduced batch size: {reduced_size} (was {batch_size}), elapsed {elapsed_sec:.0f}s")
                    reduced_attempt = self._fetch_with_fallback(
                        symbols, start, end, batch_size=reduced_size, attempt=attempt + 1, max_attempts=max_attempts
                    )
                    if any(v is not None for v in reduced_attempt.values()):
                        logger.info(f"[CIRCUIT BREAKER] ✓ Partial success with batch={reduced_size}")
                        return reduced_attempt

                # If all reduced sizes failed, emit alert and fail gracefully
                logger.critical(
                    f"[CIRCUIT BREAKER] Rate limiting persisted {error_duration/60:.1f}min despite batch size reduction. "
                    f"yfinance API experiencing degradation. Failing batch. Check yfinance API status."
                )
                try:
                    from algo.algo_alerts import AlertManager
                    alerts = AlertManager()
                    alerts.send_position_alert(
                        'YFINANCE',
                        'RATE_LIMIT_CIRCUIT_BREAK',
                        f'yfinance rate limiting persisted {error_duration/60:.1f}min despite batch reduction. '
                        f'EOD pipeline may be impacted. {self._rate_limit_errors} rate limit errors detected.',
                        {'duration_seconds': error_duration, 'error_count': self._rate_limit_errors}
                    )
                except Exception as alert_err:
                    logger.debug(f"Could not send rate limit alert: {alert_err}")
                return {s: None for s in symbols}

        try:
            self._rate_limit_wait(tokens_needed=1)
            result = self.router.fetch_ohlcv_batch(symbols, start, end, interval=self.interval)
            if result:
                # Success: reset rate limit error tracking
                self._rate_limit_errors = 0
                self._rate_limit_error_start_time = None
                return result
        except Exception as e:
            error_str = str(e).lower()
            is_rate_limit = "rate" in error_str or "429" in error_str or "too many" in error_str

            if is_rate_limit:
                # Track rate limit errors for circuit breaker
                self._rate_limit_errors += 1
                if self._rate_limit_error_start_time is None:
                    self._rate_limit_error_start_time = time.time()
                    logger.warning(
                        f"[RATE_LIMIT] First rate limiting error detected (error #{self._rate_limit_errors}). "
                        f"Circuit will break if persists >5 minutes. Monitoring yfinance API recovery."
                    )

                # Emit CloudWatch metric for rate limit occurrence
                try:
                    from algo.algo_metrics import MetricsPublisher
                    metrics = MetricsPublisher()
                    metrics.add_metric(
                        'RateLimitErrors',
                        1,
                        unit='Count',
                        dimensions={'Loader': 'stock_prices_daily'}
                    )
                    metrics.flush()
                except Exception:
                    pass

                # ISSUE #6 CRITICAL: Abort if batch=20 or smaller in EOD pipeline with multiple rate limit errors
                # Prevents infinite retry loop at very small batch sizes
                if self._is_eod_pipeline and batch_size <= 20 and self._rate_limit_errors >= 3:
                    logger.critical(
                        f"[BATCH FETCH ABORT] Batch={batch_size} with {self._rate_limit_errors} rate limit errors. "
                        f"yfinance severely degraded. Failing to prevent timeout cascade."
                    )
                    return {s: None for s in symbols}

                # Calculate adaptive backoff with jitter
                base_wait = min(60, (2 ** attempt) * 5)  # Exponential: 5s, 10s, 20s, 40s, 80s (cap at 60s)
                jitter = random.uniform(0.8, 1.2)  # ±20% jitter to avoid thundering herd
                wait_time = base_wait * jitter

                new_batch_size = max(1, batch_size // 2)
                error_duration = time.time() - self._rate_limit_error_start_time if self._rate_limit_error_start_time else 0
                # ISSUE #6 FIX: Track total elapsed time to prevent infinite retries
                total_elapsed = elapsed_sec + error_duration + wait_time
                logger.warning(
                    f"[BATCH FETCH] Rate limited (attempt {attempt+1}/{max_attempts}, error #{self._rate_limit_errors}, "
                    f"duration {error_duration:.0f}s, total elapsed {total_elapsed:.0f}s). "
                    f"Batch {batch_size} → {new_batch_size}, waiting {wait_time:.1f}s (base {base_wait}s + jitter)..."
                )
                time.sleep(wait_time)

                # Split batch and fetch recursively, tracking partial success
                results = {}
                successful_chunks = 0
                for i in range(0, len(symbols), new_batch_size):
                    chunk = symbols[i:i+new_batch_size]
                    # ISSUE #6 FIX: Pass elapsed_sec to prevent timeout cascade
                    chunk_results = self._fetch_with_fallback(chunk, start, end, new_batch_size, attempt + 1, max_attempts, elapsed_sec=total_elapsed)
                    results.update(chunk_results)
                    # Count chunk as successful if it returned non-None results for any symbols
                    if any(v is not None for v in chunk_results.values()):
                        successful_chunks += 1

                # Record partial success for adaptive batch sizing
                total_chunks = (len(symbols) + new_batch_size - 1) // new_batch_size
                self._record_batch_result(successful_chunks, total_chunks)

                return results
            else:
                # ISSUE #6 FIX: Transient error (network, timeout): differentiate error types
                # Timeout errors likely indicate API slowness, not rate limiting
                # Network/connection errors indicate infrastructure issues
                error_str = str(e).lower()
                is_timeout = "timeout" in error_str or "timed out" in error_str
                is_connection = any(x in error_str for x in ["connection", "reset", "broken", "closed"])

                error_type = "timeout (API slowness)" if is_timeout else "connection (network)" if is_connection else "other transient"

                base_wait = min(30, 2 ** attempt)
                jitter = random.uniform(0.9, 1.1)  # ±10% jitter
                wait_time = base_wait * jitter
                logger.warning(
                    f"[BATCH FETCH] Transient {error_type} error (attempt {attempt+1}/{max_attempts}, elapsed {elapsed_sec:.0f}s): {e}. "
                    f"Retrying {len(symbols)} symbols with same batch_size={batch_size} in {wait_time:.1f}s... "
                    f"(Note: batch size not reduced for timeouts — if API fundamentally slow, increasing wait time not batch reduction)"
                )
                time.sleep(wait_time)
                return self._fetch_with_fallback(symbols, start, end, batch_size, attempt + 1, max_attempts, elapsed_sec=elapsed_sec + wait_time)

    def _try_fetch(self, symbol: str, start: date, end: date, max_retries: int = 5):
        """Try to fetch data from yfinance with retry logic for transient failures."""
        import time
        import random

        for attempt in range(max_retries):
            try:
                return self.router.fetch_ohlcv_interval(symbol, start, end, self.interval)
            except Exception as e:
                error_str = str(e).lower()
                # Rate limit errors - retry with exponential backoff + jitter
                if "rate" in error_str or "429" in error_str or "too many" in error_str:
                    if attempt < max_retries - 1:
                        base_wait = min(120, (2 ** attempt) * 5)  # 5s, 10s, 20s, 40s, 80s, 120s
                        jitter = random.uniform(0.9, 1.1)  # ±10% jitter
                        wait_time = base_wait * jitter
                        logger.warning(
                            f"[{symbol}] Rate limited (attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {wait_time:.1f}s (base {base_wait}s)..."
                        )
                        time.sleep(wait_time)
                        continue
                    logger.warning(f"[{symbol}] Rate limited after {max_retries} attempts, giving up")
                    return None
                # Network/timeout errors - retry with backoff + jitter
                if any(x in error_str for x in ["timeout", "json", "parse", "connection", "reset"]):
                    if attempt < max_retries - 1:
                        base_wait = 2 ** attempt
                        jitter = random.uniform(0.8, 1.2)  # ±20% jitter for network errors
                        wait_time = base_wait * jitter
                        logger.warning(
                            f"[{symbol}] Transient error (attempt {attempt + 1}/{max_retries}): {e}, "
                            f"retrying in {wait_time:.1f}s..."
                        )
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
        non_trading_filtered = 0
        parse_errors = 0

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
                    non_trading_filtered += 1
                    logger.debug(f"[{row.get('symbol')}] {row_date}: Non-trading day, rejecting")
                    continue
            except (ValueError, TypeError) as e:
                parse_errors += 1
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

        # Log data quality summary for this batch
        if non_trading_filtered > 0 or parse_errors > 0:
            total_input = len(rows)
            filtered_pct = (non_trading_filtered + parse_errors) / total_input * 100 if total_input > 0 else 0
            symbol = rows[0].get('symbol', 'unknown') if rows else 'unknown'

            if filtered_pct > 5:
                logger.warning(
                    f"[{symbol}] High rejection rate: {non_trading_filtered} non-trading-day + {parse_errors} parse errors "
                    f"out of {total_input} rows ({filtered_pct:.1f}%). This may indicate bad data or API issues."
                )
            else:
                logger.info(
                    f"[{symbol}] Filtered {non_trading_filtered} non-trading-day + {parse_errors} parse errors "
                    f"from {total_input} rows ({filtered_pct:.1f}%)"
                )

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
        self._stats["start_time"] = datetime.fromtimestamp(start)  # ISSUE #2: Record execution start
        symbols = list(symbols)
        mode = f" (backfill {self._backfill_days}d)" if self._backfill_days > 0 else ""
        logger.info(
            "[%s] [%s] Starting batch load: %d symbols (batch_size=%d, concurrency=%d)%s",
            self._correlation_id, self.table_name, len(symbols), self.batch_size, parallelism, mode,
        )

        # Market close detection: For 1d interval near 4 PM ET, ensure yfinance has close data
        # ISSUE #2 & #11 FIX: Check market close data and HALT if unavailable (raises RuntimeError)
        market_close_warning = False
        fallback_to_prior_day = False
        if self.interval == "1d":
            try:
                # ISSUE #1 FIX: Check market close data availability
                # Returns True if available, False if timeout (non-fatal - proceed with available data)
                # Raises RuntimeError for auth errors (fatal - abort loader)
                market_close_available = self._check_market_close_data_available()  # Uses dynamic timeout
                if market_close_available:
                    logger.debug("[MARKET_CLOSE] ✓ Market close data available, proceeding with load")
                else:
                    logger.warning("[MARKET_CLOSE] ⚠️  Market close data NOT available (timeout), but proceeding with whatever data exists. "
                                  "Phase 1 will detect staleness via execution_completed timestamp.")
            except RuntimeError as market_close_err:
                # Market close check hit a fatal error (auth, configuration, etc) - abort loader
                logger.error(f"[{self._correlation_id}] [MARKET_CLOSE] Loader aborting (fatal error): {str(market_close_err)}")
                try:
                    from algo.algo_metrics import MetricsPublisher
                    m = MetricsPublisher()
                    m.put_metric('MarketCloseDataUnavailable', 1, unit='Count', dimensions={
                        'table': self.table_name,
                        'interval': self.interval,
                    })
                    m.flush()
                except Exception as metric_err:
                    logger.debug(f"Could not publish market close metric: {metric_err}")

                # Record market close failure for Phase 1 detection
                try:
                    import boto3
                    dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                    state_table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
                    state_table = dynamodb.Table(state_table_name)
                    state_table.put_item(Item={
                        'state_key': 'market_close_failure',
                        'failure_time': time.time(),
                        'reason': str(market_close_err)[:200],
                        'loader': 'stock_prices_daily',
                        'ttl': int(time.time()) + 7200,  # 2-hour TTL
                    })
                except Exception as ddb_err:
                    logger.debug(f"[MARKET_CLOSE] Could not record failure in DynamoDB: {ddb_err}")

                # ISSUE #2 & #8 FIX: Use centralized cache invalidation which marks cache as poisoned on failure
                # This ensures Phase 1 skips cache even if invalidation fails (via invalidation_failed flag)
                # CRITICAL: If cache invalidation fails completely, this raises RuntimeError to halt the loader
                try:
                    _invalidate_phase1_cache()
                except RuntimeError as cache_fail:
                    logger.critical(f"[MARKET_CLOSE] Cache invalidation FAILED (both deletion and poisoning failed). HALTING loader. Error: {cache_fail}")
                    raise

                # Return empty results - Phase 1 will detect stale data and trigger failsafe
                logger.warning(f"[MARKET_CLOSE] Loader aborting with empty results. Phase 1 will trigger failsafe.")
                return {'loaded': 0, 'failed': len(symbols), 'empty': len(symbols), 'table': self.table_name, 'market_close_failure': True}

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

                # ISSUE #3 FIX: Circuit breaker for rate limit cascade
                # If batch size has been reduced due to rate limiting AND execution time is getting long,
                # halt early instead of continuing to retry indefinitely.
                # This prevents the scenario: batch 150→20 at 7 AM → execution time becomes 80min→400min → misses 9:30 AM deadline
                current_batch_size = self._get_adaptive_batch_size()
                # Context-aware threshold: EOD (85 min total) needs to fail fast (~30 min), morning (450 min total) can wait (~2 hours)
                circuit_break_threshold_sec = 30 * 60 if self._is_eod_pipeline else 120 * 60
                if current_batch_size < 100 and elapsed > circuit_break_threshold_sec:  # Batch reduced AND threshold exceeded
                    pipeline_context = "EOD (85-min window)" if self._is_eod_pipeline else "Morning prep (450-min window)"
                    projected_total_sec = (elapsed / completion_pct) if completion_pct > 0 else 0
                    logger.critical(
                        f"[CIRCUIT_BREAKER] {pipeline_context}: Rate limit cascade detected! "
                        f"Batch size reduced to {current_batch_size} (from 150) after {elapsed/60:.0f}min. "
                        f"Only {completion_pct*100:.0f}% complete. "
                        f"Projected total execution: {projected_total_sec/60:.0f}min (would exceed deadline). "
                        f"HALTING to trigger failsafe."
                    )
                    try:
                        from algo.algo_metrics import MetricsPublisher
                        m = MetricsPublisher()
                        m.put_metric('RateLimitCircuitBreaker', 1, unit='Count', dimensions={
                            'table': self.table_name,
                            'batch_size': str(current_batch_size),
                            'elapsed_min': str(int(elapsed / 60)),
                            'completion_pct': f'{completion_pct*100:.0f}',
                        })
                        m.flush()
                    except Exception as metric_err:
                        logger.debug(f"Could not publish circuit breaker metric: {metric_err}")

                    # Return with partial data - Phase 1 will detect incomplete load and trigger failsafe
                    logger.warning(f"[CIRCUIT_BREAKER] Returning with {processed}/{len(symbols)} symbols loaded. "
                                 f"Phase 1 will detect incomplete load and trigger failsafe.")
                    self._stats["duration_sec"] = round(time.time() - start, 2)
                    self._stats["rate_limit_errors"] = self._rate_limit_errors
                    return {
                        'loaded': processed,
                        'failed': len(symbols) - processed,
                        'table': self.table_name,
                        'circuit_breaker_triggered': True,
                        'batch_size_reduced': current_batch_size,
                        'elapsed_min': int(elapsed / 60),
                    }

        self._stats["duration_sec"] = round(time.time() - start, 2)

        # Add rate limiting metrics
        self._stats["rate_limit_errors"] = self._rate_limit_errors
        if self._rate_limit_error_start_time:
            error_duration_sec = time.time() - self._rate_limit_error_start_time
            self._stats["rate_limit_error_duration_sec"] = round(error_duration_sec, 1)
        else:
            self._stats["rate_limit_error_duration_sec"] = 0

        logger.info(
            "[%s] [%s] Done. fetched=%d dedup_skip=%d quality_drop=%d inserted=%d "
            "(processed=%d skipped_wm=%d failed=%d) %.1fs sources=%s rate_limit_errors=%d",
            self._correlation_id, self.table_name,
            self._stats["rows_fetched"],
            self._stats["rows_dedup_skipped"],
            self._stats["rows_quality_dropped"],
            self._stats["rows_inserted"],
            self._stats["symbols_processed"],
            self._stats["symbols_skipped_by_watermark"],
            self._stats["symbols_failed"],
            self._stats["duration_sec"],
            self._stats["source_distribution"],
            self._rate_limit_errors,
        )

        try:
            from algo.algo_metrics import MetricsPublisher
            with MetricsPublisher() as m:
                m.put_loader_result(self.table_name, self._stats)
                # Publish rate limiting metrics separately if there were errors
                if self._rate_limit_errors > 0:
                    m.put_metric('RateLimitErrors', self._rate_limit_errors, unit='Count', dimensions={
                        'table': self.table_name,
                        'interval': self.interval,
                    })
                    if self._stats.get("rate_limit_error_duration_sec", 0) > 0:
                        m.put_metric('RateLimitErrorDuration', self._stats["rate_limit_error_duration_sec"],
                                    unit='Seconds', dimensions={
                                        'table': self.table_name,
                                        'interval': self.interval,
                                    })
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

            # ISSUE #2 FIX: Track completion percentage and mark INCOMPLETE if <95%
            symbols_expected = len(symbols) if symbols else 1
            symbols_successfully_loaded = self._stats.get("symbols_processed", 0)
            completion_pct = (symbols_successfully_loaded / symbols_expected * 100) if symbols_expected > 0 else 100.0

            # Determine status: INCOMPLETE if coverage <95%, else COMPLETED
            loader_status = 'COMPLETED'
            if completion_pct < 95:
                loader_status = 'INCOMPLETE'
                logger.warning(
                    f"[{self.table_name}] Load completed but INCOMPLETE: "
                    f"{symbols_successfully_loaded}/{symbols_expected} symbols ({completion_pct:.1f}%) — "
                    f"Phase 1 will detect this and trigger failsafe retry"
                )

            with DatabaseContext('write') as cur:
                cur.execute(
                    "DELETE FROM data_loader_status WHERE table_name = %s",
                    (self.table_name,),
                )
                cur.execute(
                    "INSERT INTO data_loader_status "
                    "(table_name, row_count, latest_date, last_updated, status, "
                    "completion_pct, symbol_count, symbols_loaded, execution_started, execution_completed) "
                    "VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s)",
                    (self.table_name, total_rows, latest_date, loader_status,
                     completion_pct, symbols_expected, symbols_successfully_loaded,
                     self._stats.get("start_time"), datetime.now()),
                )

            # ISSUE #22 FIX: Invalidate Phase 1 data_loader_status cache on completion
            # Ensures Phase 1 detects updated loader status immediately, not after cache TTL
            try:
                from zoneinfo import ZoneInfo
                import os
                import boto3

                # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
                cache_date = datetime.now(ZoneInfo("America/New_York")).date()
                cache_key = f"data_loader_status-{cache_date.isoformat()}"
                cache_table_name = os.getenv('CACHE_TABLE', 'algo_phase1_cache')

                dynamodb = boto3.resource('dynamodb')
                cache_table = dynamodb.Table(cache_table_name)
                cache_table.delete_item(Key={'cache_key': cache_key})
                logger.debug(f"[CACHE INVALIDATION] Invalidated Phase 1 cache for {cache_key}")
            except Exception as cache_err:
                logger.debug(f"[CACHE INVALIDATION] Could not invalidate cache: {cache_err}")
        except Exception as e:
            logger.warning(f"Failed to update data_loader_status for {self.table_name}: {e}")

        return self._stats

    def _load_batch(self, symbols: List[str]) -> None:
        """Load a batch of symbols using batch API fetch (50x reduction in API calls)."""
        wm_store = self._get_watermark()

        # Determine the watermark date for all symbols in batch
        # (simplified: use same date for all, finest-grained would be per-symbol)
        if self._backfill_days > 0:
            # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
            previous_date = (datetime.now(ZoneInfo("America/New_York")).date() - timedelta(days=self._backfill_days))
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
                logger.debug(f"[{self.table_name}] {symbol}: No rows fetched (watermark current), skipping")
                self._stats["symbols_skipped_by_watermark"] += 1
                self._stats["symbols_processed"] += 1  # Count as processed (no new data needed, not a failure)
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

def _invalidate_phase1_cache():
    """Invalidate Phase 1 cache to force fresh status check on next run.

    Called on loader failure to ensure Phase 1 doesn't use stale cached data.
    CRITICAL: If invalidation fails, marks cache with 'invalidation_failed' flag
    so Phase 1 knows not to use it. If that also fails, raises RuntimeError to
    halt the loader and prevent silent stale-data use.

    ISSUE #2 FIX: Three-tier approach:
    1. Try to delete cache (best case)
    2. If delete fails, mark as poisoned so Phase 1 skips it
    3. If both fail, raise RuntimeError to halt loader immediately
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import boto3

    # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
    try:
        cache_date = datetime.now(ZoneInfo("America/New_York")).date()
        cache_key = f"data_loader_status-{cache_date.isoformat()}"
        cache_table_name = os.getenv('CACHE_TABLE', 'algo_phase1_cache')
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        cache_table = dynamodb.Table(cache_table_name)

        try:
            # Step 1: Try direct deletion
            cache_table.delete_item(Key={'cache_key': cache_key})
            logger.info(f"[CACHE INVALIDATION] ✓ Successfully deleted Phase 1 cache: {cache_key}")
            return
        except Exception as delete_err:
            logger.error(f"[CACHE INVALIDATION] ✗ DELETE FAILED: {type(delete_err).__name__}: {delete_err}. Attempting cache poisoning...")

        # Step 2: If delete failed, try to poison the cache so Phase 1 knows not to use it
        try:
            cache_table.update_item(
                Key={'cache_key': cache_key},
                UpdateExpression='SET invalidation_failed = :true, poisoned_at = :now',
                ExpressionAttributeValues={':true': True, ':now': time.time()}
            )
            logger.warning(f"[CACHE INVALIDATION] ✓ POISONED cache (set invalidation_failed=true) - Phase 1 will skip stale data")
            return
        except Exception as poison_err:
            logger.error(f"[CACHE INVALIDATION] ✗ POISONING ALSO FAILED: {type(poison_err).__name__}: {poison_err}")

    except Exception as setup_err:
        logger.error(f"[CACHE INVALIDATION] Setup error: {setup_err}")

    # Step 3: Both deletion AND poisoning failed - CRITICAL: MUST HALT
    logger.critical(
        f"[CACHE INVALIDATION] ✗✗ CRITICAL FAILURE: Could not delete OR poison cache. "
        f"Phase 1 will potentially use stale data. HALTING LOADER IMMEDIATELY."
    )
    raise RuntimeError(
        f"CRITICAL: Cache invalidation completely failed (cannot delete or poison). "
        f"Halting loader to prevent silent stale-data corruption."
    )

def log_loader_execution(loader_name, table_name, status, records_loaded=0, records_updated=0, error_msg=None, duration_seconds=0):
    """Log loader execution to data_loader_runs table for monitoring."""
    try:
        with DatabaseContext('write') as cur:
            # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
            run_date = datetime.now(ZoneInfo("America/New_York")).date()
            cur.execute("""
                INSERT INTO data_loader_runs (
                    loader_name, table_name, run_date, status, records_loaded, records_updated,
                    error_message, duration_seconds, started_at, completed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                )
                ON CONFLICT (loader_name, run_date) DO UPDATE SET
                    status = EXCLUDED.status,
                    records_loaded = EXCLUDED.records_loaded,
                    records_updated = EXCLUDED.records_updated,
                    error_message = EXCLUDED.error_message,
                    duration_seconds = EXCLUDED.duration_seconds,
                    completed_at = NOW()
            """, (
                loader_name,
                table_name,
                run_date,
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
    logger.info(f"[{_correlation_id}] [MAIN] Starting price loader instance")

    try:
        logger.info(f"[{_correlation_id}] [MAIN] Environment loaded successfully")
    except Exception as e:
        logger.error(f"[MAIN] Failed to load environment: {e}", exc_info=True)
        try:
            _invalidate_phase1_cache()
        except RuntimeError as cache_err:
            logger.critical(f"[MAIN] Cache invalidation failed on environment error: {cache_err}")
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
        try:
            _invalidate_phase1_cache()
        except RuntimeError as cache_err:
            logger.critical(f"[MAIN] Cache invalidation failed on symbols error: {cache_err}")
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
                try:
                    _invalidate_phase1_cache()
                except RuntimeError as cache_err:
                    logger.critical(f"[MAIN] Cache invalidation failed on loader error: {cache_err}")
                fail_count += 1
                return 1

    logger.info(f"[MAIN] All intervals completed. Total: {total_stats}")

    duration_seconds = round(time.time() - start_time, 2)
    if fail_count > 0:
        logger.error(f"[MAIN] {fail_count} interval(s) had too many failures")
        try:
            _invalidate_phase1_cache()
        except RuntimeError as cache_err:
            logger.critical(f"[MAIN] Cache invalidation failed on final failure: {cache_err}")
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

