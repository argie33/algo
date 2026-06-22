#!/usr/bin/env python3

"""UNIFIED Price Loader - loads all intervals (1d, 1wk, 1mo) and asset classes (stock, etf).

Environment variables (set by Terraform/ECS task definition):
  LOADER_INTERVALS: comma-separated intervals (default: "1d,1wk,1mo")
  LOADER_ASSET_CLASSES: comma-separated asset classes (default: "stock,etf")
  LOADER_SYMBOLS: optional comma-separated symbols; if blank, uses database active symbols
  LOADER_PARALLELISM: thread pool size (default: 2)

Runs each interval+asset_class combination sequentially, parallelizing symbol fetches within.
Tables: price_daily, price_weekly, price_monthly, etf_price_daily, etf_price_weekly, etf_price_monthly
"""

import logging
import os
import sys
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Optional, cast

import psycopg2.sql

from loaders.price_fetcher import PriceFetcher
from loaders.price_transformer import PriceTransformer
from loaders.price_validator import PriceValidator
from monitoring.metrics_context import TimeBlock
from utils.data.provenance import DataProvenanceTracker
from utils.data.tick_validator import validate_price_tick
from utils.data.watermark import WatermarkManager
from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table
from utils.infrastructure.circuit_breaker import CircuitBreaker, DataImportance
from utils.infrastructure.correlation import set_correlation_id
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.config import get_parallelism
from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.validation.data_freshness import FreshnessValidator, StaleDataError


logger = logging.getLogger(__name__)

# Correlation ID for tracing - Phase 1 passes PHASE1_CORRELATION_ID via environment
# Initialize correlation_context with the environment-provided ID or auto-generate
_correlation_id = os.getenv("PHASE1_CORRELATION_ID") or f"AUTO-{str(uuid.uuid4())[:8]}"
set_correlation_id(_correlation_id)


class PriceLoader(OptimalLoader):
    """Multi-timeframe price loader. Replaces 4 separate loaders.

    Data Criticality: CRITICAL (used for position sizing, P&L calculations)
    Failure Mode: Fails fast on unavailable/stale data, does not degrade to stale prices
    Freshness Requirement: Maximum 1 day staleness for daily prices

    Uses canonical circuit breaker (utils.infrastructure.circuit_breaker:CircuitBreaker)
    with DataImportance.CRITICAL and freshness validation to prevent silent stale data.
    """

    def __init__(self, interval: str = "1d", asset_class: str = "stock", *args, **kwargs):
        """Initialize with interval (1d/1wk/1mo) and asset class (stock/etf)."""
        assert interval in ("1d", "1wk", "1mo"), f"Invalid interval: {interval}"
        assert asset_class in ("stock", "etf"), f"Invalid asset_class: {asset_class}"

        self.interval = interval
        self.asset_class = asset_class
        self._correlation_id = _correlation_id
        self.batch_size = 500

        # Circuit breaker for data loader outage handling
        self._circuit_breaker = CircuitBreaker(name="yfinance_prices", importance=DataImportance.CRITICAL)

        # Freshness validator: stock prices must be <= 1 day old
        self._freshness_validator = FreshnessValidator(
            max_age_hours={"price_data": 24.0}
        )

        # Map interval + asset_class to table name
        if asset_class == "etf":
            self.table_name = {
                "1d": "etf_price_daily",
                "1wk": "etf_price_weekly",
                "1mo": "etf_price_monthly",
            }[interval]
        else:
            self.table_name = {
                "1d": "price_daily",
                "1wk": "price_weekly",
                "1mo": "price_monthly",
            }[interval]

        self.primary_key = ("symbol", "date")
        self.watermark_field = "date"
        super().__init__(*args, **kwargs)
        self.tracker = None
        self.watermark_mgr = None
        self.run_id = None

        # Initialize specialists
        self._is_eod_pipeline = self._detect_eod_pipeline_context()
        from config.thresholds import ThresholdConfig
        self._rate_limit_circuit_break_threshold = ThresholdConfig.get_rate_limit_threshold(self._is_eod_pipeline)

        # Instantiate specialists - each handles a specific concern
        self.fetcher = PriceFetcher(
            router=self.router,
            interval=interval,
            asset_class=asset_class,
            is_eod_pipeline=self._is_eod_pipeline,
        )
        self.fetcher.set_circuit_breaker(self._circuit_breaker)

        self.validator = PriceValidator(table_name=self.table_name, asset_class=asset_class)
        self.transformer = PriceTransformer(asset_class=asset_class)

        # Batch tracking for rate limit detection
        self._batch_success_count = 0
        self._batch_total_count = 0
        self._batch_failure_ratio = 0.0
        self._market_close_detected = False
        self._market_close_timeout_count = 0
        self._last_market_close_timeout_time: float | None = None

        # ISSUE #14-15 FIX: Differentiate failure causes for targeted remediation
        # Track root cause of failures to apply appropriate fixes:
        # - Market close unavailability: wait and retry (data will become available)
        # - Rate limiting (429): reduce batch size, apply backoff
        # - API lag/timeout: increase timeout, reduce parallelism
        # - Other errors: log and fail
        self._failure_cause = None  # 'market_close', 'rate_limit_429', 'api_lag', 'other'
        self._api_lag_timeouts = 0  # Count of timeout errors (not rate limiting)
        self._api_lag_error_start_time = None  # When API lag started

        # CREATIVE FIX #2: Track batch size performance for smart batch sizing
        self._batch_size_performance: dict[int, list[int]] = {}

        # Rate limit tracking
        self._rate_limit_errors = 0
        self._rate_limit_error_start_time: float | None = None

        # CREATIVE FIX #1: Adaptive request pacing to stay under rate limits
        self._request_latency_samples: list[tuple[float, float]] = []
        self._latency_window_sec = 60
        self._adaptive_request_interval = 0.375
        self._min_request_interval = 0.375
        self._last_request_time: float | None = None

        # Rate limit token bucket (thread-safe fairness)
        self._rate_limit_event = threading.Condition()
        self._rate_limit_tokens = 160.0
        self._rate_limit_max_tokens = 160.0
        self._rate_limit_refill_rate = 160.0 / 60.0
        self._rate_limit_last_refill = time.time()

    def _detect_eod_pipeline_context(self) -> bool:
        """Detect if running during EOD pipeline (4:05-5:30 PM ET) for timing-aware rate limiting.

        Returns True if current time is 4:05 PM Â± 2 hours (accounts for slow yfinance lag).
        EOD pipeline has tight deadline (85 min), so we use aggressive rate limiting strategy.
        """
        from datetime import datetime

        now_et = datetime.now(EASTERN_TZ)
        eod_start_et = now_et.replace(hour=16, minute=5, second=0, microsecond=0)  # 4:05 PM ET

        # Check if we're within 2 hours of EOD start (accounts for possible scheduler delays)
        time_since_eod_start = (now_et - eod_start_et).total_seconds() / 60
        if -10 < time_since_eod_start < 120:  # -10 min to +120 min relative to 4:05 PM
            logger.info(
                f"[CONTEXT] Running during EOD pipeline ({time_since_eod_start:.0f} min from 4:05 PM ET), using aggressive rate limiting"
            )
            return True

        logger.debug(
            f"[CONTEXT] Running during morning/regular hours ({time_since_eod_start:.0f} min from 4:05 PM ET), using conservative rate limiting"
        )
        return False

    def _validate_schema_preflight(self):
        """Pre-flight validation: Ensure table schema is correct before loading any data.

        CRITICAL: Validates that target table has all required columns with correct data types.
        This catches schema mismatches (e.g., price column became TEXT instead of NUMERIC)
        before attempting to load or insert data.

        If validation fails, raises RuntimeError to halt loader immediately and prevent
        silent data corruption or runtime failures.
        """
        from loaders.schema_definitions import TABLE_SCHEMAS
        from utils.db.context import DatabaseContext
        from utils.validation.schema import validate_table_schema

        if self.table_name not in TABLE_SCHEMAS:
            logger.warning(f"[SCHEMA] No pre-defined schema for {self.table_name}, skipping validation")
            return

        required_schema = TABLE_SCHEMAS[self.table_name]

        try:
            with DatabaseContext("read") as cur:
                is_valid, errors = validate_table_schema(
                    cur,
                    self.table_name,
                    required_columns=required_schema,
                    check_row_count=False,  # Don't require table to have rows yet
                )

                if not is_valid:
                    error_msg = "\n".join(errors)
                    logger.error(
                        f"[SCHEMA] âŒ Schema validation FAILED for {self.table_name}:\n{error_msg}\n"
                        "This will cause data loading to fail. "
                        "Verify table schema matches expected definition."
                    )
                    raise RuntimeError(f"Schema validation failed for {self.table_name}: {error_msg}")

                logger.info(
                    f"[SCHEMA] âœ“ Schema validation passed for {self.table_name} ({len(required_schema)} columns)"
                )

                # CRITICAL FIX: Verify unique constraint exists (prevents duplicate insertions)
                # This is a defensive check to ensure data integrity constraints are in place
                self._verify_unique_constraint_exists(cur)

        except RuntimeError:
            raise  # Re-raise validation errors
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(
                f"[SCHEMA] Could not perform schema validation for {self.table_name}: {e}",
                exc_info=True,
            )
            raise RuntimeError(f"Schema validation could not complete: {e}") from e

    def _verify_unique_constraint_exists(self, cur):
        """Verify that unique constraint on primary key exists (prevents duplicates).

        CRITICAL: Ensures that the database enforces uniqueness on (symbol, date).
        If this constraint is missing, duplicate rows can be inserted silently,
        corrupting the dataset.

        This is the root cause check for issue where 20,150 duplicate rows
        were inserted when the unique constraint didn't exist.
        """
        if not self.primary_key:
            logger.debug(f"[CONSTRAINT] No primary_key defined for {self.table_name}, skipping check")
            return

        pk_cols = ",".join(self.primary_key)
        try:
            # Check for unique constraint or index on primary key
            cur.execute(
                """
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_name = %s
                  AND constraint_type = 'UNIQUE'
                LIMIT 1
            """,
                (self.table_name,),
            )

            constraint_exists = cur.fetchone() is not None

            if not constraint_exists:
                # Check for unique index as fallback
                cur.execute(
                    """
                    SELECT 1 FROM pg_indexes
                    WHERE tablename = %s AND indexdef LIKE '%UNIQUE%'
                    LIMIT 1
                """,
                    (self.table_name,),
                )
                index_exists = cur.fetchone() is not None
            else:
                index_exists = True

            if constraint_exists or index_exists:
                logger.info(f"[CONSTRAINT] âœ“ Unique constraint/index found on {self.table_name}({pk_cols})")
            else:
                # This is a CRITICAL error - without the constraint, duplicates can occur
                error_msg = (
                    f"[CONSTRAINT] âŒ CRITICAL: No UNIQUE constraint or index on {self.table_name}({pk_cols}). "
                    f"This allows duplicate rows to be inserted, corrupting the dataset. "
                    f"Root cause analysis: https://github.com/yourorg/algo/blob/main/steering/duplicate_rows_root_cause_analysis.md. "
                    f"Create constraint with: ALTER TABLE {self.table_name} ADD CONSTRAINT "
                    f"{self.table_name}_{'_'.join(self.primary_key)}_unique UNIQUE ({pk_cols})"
                )
                logger.critical(error_msg)
                raise RuntimeError(error_msg)

        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(
                f"[CONSTRAINT] Could not verify unique constraint for {self.table_name}: {e}. "
                f"Proceeding with caution - duplicates may occur if constraint doesn't exist."
            )

    def _get_smart_batch_size(self) -> int:
        """CREATIVE FIX #2: Calculate optimal batch size based on observed API performance.

        Instead of starting conservative and reducing, we learn which batch sizes
        work well for this specific yfinance instance and use those.

        Algorithm:
        1. If we have performance data for batch sizes, use the one with highest success rate
        2. If multiple sizes tie, prefer larger (fewer API calls)
        3. If no data yet, use context-aware default

        This prevents unnecessary retries by picking sizes that we know work.
        """
        # Find batch size with best success rate
        if self._batch_size_performance:
            best_size: int | None = None
            best_rate: float = -1
            for size, (successes, failures) in self._batch_size_performance.items():
                total = successes + failures
                if total >= 2:  # Need at least 2 trials to consider
                    rate = successes / total
                    if rate > best_rate or (rate == best_rate and (best_size is None or size > best_size)):
                        best_rate = rate
                        best_size = size

            if best_size is not None and best_rate >= 0.5:
                logger.debug(f"[BATCH_SIZE_SMART] Using batch={best_size} (success rate {best_rate:.0%})")
                return best_size

        # Fallback: use default with context awareness
        if self._is_eod_pipeline:
            return 50  # Conservative during EOD
        return 100

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
        # CREATIVE FIX #2: Use smart batch sizing if available
        smart_size = self._get_smart_batch_size()
        if smart_size != 100 and smart_size != 50:  # If smart sizing found a good size
            return smart_size

        # Fallback to reactive sizing
        # ISSUE #6 FIX: Proactive conservative sizing during EOD to avoid timeout
        # Even though 160/min rate limit theoretically allows batch=150,
        # if API lag or rate limiting persists, conservative batch sizing ensures completion.
        # Worst case: batch=20 Ã— 250 symbols/batch = 12500 API calls at 160/min = ~78 min,
        # well under Step Function timeout (27000s = 450 min).
        if self._is_eod_pipeline and self._batch_total_count == 0:
            logger.info(
                "[BATCH_SIZE] EOD pipeline context: starting with batch=50 (conservative to ensure Step Function completion)"
            )
            return 50  # Start conservative during EOD to protect against timeouts

        if self._is_eod_pipeline and self._rate_limit_errors > 0:
            logger.debug(
                f"[BATCH_SIZE] EOD pipeline with {self._rate_limit_errors} prior errors, using batch=20 (very conservative)"
            )
            return 20  # Very conservative if we've already hit rate limits during EOD

        # Reactive: Adjust based on recent success rate
        if self._batch_total_count == 0:
            return 100  # Default batch size on first run (non-EOD)

        success_rate = self._batch_success_count / self._batch_total_count

        if success_rate > 0.8:
            return 100  # High success: keep large batches
        elif success_rate > 0.5:
            return 50  # Moderate success: smaller batches
        else:
            return 20  # Low success: very small batches

    def _record_batch_result(self, success_count: int, total_count: int):
        """Record batch success/failure ratio for adaptive retry logic.

        Allows tracking partial success without requiring per-symbol results.
        """
        self._batch_success_count = success_count
        self._batch_total_count = total_count
        if total_count == 0:
            raise ValueError("No symbols to fetch â€” batch size calculation error")
        self._batch_failure_ratio = 1.0 - (success_count / total_count)

        if success_count < total_count:
            logger.info(
                f"[BATCH RESULT] Partial success: {success_count}/{total_count} symbols ({success_count / total_count * 100:.0f}%). "
                f"Failure ratio: {self._batch_failure_ratio:.2f}. "
                f"Next batch size recommendation: {self._get_adaptive_batch_size()}"
            )

    def _check_market_close_data_available(self, max_wait_sec: int | None = None) -> bool:
        """Check if SPY close data is available (market close data freshness check).

        EOD pipeline starts at 4:05 PM ET. yfinance API can lag 5-15 minutes after market close (4 PM ET).
        Uses exponential backoff (5s, 10s, 20s, 40s, ...) to avoid hammering the API while waiting for
        data availability.

        Timeout is context-aware:
        - EOD pipeline (4:05-6:00 PM): 1800s (30 min) â€” generous buffer within 85-min pipeline window
        - Morning prep (3:30-9:30 AM): 600s (10 min) â€” market just opened, data should be fresh
        - Other times: 300s (5 min) â€” should rarely block

        ISSUE #11 FIX: Returns False if timeout and raises RuntimeError to halt loader.
        This prevents the loader from silently proceeding with stale data.
        Phase 1 will catch this failure and trigger failsafe.

        Returns: True if SPY close data available
        Raises: RuntimeError if data cannot be verified (loader should abort)
        """
        if max_wait_sec is None:
            # CRITICAL FIX: Read timeout from algo_config with strict validation
            # Use context-aware defaults: EOD (1800s/30min) vs Morning (600s/10min)
            # Increased from 1200s to 1800s to handle yfinance lag of 10-15 minutes
            default_timeout_sec = 600 if self._is_eod_pipeline else 300
            config_key = (
                "yfinance_market_close_timeout_eod_sec"
                if self._is_eod_pipeline
                else "yfinance_market_close_timeout_morning_sec"
            )
            config_used = "default"

            try:
                from utils.db.context import DatabaseContext

                with DatabaseContext("read") as config_cur:
                    config_cur.execute("SELECT value FROM algo_config WHERE key = %s", (config_key,))
                    config_result = config_cur.fetchone()
                    if config_result:
                        try:
                            config_value = int(config_result[0])
                            # CRITICAL: Validate timeout is reasonable (1s-3600s)
                            # Increased upper bound from 1800s to 3600s to support longer waits if needed
                            if config_value < 1 or config_value > 3600:
                                logger.warning(
                                    f"[MARKET_CLOSE] âš ï,  Config {config_key}={config_value}s is out of bounds (1-3600s). "
                                    f"Using default {default_timeout_sec}s instead."
                                )
                                max_wait_sec = default_timeout_sec
                                config_used = "default (config out of bounds)"
                            else:
                                max_wait_sec = config_value
                                logger.info(
                                    f"[MARKET_CLOSE] Using configured timeout: {max_wait_sec}s (from {config_key})"
                                )
                                config_used = "configured"
                        except (ValueError, TypeError) as parse_err:
                            logger.warning(
                                f"[MARKET_CLOSE] âš ï,  Config {config_key}={config_result[0]} is not a valid integer. "
                                f"Using default {default_timeout_sec}s instead. Error: {parse_err}"
                            )
                            max_wait_sec = default_timeout_sec
                            config_used = "default (config invalid)"
                    else:
                        max_wait_sec = default_timeout_sec
                        logger.debug(
                            f"[MARKET_CLOSE] WARNING Config key {config_key} not found, using default timeout: {max_wait_sec}s"
                        )
                        config_used = "default (key missing)"
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as config_err:
                error_msg = (
                    f"[MARKET_CLOSE] Could not read market close timeout config. "
                    f"Configuration is non-optional: {config_err}. "
                    f"Check database connectivity and algo_config table."
                )
                logger.critical(error_msg)
                raise RuntimeError(error_msg) from config_err

            logger.info(
                f"[MARKET_CLOSE] Using {config_used} timeout: {max_wait_sec}s ({max_wait_sec / 60:.0f} min) "
                f"(pipeline={'EOD' if self._is_eod_pipeline else 'morning'})"
            )
        else:
            logger.debug(f"[MARKET_CLOSE] Using override timeout: {max_wait_sec}s")

        from datetime import datetime

        from algo.infrastructure import MarketCalendar

        # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
        today = datetime.now(EASTERN_TZ).date()

        # Check if today is a trading day
        if not MarketCalendar.is_trading_day(today):
            logger.info("[MARKET_CLOSE] Today is not a trading day, skipping close data check")
            return True

        # Check if we're within 45 minutes after market close (4:00 PM ET Â± 45 min = 3:15 PM - 4:45 PM)
        now_et = datetime.now(EASTERN_TZ)
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

        # We're 0-45 minutes after market close - verify SPY data with efficient retry
        logger.info(
            f"[MARKET_CLOSE] {minutes_after_close:.1f}min after close at 4 PM ET, checking yfinance for SPY data..."
        )

        start_time = time.time()
        attempt = 0
        # ISSUE #11 FIX: Use SHORT timeout (15s) per check, fixed waits between retries
        # This allows ~4x more attempts in the same 30-min budget vs 120s timeout per attempt
        # Typical yfinance lag is 5-15 min, so more frequent polling catches data sooner
        short_check_timeout = 15  # Each yfinance check uses only 15s (not 120s)
        wait_between_checks = 3  # Wait only 3s between short checks (fixed, not exponential)
        last_error_type = None
        last_error_msg = None

        while time.time() - start_time < max_wait_sec:
            attempt += 1
            try:
                # Use FAST market close check: 15s timeout instead of 120s
                # This is much more efficient for checking "is data available?" vs "download all data"
                data_available = self.router.check_market_close_data_available_fast(
                    symbol="SPY", timeout_sec=short_check_timeout
                )
                if data_available:
                    elapsed = time.time() - start_time
                    logger.info(f"[MARKET_CLOSE] âœ“ Data available after {elapsed:.1f}s (attempt {attempt})")
                    # Emit success metric
                    try:
                        from algo.reporting import MetricsPublisher

                        metrics = MetricsPublisher()
                        metrics.put_metric(  # type: ignore
                            "MarketCloseDataAvailable",
                            1,
                            unit="Count",
                            dimensions={"Status": "success"},
                        )
                        metrics.flush()
                    except Exception as metric_err:
                        logger.debug(f"Could not publish market close success metric: {metric_err}")
                    return True
            except Exception as e:
                last_error_type = type(e).__name__
                last_error_msg = str(e)[:200]  # Truncate for logging
                error_str = str(e).lower()
                is_timeout = "timeout" in error_str or "connect" in error_str or "read timed" in error_str
                is_rate_limit = "429" in error_str or "too many" in error_str or "rate" in error_str

                log_level = "warning" if is_rate_limit else ("warning" if is_timeout else "debug")
                logger.log(
                    (
                        getattr(logging, log_level.upper())
                        if log_level in ["debug", "warning", "error"]
                        else logging.DEBUG
                    ),
                    f"[MARKET_CLOSE] Attempt {attempt}: {last_error_type} "
                    + ("(rate limit)" if is_rate_limit else "(timeout)" if is_timeout else "(other)")
                    + f" - {last_error_msg}",
                )

            # Check time remaining and wait before next attempt
            elapsed = time.time() - start_time
            wait_remaining = max_wait_sec - elapsed
            wait_time = min(wait_between_checks, wait_remaining)

            if wait_time > 0 and wait_remaining > 0:
                logger.debug(
                    f"[MARKET_CLOSE] Waiting {wait_time:.0f}s before retry {attempt + 1}... (elapsed {elapsed / 60:.1f}min/{max_wait_sec / 60:.0f}min)"
                )
                time.sleep(wait_time)
            elif wait_remaining <= 0:
                break  # Total timeout reached

        # Timeout - data not available, HALT loader with explicit error (ISSUE #11 FIX)
        elapsed = time.time() - start_time

        # ISSUE #7 FIX: Track consecutive market close timeouts to detect API degradation
        now = time.time()
        if (
            self._last_market_close_timeout_time and (now - self._last_market_close_timeout_time) < 86400
        ):  # Within 24 hours
            self._market_close_timeout_count += 1
        else:
            self._market_close_timeout_count = 1
        self._last_market_close_timeout_time = now

        # Alert if this is repeated failure (3+ times in 24h = API degradation pattern)
        if self._market_close_timeout_count >= 3:
            alert_msg = (
                f"ALERT: Market close data unavailable {self._market_close_timeout_count} times in 24h. "
                "Possible yfinance API degradation. Check status page and consider switching data provider."
            )
            logger.critical(f"[{self._correlation_id}] {alert_msg}")
            try:
                from algo.reporting import AlertManager

                AlertManager().critical(alert_msg)
            except Exception as alert_err:
                logger.error(
                    f"[{self._correlation_id}] Failed to send critical alert: {alert_err}",
                    exc_info=True,
                )

        # Emit failure metric with diagnostic info
        try:
            from algo.reporting import MetricsPublisher

            metrics = MetricsPublisher()
            metrics.put_metric(  # type: ignore
                "MarketCloseDataAvailable",
                0,
                unit="Count",
                dimensions={
                    "Status": "timeout",
                    "LastError": last_error_type or "unknown",
                    "ConsecutiveCount": str(self._market_close_timeout_count),
                },
            )
            metrics.flush()
        except Exception as metrics_err:
            logger.error(
                f"[{self._correlation_id}] Failed to publish market close timeout metric: {metrics_err}",
                exc_info=True,
            )

        # Determine root cause for clearer diagnostics
        last_error_lower = (last_error_msg or "").lower()
        is_rate_limit = "429" in last_error_lower or "too many" in last_error_lower or "rate" in last_error_lower
        root_cause = "yfinance rate limiting" if is_rate_limit else "yfinance API lag/unavailability"

        error_msg = (
            f"Market close data NOT available after {elapsed:.0f}s ({elapsed / 60:.1f} min, {attempt} attempts). "
            f"Root cause: {root_cause} | Last error: {last_error_type} - {last_error_msg or 'no message'}. "
            "Cannot load prices without market close data. Aborting to avoid stale price data. "
            "Phase 1 will trigger failsafe when data becomes available. "
            "Check yfinance API status and RDS connection pool health. "
            f"[Consecutive timeouts: {self._market_close_timeout_count}/24h]"
        )
        logger.error(f"[{self._correlation_id}] [MARKET_CLOSE] âœ— {error_msg}")
        raise RuntimeError(error_msg)

    def _record_request_latency(self, latency_sec: float) -> None:
        """CREATIVE FIX #1: Track API latency to predict when rate limits will be hit.

        Records request latency and uses it to adaptively adjust request interval.
        If API is responding slowly (>1s per request), we increase wait time between requests
        to stay under the 160 req/min limit.
        """
        now = time.time()
        self._request_latency_samples.append((now, latency_sec))

        # Keep only recent samples (within 60s window)
        cutoff = now - self._latency_window_sec
        self._request_latency_samples = [(t, lat) for t, lat in self._request_latency_samples if t >= cutoff]

        if len(self._request_latency_samples) >= 3:  # Need at least 3 samples to estimate
            avg_latency = sum(lat for _, lat in self._request_latency_samples) / len(self._request_latency_samples)

            # If API is responding slowly, increase wait time to avoid rate limiting
            # Formula: if avg_latency > 0.6s, we're approaching the 160 req/min limit
            # Adjust interval to: latency + slack for other requests
            if avg_latency > 0.6:
                new_interval = max(self._min_request_interval, avg_latency * 1.5)  # 1.5x latency for safety
                if new_interval > self._adaptive_request_interval:
                    self._adaptive_request_interval = new_interval
                    logger.info(
                        f"[RATE_LIMIT_PREDICT] API latency {avg_latency:.3f}s avg, increasing request interval to {new_interval:.3f}s"
                    )
            elif avg_latency < 0.3:
                # API is responding quickly, we can be more aggressive
                new_interval = max(self._min_request_interval, 0.375)  # Default 160 req/min
                if new_interval < self._adaptive_request_interval:
                    self._adaptive_request_interval = new_interval
                    logger.debug(
                        f"[RATE_LIMIT_PREDICT] API latency {avg_latency:.3f}s avg, decreasing interval to {new_interval:.3f}s"
                    )

    def _adaptive_request_pacing(self) -> None:
        """CREATIVE FIX #1: Implement predictive rate limiting with request pacing.

        Instead of hitting rate limits and then backing off exponentially,
        we spread requests over time at a rate that's guaranteed to stay under the limit.
        This prevents the circuit breaker from ever triggering.
        """
        if self._last_request_time is None:
            self._last_request_time = time.time()
            return

        now = time.time()
        elapsed = now - self._last_request_time
        wait_needed = self._adaptive_request_interval - elapsed

        if wait_needed > 0.01:  # Only sleep if >10ms wait needed
            logger.debug(
                f"[RATE_LIMIT_PACE] Request pacing: waiting {wait_needed:.3f}s (interval {self._adaptive_request_interval:.3f}s)"
            )
            time.sleep(wait_needed)

        self._last_request_time = time.time()

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
                self._rate_limit_tokens = min(
                    self._rate_limit_max_tokens,
                    self._rate_limit_tokens + elapsed * self._rate_limit_refill_rate,
                )
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

    def fetch_incremental(self, symbol: str, since: date | None):
        """Fetch OHLCV from yfinance at specified interval."""
        return self.fetcher.fetch_incremental(symbol, since, is_eod_pipeline=self._is_eod_pipeline)

    def fetch_batch_incremental(self, symbols: list[str], since: date | None):
        """Fetch OHLCV for multiple symbols at once (50x faster than per-symbol).

        Returns: dict[symbol] -> rows or None
        """
        return self.fetcher.fetch_batch_incremental(symbols, since, is_eod_pipeline=self._is_eod_pipeline)

    def _execute_batch_fetch(self, symbols: list[str], start: date, end: date) -> dict | None:
        """Execute batch fetch with circuit breaker and validate freshness."""
        result = self.fetcher._execute_batch_fetch(symbols, start, end)

        if result and isinstance(result, dict):
            latest_price_date: datetime | None = None
            for rows in result.values():
                if rows:
                    for row in rows:
                        row_date_str = row.get("date")
                        if row_date_str:
                            try:
                                row_date = datetime.fromisoformat(row_date_str)
                                if latest_price_date is None or row_date > latest_price_date:
                                    latest_price_date = row_date
                            except (ValueError, TypeError):
                                pass

            if latest_price_date is not None:
                try:
                    self._freshness_validator.check("price_data", latest_price_date, allow_missing=False)
                except StaleDataError as e:
                    logger.critical(
                        f"[FRESHNESS_VALIDATION] {e}. Stock prices are too stale for position sizing. Cannot proceed."
                    )
                    self._circuit_breaker.record_failure()
                    raise RuntimeError(f"Price data freshness validation failed: {e}") from e

        return result

    def _handle_successful_fetch(self, result: dict, symbols: list[str]) -> dict:
        """Reset rate limit tracking and record batch performance."""
        if self._rate_limit_errors > 0:
            logger.info(
                f"[RATE_LIMIT_RECOVERY] API recovered after {self._rate_limit_errors} errors. "
                f"Decreasing request interval from {self._adaptive_request_interval:.3f}s back to normal."
            )
            self._adaptive_request_interval = max(0.375, self._adaptive_request_interval * 0.9)

        self._rate_limit_errors = 0
        self._rate_limit_error_start_time = None

        batch_size_key = len(symbols)
        if batch_size_key not in self._batch_size_performance:
            self._batch_size_performance[batch_size_key] = [0, 0]
        self._batch_size_performance[batch_size_key][0] += 1

        return result

    def _handle_rate_limit_error(
        self,
        symbols: list[str],
        start: date,
        end: date,
        batch_size: int,
        attempt: int,
        max_attempts: int,
        elapsed_sec: float,
        error: Exception,
    ) -> dict | None:
        """Retry rate limit errors with pacing or batch reduction."""
        import random
        import time

        self._rate_limit_errors += 1
        if self._rate_limit_error_start_time is None:
            self._rate_limit_error_start_time = time.time()
            logger.warning(
                f"[RATE_LIMIT] First rate limiting error detected (error #{self._rate_limit_errors}). "
                "Circuit will break if persists >5 minutes. Monitoring yfinance API recovery."
            )

        self._adaptive_request_interval = min(2.0, self._adaptive_request_interval * 1.5)
        logger.info(
            f"[RATE_LIMIT_PREDICT] Rate limit detected, increasing request interval to {self._adaptive_request_interval:.3f}s"
        )

        try:
            from algo.reporting import MetricsPublisher

            metrics = MetricsPublisher()
            metrics.add_metric(
                "RateLimitErrors",
                1,
                unit="Count",
                dimensions={"Loader": "stock_prices_daily"},
            )
            metrics.flush()
        except Exception as metric_err:
            logger.debug(f"Could not publish rate limit metric: {metric_err}")

        batch_size_key = len(symbols)
        if batch_size_key not in self._batch_size_performance:
            self._batch_size_performance[batch_size_key] = [0, 0]
        self._batch_size_performance[batch_size_key][1] += 1

        if batch_size == 1 and self._rate_limit_errors >= 2:
            raise RuntimeError(
                f"[BATCH=1 RATE LIMIT ABORT] Batch=1 with {self._rate_limit_errors} rate limit errors. "
                "yfinance API appears down. Cannot proceed with price fetching."
            ) from error

        if self._is_eod_pipeline and batch_size <= 20 and self._rate_limit_errors >= 3:
            raise RuntimeError(
                f"[BATCH FETCH ABORT] Batch={batch_size} with {self._rate_limit_errors} rate limit errors. "
                "yfinance severely degraded. Cannot proceed with price fetching."
            )

        if attempt == 0:
            logger.info(
                f"[RATE_LIMIT] Retrying batch={batch_size} with increased request pacing (attempt {attempt + 1}/{max_attempts})..."
            )
            error_duration = time.time() - self._rate_limit_error_start_time if self._rate_limit_error_start_time else 0
            base_wait = min(30, (2**attempt) * 5)
            jitter = random.uniform(0.9, 1.1)
            wait_time = base_wait * jitter
            logger.debug(f"[RATE_LIMIT] Waiting {wait_time:.1f}s before paced retry...")
            time.sleep(wait_time)
            return cast(
                dict | None,
                self._fetch_with_fallback(symbols, start, end, batch_size, attempt + 1, max_attempts, elapsed_sec),
            )

        new_batch_size = max(1, batch_size // 2)
        error_duration = time.time() - self._rate_limit_error_start_time if self._rate_limit_error_start_time else 0
        total_elapsed = elapsed_sec + error_duration

        base_wait = min(60, (2**attempt) * 2)
        jitter = random.uniform(0.8, 1.2)
        wait_time = base_wait * jitter

        logger.warning(
            f"[BATCH FETCH] Rate limited after paced retry (attempt {attempt + 1}/{max_attempts}, error #{self._rate_limit_errors}, "
            f"duration {error_duration:.0f}s, total elapsed {total_elapsed:.0f}s). "
            f"Batch {batch_size} -> {new_batch_size}, waiting {wait_time:.1f}s..."
        )
        time.sleep(wait_time)

        results = {}
        successful_chunks = 0
        for i in range(0, len(symbols), new_batch_size):
            chunk = symbols[i : i + new_batch_size]
            chunk_results = self._fetch_with_fallback(
                chunk,
                start,
                end,
                new_batch_size,
                attempt + 1,
                max_attempts,
                elapsed_sec=total_elapsed,
            )
            results.update(chunk_results)
            if any(v is not None for v in chunk_results.values()):
                successful_chunks += 1

        total_chunks = (len(symbols) + new_batch_size - 1) // new_batch_size
        self._record_batch_result(successful_chunks, total_chunks)

        return results

    def _handle_transient_error(
        self,
        symbols: list[str],
        start: date,
        end: date,
        batch_size: int,
        attempt: int,
        max_attempts: int,
        elapsed_sec: float,
        error: Exception,
    ) -> dict | None:
        """Retry transient errors with exponential backoff."""
        import random
        import time

        error_str = str(error).lower()
        is_timeout = "timeout" in error_str or "timed out" in error_str
        is_connection = any(x in error_str for x in ["connection", "reset", "broken", "closed"])

        error_type = (
            "timeout (API slowness)" if is_timeout else "connection (network)" if is_connection else "other transient"
        )

        if is_timeout or is_connection:
            self._adaptive_request_interval = min(2.0, self._adaptive_request_interval * 1.2)
            logger.warning(
                f"[BATCH FETCH] Transient {error_type} error, increasing request interval to {self._adaptive_request_interval:.3f}s for recovery"
            )

        base_wait = min(30, 2**attempt)
        jitter = random.uniform(0.9, 1.1)
        wait_time = base_wait * jitter

        logger.warning(
            f"[BATCH FETCH] Transient {error_type} error (attempt {attempt + 1}/{max_attempts}, elapsed {elapsed_sec:.0f}s): {error}. "
            f"Retrying {len(symbols)} symbols with same batch_size={batch_size} in {wait_time:.1f}s... "
            "(Note: batch size not reduced for timeouts - if API fundamentally slow, increasing wait time not batch reduction)"
        )
        time.sleep(wait_time)
        return cast(
            dict | None,
            self._fetch_with_fallback(
                symbols,
                start,
                end,
                batch_size,
                attempt + 1,
                max_attempts,
                elapsed_sec=elapsed_sec + wait_time,
            ),
        )

    def _fetch_with_fallback(
        self,
        symbols: list[str],
        start: date,
        end: date,
        batch_size: int,
        attempt: int = 0,
        max_attempts: int = 3,
        elapsed_sec: float = 0,
    ):
        """Fetch with progressive batch size reduction and adaptive retry with jitter.

        ISSUE #6 FIX: Add upper bound check - if batch_size=1 and still rate limited, fail immediately.
        Attempts: full batch -> split in half -> quarter size -> give up.
        Includes randomized jitter to avoid thundering herd and circuit breaker for persistent errors.

        CRITICAL: Prevents infinite batch reduction + timeout cascade by tracking elapsed time.
        If batch=1 and elapsed > threshold, fail immediately rather than waiting indefinitely.
        """
        import random
        import time

        # ISSUE #6 FIX: Prevent infinite batch reduction and Step Function timeout
        # Track elapsed time to detect when we're spending too long on rate limiting
        if elapsed_sec is None:
            elapsed_sec = 0

        # CRITICAL BOUND: If batch_size=1 and rate limiting persists, give up per pipeline context
        # ISSUE #23 FIX: Reduced thresholds - rates at batch=1 usually indicate API is down
        # EOD (85 min deadline): 2 min max wait at batch=1 to fail fast and trigger failsafe
        # Morning (450 min deadline): 5 min max wait at batch=1 (was 10, but if batch=1 hangs, API is likely degraded)
        max_single_batch_wait = 120 if self._is_eod_pipeline else 300
        if batch_size == 1 and elapsed_sec > max_single_batch_wait:
            logger.critical(
                f"[BATCH FETCH TIMEOUT] Batch=1 with {elapsed_sec / 60:.1f}min elapsed. "
                "Failing immediately to prevent Step Function timeout. yfinance severely degraded."
            )
            raise RuntimeError(
                f"[BATCH FETCH TIMEOUT] Batch=1 with {elapsed_sec / 60:.1f}min elapsed. "
                "yfinance API severely degraded - cannot proceed without data."
            )

        # ISSUE #6 FIX: If we've shrunk to batch_size=1 and still rate limiting, give up immediately
        # This prevents infinite reduction and timeout cascade
        if batch_size <= 0 or attempt >= max_attempts:
            logger.critical(
                f"[BATCH FETCH] Exhausted all retry attempts: {attempt}/{max_attempts} with batch_size={batch_size}, elapsed {elapsed_sec:.0f}s"
            )
            raise RuntimeError(
                f"[BATCH FETCH EXHAUSTED] Max attempts ({max_attempts}) exceeded with batch_size={batch_size}. "
                "yfinance API unavailable - cannot fetch price data."
            )

        # Issue #1 FIX (Blocker #1): Proactive early abort if rate limiting detected at batch >= 20
        # CRITICAL: Fail-fast rather than wait through hopeless retry loops.
        # At batch=20 with persistent 429s, loader could take 400+ min for 5000+ symbols.
        # If we've hit 3+ rate limit errors, yfinance is clearly degraded. Timing is context-aware:
        #   - EOD (85-min pipeline): abort immediately after 3 errors (tight deadline, fail-fast required)
        #   - Morning (450-min pipeline): abort after 3 errors + 30s duration (allow brief recovery)
        # This prevents: batch 150â†’20â†’10â†’5â†’1 cascade where load time balloons from 15 min â†’ 200+ min
        if batch_size >= 20 and self._rate_limit_errors >= 3:
            error_duration = (
                (time.time() - self._rate_limit_error_start_time) if self._rate_limit_error_start_time else 0
            )
            should_abort = self._is_eod_pipeline or error_duration > 30
            if should_abort:
                context = "EOD (fail-fast)" if self._is_eod_pipeline else f"persistent {error_duration:.0f}s"
                logger.critical(
                    f"[RATE_LIMIT_EARLY_ABORT] Batch size {batch_size} with {self._rate_limit_errors} rate limit errors ({context}). "
                    "yfinance API severely degraded. Aborting early to prevent timeout cascade."
                )
                raise RuntimeError(
                    f"[RATE_LIMIT_EARLY_ABORT] {self._rate_limit_errors} rate limit errors at batch={batch_size} ({context}). "
                    "yfinance API severely degraded - cannot fetch price data."
                )

        # Issue #20 FIX: At batch=1, try longer wait before giving up
        if batch_size == 1 and self._rate_limit_errors > 3:
            # Try with exponential backoff + longer wait times (up to 10 min) at batch=1
            max_batch1_wait = 600  # 10 minutes for batch=1 final attempts
            if error_duration := (
                (time.time() - self._rate_limit_error_start_time) if self._rate_limit_error_start_time else 0
            ):
                remaining_wait = max(0, max_batch1_wait - error_duration)
                if remaining_wait > 60:  # Only if we have >1 min left
                    logger.warning(
                        f"[BATCH=1 BACKOFF] Batch size at minimum with {self._rate_limit_errors} errors. "
                        f"Attempting longer exponential backoff ({remaining_wait:.0f}s remaining) before final failure."
                    )
                    # Don't return yet - let the normal retry loop below handle the backoff
                elif remaining_wait > 0:
                    logger.warning(
                        f"[BATCH=1] Rate limiting at batch=1. Last chance with {remaining_wait:.0f}s remaining before timeout."
                    )

            # If we've exhausted backoff time, fail
            if error_duration and error_duration > max_batch1_wait:
                logger.critical(
                    f"[BATCH FETCH ABORT] Batch size at minimum (1 symbol) with {self._rate_limit_errors} rate limit errors "
                    f"persisting for {error_duration / 60:.1f}min. yfinance API severely degraded. Failing to prevent timeout."
                )
                try:
                    from algo.reporting import MetricsPublisher

                    m = MetricsPublisher()
                    m.put_metric(  # type: ignore
                        "BatchFetchMinimumSizeReached",
                        1,
                        unit="Count",
                        dimensions={
                            "table": self.table_name,
                            "error_count": str(self._rate_limit_errors),
                        },
                    )
                    m.flush()
                except Exception as metric_err:
                    logger.debug(f"Could not publish batch fetch minimum size metric: {metric_err}")
                raise RuntimeError(
                    f"[BATCH FETCH ABORT] Batch at minimum with {self._rate_limit_errors} rate limit errors for {error_duration / 60:.1f}min. "
                    "yfinance API severely degraded - cannot fetch price data."
                )

        # Check circuit breaker: if rate limiting has persisted for > threshold, try smaller batch size
        # Issue #6: Instead of failing completely, reduce batch size to avoid timeout
        # ISSUE #1 FIX: Skip circuit breaker if early abort already triggered (prevents false retry loop)
        if self._rate_limit_error_start_time is not None and not (batch_size >= 20 and self._rate_limit_errors >= 3):
            error_duration = time.time() - self._rate_limit_error_start_time
            if error_duration > self._rate_limit_circuit_break_threshold:
                logger.warning(
                    f"[CIRCUIT BREAKER] Rate limiting persisted for {error_duration / 60:.1f} minutes ({error_duration:.0f}s). "
                    "Attempting to continue with smaller batch size instead of failing completely."
                )

                # Try with progressively smaller batch sizes (10, 5, 1)
                # ISSUE #6 FIX: Stop trying if already spent too long on rate limiting
                if elapsed_sec > max_single_batch_wait * 0.8:  # 8 minutes threshold
                    logger.critical(
                        f"[CIRCUIT BREAKER] Rate limiting {elapsed_sec / 60:.1f}min, approaching timeout. "
                        "Skipping reduced batch size attempts, failing batch immediately."
                    )
                    raise RuntimeError(
                        f"[CIRCUIT BREAKER TIMEOUT] Rate limiting for {elapsed_sec / 60:.1f}min, approaching Step Function timeout. "
                        "yfinance API unavailable - cannot fetch price data."
                    )

                reduced_batch_sizes = [10, 5, 1]
                for reduced_size in reduced_batch_sizes:
                    if reduced_size >= batch_size:
                        continue  # Skip if not smaller than current

                    logger.info(
                        f"[CIRCUIT BREAKER] Retrying with reduced batch size: {reduced_size} (was {batch_size}), elapsed {elapsed_sec:.0f}s"
                    )
                    reduced_attempt = self._fetch_with_fallback(
                        symbols,
                        start,
                        end,
                        batch_size=reduced_size,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                    )
                    if any(v is not None for v in reduced_attempt.values()):
                        logger.info(f"[CIRCUIT BREAKER] âœ“ Partial success with batch={reduced_size}")
                        return reduced_attempt

                # If all reduced sizes failed, emit alert and fail gracefully
                logger.critical(
                    f"[CIRCUIT BREAKER] Rate limiting persisted {error_duration / 60:.1f}min despite batch size reduction. "
                    "yfinance API experiencing degradation. Failing batch. Check yfinance API status."
                )
                try:
                    from algo.reporting import AlertManager

                    alerts = AlertManager()
                    alerts.send_position_alert(
                        "YFINANCE",
                        "RATE_LIMIT_CIRCUIT_BREAK",
                        f"yfinance rate limiting persisted {error_duration / 60:.1f}min despite batch reduction. "
                        f"EOD pipeline may be impacted. {self._rate_limit_errors} rate limit errors detected.",
                        {
                            "duration_seconds": error_duration,
                            "error_count": self._rate_limit_errors,
                        },
                    )
                except Exception as alert_err:
                    logger.debug(f"Could not send rate limit alert: {alert_err}")
                return dict.fromkeys(symbols)

        try:
            result = self._execute_batch_fetch(symbols, start, end)
            if result:
                return self._handle_successful_fetch(result, symbols)
            return result
        except Exception as e:
            error_str = str(e).lower()

            is_circuit_open = "circuit" in error_str.lower() and (
                "open" in error_str.lower() or "unavailable" in error_str.lower()
            )
            if is_circuit_open:
                logger.critical(
                    f"[CIRCUIT_BREAKER] yfinance_prices circuit open: {e}. "
                    "Cannot fetch price data when API is down. Failing fast."
                )
                raise RuntimeError(
                    f"[CIRCUIT_BREAKER] Price data circuit open: {e}. "
                    "Cannot proceed without price data. Waiting for API recovery."
                ) from e

            is_rate_limit = "rate" in error_str or "429" in error_str or "too many" in error_str

            if is_rate_limit:
                return self._handle_rate_limit_error(
                    symbols, start, end, batch_size, attempt, max_attempts, elapsed_sec, e
                )
            else:
                return self._handle_transient_error(
                    symbols, start, end, batch_size, attempt, max_attempts, elapsed_sec, e
                )

    def _try_fetch(self, symbol: str, start: date, end: date, max_retries: int = 5):
        """Try to fetch data from yfinance with retry logic for transient failures."""
        import random
        import time

        for attempt in range(max_retries):
            try:
                return self.router.fetch_ohlcv_interval(symbol, start, end, self.interval)
            except Exception as e:
                error_str = str(e).lower()
                # Rate limit errors - retry with exponential backoff + jitter
                if "rate" in error_str or "429" in error_str or "too many" in error_str:
                    if attempt < max_retries - 1:
                        # ISSUE #23 FIX: Reduced exponential backoff base from 5s to 2s
                        # Prevents long waits: 5 retries at old rate = 310s, new rate = 62s
                        base_wait = min(120, (2**attempt) * 2)  # 2s, 4s, 8s, 16s, 32s, 64s, 128s â†’ capped at 120s
                        jitter = random.uniform(0.9, 1.1)  # Â±10% jitter
                        wait_time = base_wait * jitter
                        logger.warning(
                            f"[{symbol}] Rate limited (attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {wait_time:.1f}s (base {base_wait}s)..."
                        )
                        time.sleep(wait_time)
                        continue
                    raise RuntimeError(
                        f"[{symbol}] Rate limited after {max_retries} attempts. "
                        "Cannot fetch price data when API is rate limited."
                    )
                # Network/timeout errors - retry with backoff + jitter
                if any(x in error_str for x in ["timeout", "json", "parse", "connection", "reset"]):
                    if attempt < max_retries - 1:
                        base_wait = 2**attempt
                        jitter = random.uniform(0.8, 1.2)  # Â±20% jitter for network errors
                        wait_time = base_wait * jitter
                        logger.warning(
                            f"[{symbol}] Transient error (attempt {attempt + 1}/{max_retries}): {e}, "
                            f"retrying in {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    raise RuntimeError(
                        f"[{symbol}] Transient error after {max_retries} attempts: {e}. "
                        "Cannot fetch price data after exhausting retries."
                    )
                # Auth errors - must fail fast
                if "403" in error_str or "401" in error_str or "unauthorized" in error_str:
                    raise RuntimeError(
                        f"[{symbol}] Authentication error accessing price data: {e}. "
                        "Cannot proceed without valid credentials."
                    )
                # Other errors - log and re-raise
                logger.error(f"[{symbol}] Unexpected error: {e}")
                raise
        # Should not reach here, but if we do, raise error
        raise RuntimeError(f"[{symbol}] Exhausted all fetch attempts without successful data fetch")

    def transform(self, rows):
        """Validate and filter rows. Phase 1: Reject invalid ticks. Integrated validation framework."""
        return self.transformer.validate_and_transform(rows, tracker=self.tracker)

    def _validate_row(self, row: dict) -> bool:
        """Add price-range sanity check on top of default PK check."""
        if not super()._validate_row(row):
            return False
        try:
            return cast(bool, row["high"] >= row["low"] and row["close"] > 0 and row["open"] > 0)
        except (KeyError, TypeError) as e:
            raise RuntimeError(
                f"[PRICE_VALIDATION] Price validation failed: row is missing required fields or has invalid types: {e}. "
                "Price data integrity check is mandatory."
            )

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

    def _validate_and_check_preconditions(self) -> None:
        """Validate preflight conditions: schema and market close availability."""
        self._validate_schema_preflight()
        if self.interval == "1d":
            self._validate_market_close_for_1d()

    def _validate_market_close_for_1d(self) -> None:
        """Ensure market close data is available for daily price loads."""
        from algo.infrastructure import MarketCalendar

        today = datetime.now(EASTERN_TZ).date()
        if not MarketCalendar.is_trading_day(today):
            logger.info("[MARKET_CLOSE] Today is not a trading day, skipping check")
            return

        try:
            market_close_available = self._check_market_close_data_available(max_wait_sec=10)
            if not market_close_available:
                raise RuntimeError(
                    "[MARKET_CLOSE] Market close data NOT available. "
                    "Cannot load prices without verifying data is current."
                )
            logger.debug("[MARKET_CLOSE] âœ“ Market close data available")
        except Exception as e:
            raise RuntimeError(
                f"[MARKET_CLOSE] Could not verify market close data: {e}. Cannot load prices without this verification."
            )

    def _execute_batch_jobs(
        self,
        batches: list[list[str]],
        parallelism: int,
        start_time: float,
        total_symbols: int,
    ) -> dict | None:
        """Execute batch jobs concurrently with timeout monitoring and circuit breaker logic.

        Returns:
          - None if all batches completed successfully
          - dict with circuit breaker metrics if halted early

        """
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from config.thresholds import ThresholdConfig

        task_timeout_sec = 25200
        emergency_multiplier = ThresholdConfig.loader_emergency_mode_threshold_multiplier()
        emergency_mode_threshold = task_timeout_sec * emergency_multiplier
        completion_threshold_pct = 0.10
        emergency_mode_enabled = False

        processed = 0
        batch_times = []

        max_concurrent = min(parallelism, 5)
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {executor.submit(self._load_batch, batch): batch for batch in batches}
            for future in as_completed(futures):
                batch = futures[future]
                batch_start = time.time()
                try:
                    future.result()
                except Exception as e:
                    symbols_str = ", ".join(batch[:5]) + ("..." if len(batch) > 5 else "") if batch else "unknown"
                    logger.error(
                        f"Batch {len(batch) if batch else 0} symbols failed: {type(e).__name__}: {str(e)[:200]}\n  Symbols: {symbols_str}\n  Operation: Fetch prices via yfinance\n  Endpoint: Data pipeline",
                        exc_info=True,
                    )

                batch_elapsed = time.time() - batch_start
                batch_times.append(batch_elapsed)
                processed += len(batch)

                result = self._monitor_and_enforce_timeouts(
                    elapsed_sec=time.time() - start_time,
                    processed=processed,
                    total_symbols=total_symbols,
                    batch_times=batch_times,
                    batches_count=len(batches),
                    task_timeout_sec=task_timeout_sec,
                    emergency_mode_threshold=emergency_mode_threshold,
                    completion_threshold_pct=completion_threshold_pct,
                    emergency_mode_enabled=emergency_mode_enabled,
                    batch_elapsed=batch_elapsed,
                    max_concurrent=max_concurrent,
                )
                if result is not None:
                    return result

        return None

    def _monitor_and_enforce_timeouts(
        self,
        elapsed_sec: float,
        processed: int,
        total_symbols: int,
        batch_times: list[float],
        batches_count: int,
        task_timeout_sec: int,
        emergency_mode_threshold: float,
        completion_threshold_pct: float,
        emergency_mode_enabled: bool,
        batch_elapsed: float,
        max_concurrent: int,
    ) -> dict | None:
        """Monitor timeout conditions and enforce circuit breaker logic.

        Returns:
          - dict with early halt metrics if circuit breaker triggered
          - None if execution should continue

        """
        import time

        avg_batch_time = sum(batch_times) / len(batch_times) if batch_times else 0
        completion_pct = processed / total_symbols if total_symbols else 0
        remaining_batches = batches_count - (processed // self.batch_size)
        estimated_remaining_sec = remaining_batches * avg_batch_time

        logger.info(
            "  Progress: %d/%d symbols (%.0f%%) â€” batch: %.1fs, avg: %.1fs, est. %d more min",
            processed,
            total_symbols,
            (completion_pct * 100),
            batch_elapsed,
            avg_batch_time,
            estimated_remaining_sec / 60,
        )

        total_estimated_sec = elapsed_sec + estimated_remaining_sec
        if total_estimated_sec > task_timeout_sec:
            logger.error(
                f"[TIMEOUT_ALERT] ETA ({total_estimated_sec:.0f}s) exceeds task timeout ({task_timeout_sec}s). "
                f"Currently at {completion_pct * 100:.1f}% completion. Triggering emergency mode."
            )
            try:
                from algo.reporting import MetricsPublisher

                m = MetricsPublisher()
                m.put_metric(  # type: ignore
                    "LoaderTimeoutAlert",
                    1,
                    unit="Count",
                    dimensions={
                        "table": self.table_name,
                        "progress_pct": f"{completion_pct * 100:.0f}",
                        "eta_sec": f"{total_estimated_sec:.0f}",
                    },
                )
                m.flush()
            except Exception as metric_err:
                logger.debug(f"Could not publish timeout metric: {metric_err}")

            if not emergency_mode_enabled:
                logger.warning(f"[EMERGENCY] Reducing parallelism from {max_concurrent} to 1 to finish before timeout")

        if batch_elapsed > 120:
            logger.warning(
                f"  [SLOW BATCH] {self.batch_size} symbols took {batch_elapsed:.0f}s â€” "
                "likely yfinance rate limiting. Consider reducing parallelism or checking API status."
            )

        if (
            elapsed_sec > emergency_mode_threshold
            and completion_pct < completion_threshold_pct
            and not emergency_mode_enabled
        ):
            logger.error(
                f"[TIMEOUT_WARNING] At {elapsed_sec / 60:.1f}min, only {completion_pct * 100:.1f}% complete "
                f"(need {completion_threshold_pct * 100:.1f}% by {emergency_mode_threshold / 60:.1f}min). "
                "Will timeout if pace doesn't improve."
            )

        current_batch_size = self._get_adaptive_batch_size()
        circuit_break_threshold_sec = self._rate_limit_circuit_break_threshold
        if current_batch_size < 100 and elapsed_sec > circuit_break_threshold_sec:
            pipeline_context = "EOD (85-min window)" if self._is_eod_pipeline else "Morning prep (450-min window)"
            projected_total_sec = (elapsed_sec / completion_pct) if completion_pct > 0 else 0
            logger.critical(
                f"[CIRCUIT_BREAKER] {pipeline_context}: Rate limit cascade detected! "
                f"Batch size reduced to {current_batch_size} (from 150) after {elapsed_sec / 60:.0f}min. "
                f"Only {completion_pct * 100:.0f}% complete. "
                f"Projected total execution: {projected_total_sec / 60:.0f}min (would exceed deadline). "
                "HALTING to trigger failsafe."
            )
            try:
                from algo.reporting import MetricsPublisher

                m = MetricsPublisher()
                m.put_metric(  # type: ignore
                    "RateLimitCircuitBreaker",
                    1,
                    unit="Count",
                    dimensions={
                        "table": self.table_name,
                        "batch_size": str(current_batch_size),
                        "elapsed_min": str(int(elapsed_sec / 60)),
                        "completion_pct": f"{completion_pct * 100:.0f}",
                    },
                )
                m.flush()
            except (ValueError, ZeroDivisionError, TypeError) as metric_err:
                logger.debug(f"Could not publish circuit breaker metric: {metric_err}")

            logger.warning(
                f"[CIRCUIT_BREAKER] Returning with {processed}/{total_symbols} symbols loaded. "
                "Phase 1 will detect incomplete load and trigger failsafe."
            )
            self._stats["duration_sec"] = round(elapsed_sec, 2)
            self._stats["rate_limit_errors"] = self._rate_limit_errors
            return {
                "loaded": processed,
                "failed": total_symbols - processed,
                "table": self.table_name,
                "circuit_breaker_triggered": True,
                "batch_size_reduced": current_batch_size,
                "elapsed_min": int(elapsed_sec / 60),
            }

        return None

    def _finalize_execution_metrics(self) -> None:
        """Finalize execution: publish metrics, update loader status, attempt final symbol retry."""
        import time
        from datetime import timedelta, timezone

        self._stats["rate_limit_errors"] = self._rate_limit_errors
        if self._rate_limit_error_start_time:
            error_duration_sec = time.time() - self._rate_limit_error_start_time
            self._stats["rate_limit_error_duration_sec"] = round(error_duration_sec, 1)
        else:
            self._stats["rate_limit_error_duration_sec"] = 0

        try:
            from algo.reporting import MetricsPublisher

            with MetricsPublisher() as m:
                m.put_loader_result(self.table_name, self._stats)
                if self._rate_limit_errors > 0:
                    m.put_metric(
                        "RateLimitErrors",
                        self._rate_limit_errors,
                        unit="Count",
                        dimensions={
                            "table": self.table_name,
                            "interval": self.interval,
                        },
                    )
                    if self._stats.get("rate_limit_error_duration_sec", 0) > 0:  # type: ignore
                        m.put_metric(
                            "RateLimitErrorDuration",
                            self._stats["rate_limit_error_duration_sec"],
                            unit="Seconds",
                            dimensions={
                                "table": self.table_name,
                                "interval": self.interval,
                            },
                        )
        except Exception as e:
            logger.debug(f"metrics unavailable: {e}")

        self._update_loader_status()

    def _update_loader_status(self, status: str = "COMPLETED") -> None:
        """Update data_loader_status table with completion metrics."""
        try:
            with DatabaseContext("read") as cur:
                table_safe = assert_safe_table(self.table_name)
                cur.execute(
                    psycopg2.sql.SQL("SELECT COUNT(*), MAX(date) FROM {}").format(psycopg2.sql.Identifier(table_safe))
                )
                result = cur.fetchone()
                total_rows = result[0] if result else 0
                latest_date = result[1] if result else None

            symbols_total = self._stats.get("symbols_total", 1)
            symbols_expected = symbols_total if isinstance(symbols_total, int) else 1
            if "symbols_processed" not in self._stats:
                raise RuntimeError(f"[{self.table_name}] Load stats incomplete: 'symbols_processed' not tracked.")
            symbols_successfully_loaded = self._stats.get("symbols_processed", 0)
            if not isinstance(symbols_successfully_loaded, int):
                symbols_successfully_loaded = 0

            completion_pct = (symbols_successfully_loaded / symbols_expected * 100) if symbols_expected > 0 else 100.0

            loader_status = "COMPLETED" if completion_pct >= 95 else "INCOMPLETE"
            if completion_pct < 95:
                logger.warning(
                    f"[{self.table_name}] Load completed but INCOMPLETE: "
                    f"{symbols_successfully_loaded}/{symbols_expected} symbols ({completion_pct:.1f}%)"
                )

            with DatabaseContext("write") as cur:
                cur.execute(
                    "DELETE FROM data_loader_status WHERE table_name = %s",
                    (self.table_name,),
                )
                from datetime import timezone

                exec_completed_utc = datetime.now(timezone.utc)
                cur.execute(
                    "INSERT INTO data_loader_status "
                    "(table_name, row_count, latest_date, last_updated, status, "
                    "completion_pct, symbol_count, symbols_loaded, execution_started, execution_completed) "
                    "VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s)",
                    (
                        self.table_name,
                        total_rows,
                        latest_date,
                        loader_status,
                        completion_pct,
                        symbols_expected,
                        symbols_successfully_loaded,
                        self._stats.get("start_time"),
                        exec_completed_utc,
                    ),
                )

            try:
                # CRITICAL FIX #5: Use proper fail-fast cache invalidation with three-tier approach
                # (not just inline deletion with defensive silent failure)
                _invalidate_phase1_cache()
            except RuntimeError as cache_err:
                # Cache invalidation failed after exhausting all retry strategies.
                # This means Phase 1 might use stale data = data corruption risk.
                # Must halt loader to maintain data integrity.
                logger.critical(
                    f"[CACHE INVALIDATION] CRITICAL FAILURE in _finalize_loader_metadata: {cache_err}"
                )
                raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Failed to update data_loader_status for {self.table_name}: {e}")

    def run(  # type: ignore
        self, symbols: list, parallelism: int = 1, backfill_days: int | None = None
    ) -> dict:
        """Override to use batch fetching (50x faster than per-symbol) + concurrent batches."""
        if backfill_days is not None:
            self._backfill_days = backfill_days

        import time
        from datetime import timezone

        self._validate_schema_preflight()

        start = time.time()
        self._stats["start_time"] = datetime.now(timezone.utc)
        symbols = list(symbols)
        mode = f" (backfill {self._backfill_days}d)" if self._backfill_days > 0 else ""
        logger.info(
            "[%s] [%s] Starting batch load: %d symbols (batch_size=%d, concurrency=%d)%s",
            self._correlation_id,
            self.table_name,
            len(symbols),
            self.batch_size,
            parallelism,
            mode,
        )

        if self.interval == "1d" and self._is_eod_pipeline:
            logger.info("[SLA_OPT] Skipping 1d price load during EOD pipeline â€” reusing morning prep data")
            return {"symbols_loaded": 0, "symbols_failed": 0, "rows_inserted": 0}

        self._validate_and_check_preconditions()

        batches = [symbols[i : i + self.batch_size] for i in range(0, len(symbols), self.batch_size)]
        self._stats["symbols_total"] = len(symbols)

        circuit_breaker_result = self._execute_batch_jobs(batches, parallelism, start, len(symbols))
        if circuit_breaker_result is not None:
            return circuit_breaker_result

        self._stats["duration_sec"] = round(time.time() - start, 2)
        self._finalize_execution_metrics()

        logger.info(
            "[%s] [%s] Done. fetched=%d dedup_skip=%d quality_drop=%d inserted=%d "
            "(processed=%d skipped_wm=%d failed=%d) %.1fs sources=%s rate_limit_errors=%d",
            self._correlation_id,
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
            self._rate_limit_errors,
        )

        return self._stats

    def _load_batch(self, symbols: list[str]) -> None:
        """Load a batch of symbols using batch API fetch (50x reduction in API calls)."""
        wm_store = self._get_watermark()

        # Determine the watermark date for all symbols in batch
        # (simplified: use same date for all, finest-grained would be per-symbol)
        if self._backfill_days > 0:
            # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
            previous_date = datetime.now(EASTERN_TZ).date() - timedelta(days=self._backfill_days)
        else:
            # Use earliest watermark from batch
            watermarks = [wm_store.get(s) if wm_store else None for s in symbols]
            previous_dates = [self._parse_watermark_date(w) for w in watermarks]
            previous_date = (
                min(d for d in previous_dates if d) if any(previous_dates) else None  # type: ignore[assignment]
            )

        # Batch fetch all symbols at once
        batch_results = self.fetch_batch_incremental(symbols, previous_date)

        # Process each symbol's results
        for symbol in symbols:
            rows = batch_results.get(symbol) if batch_results else None
            if not rows:
                logger.debug(f"[{self.table_name}] {symbol}: No rows fetched (watermark current), skipping")
                self._stats["symbols_skipped_by_watermark"] += 1  # type: ignore
                self._stats[  # type: ignore
                    "symbols_processed"
                ] += 1  # Count as processed (no new data needed, not a failure)
                continue

            logger.debug(f"[{self.table_name}] {symbol}: Fetched {len(rows)} rows from batch")
            self._stats["rows_fetched"] += len(rows)  # type: ignore

            if self.router and self.router.last_source:
                src = self.router.last_source
                self._stats["source_distribution"][src] = (  # type: ignore
                    self._stats["source_distribution"].get(src, 0) + 1  # type: ignore
                )

            rows = self.transform(rows)
            before_quality = len(rows)
            rows = [r for r in rows if self._validate_row(r)]
            self._stats["rows_quality_dropped"] += before_quality - len(rows)  # type: ignore

            # Bloom dedup (cheap pre-filter)
            # SKIP for price_daily: EOD price data is immutable, dedup not needed
            # Prevents filtering out fresh May 23 data that yfinance returns with May 22 date
            dedup = None  # self._get_dedup()
            if dedup and self.primary_key:
                before_dedup = len(rows)
                rows = self._dedup_filter(dedup, rows)
                self._stats["rows_dedup_skipped"] += before_dedup - len(rows)

            if not rows:
                self._stats["symbols_processed"] += 1  # type: ignore
                continue

            # Calculate new watermark BEFORE insert
            new_wm = self.watermark_from_rows(rows)

            # Bulk insert in chunks
            inserted = 0
            for chunk_start in range(0, len(rows), self.chunk_size):
                chunk = rows[chunk_start : chunk_start + self.chunk_size]
                is_final_chunk = chunk_start + self.chunk_size >= len(rows)
                chunk_wm = new_wm if is_final_chunk else None
                inserted += self._bulk_insert(
                    chunk,
                    symbol=symbol if is_final_chunk else None,
                    new_watermark=chunk_wm,
                )

            if dedup and self.primary_key:
                for row in rows:
                    key = ":".join(str(row.get(c, "")) for c in self.primary_key)
                    dedup.add(key)

            self._stats["rows_inserted"] += inserted  # type: ignore
            self._stats["symbols_processed"] += 1  # type: ignore


def _invalidate_phase1_cache():
    """Invalidate Phase 1 cache to force fresh status check on next run.

    Called on loader failure to ensure Phase 1 doesn't use stale cached data.
    CRITICAL: If invalidation fails, marks cache with 'invalidation_failed' flag
    so Phase 1 knows not to use it. If that also fails, raises RuntimeError to
    halt the loader and prevent silent stale-data use.

    ISSUE #2 FIX: Three-tier approach:
    1. Try to delete cache (best case)
    2. If delete fails, mark as poisoned so Phase 1 skips it
    3. If both fail and not a permission error, halt loader immediately
    4. If permission error, log warning and allow loader to continue
    """
    from datetime import datetime

    import boto3
    from botocore.exceptions import ClientError

    # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
    try:
        cache_date = datetime.now(EASTERN_TZ).date()
        cache_key = f"data_loader_status-{cache_date.isoformat()}"
        cache_table_name = os.getenv("CACHE_TABLE", "algo_phase1_cache")
        dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
        cache_table = dynamodb.Table(cache_table_name)

        try:
            # Step 1: Try direct deletion
            cache_table.delete_item(Key={"cache_key": cache_key})
            logger.info(f"[CACHE INVALIDATION] âœ“ Successfully deleted Phase 1 cache: {cache_key}")
            return
        except ClientError as delete_err:
            error_dict = delete_err.response.get("Error")
            if error_dict and error_dict.get("Code") in ("AccessDenied", "AccessDeniedException"):
                logger.warning(
                    "[CACHE INVALIDATION] âš  Permission denied (DELETE): No DynamoDB write access. "
                    "Loader will proceed without cache invalidation (risk: may use stale data from previous run)."
                )
                return
            logger.error(
                f"[CACHE INVALIDATION] âœ— DELETE FAILED: {type(delete_err).__name__}: {delete_err}. Attempting cache poisoning..."
            )
        except Exception as delete_err:
            logger.error(
                f"[CACHE INVALIDATION] âœ— DELETE FAILED: {type(delete_err).__name__}: {delete_err}. Attempting cache poisoning..."
            )

        # Step 2: If delete failed, try to poison the cache so Phase 1 knows not to use it
        try:
            from decimal import Decimal

            cache_table.update_item(
                Key={"cache_key": cache_key},
                UpdateExpression="SET invalidation_failed = :true, poisoned_at = :now",
                ExpressionAttributeValues={
                    ":true": True,
                    ":now": Decimal(str(time.time())),
                },
            )
            logger.warning(
                "[CACHE INVALIDATION] âœ“ POISONED cache (set invalidation_failed=true) - Phase 1 will skip stale data"
            )
            return
        except ClientError as poison_err:
            error_dict = poison_err.response.get("Error")
            if error_dict and error_dict.get("Code") in ("AccessDenied", "AccessDeniedException"):
                logger.warning(
                    "[CACHE INVALIDATION] âš  Permission denied (UPDATE): No DynamoDB write access. "
                    "Loader will proceed without cache invalidation (risk: may use stale data from previous run)."
                )
                return
            logger.error(f"[CACHE INVALIDATION] âœ— POISONING ALSO FAILED: {type(poison_err).__name__}: {poison_err}")
        except (ValueError, ZeroDivisionError, TypeError) as poison_err:
            logger.error(f"[CACHE INVALIDATION] âœ— POISONING ALSO FAILED: {type(poison_err).__name__}: {poison_err}")

    except (ValueError, ZeroDivisionError, TypeError) as setup_err:
        logger.error(f"[CACHE INVALIDATION] Setup error: {setup_err}")

    # Step 3: Both deletion AND poisoning failed - CRITICAL: MUST HALT
    logger.critical(
        "[CACHE INVALIDATION] âœ—âœ— CRITICAL FAILURE: Could not delete OR poison cache. "
        "Phase 1 will potentially use stale data. HALTING LOADER IMMEDIATELY."
    )
    raise RuntimeError(
        "CRITICAL: Cache invalidation completely failed (cannot delete or poison). "
        "Halting loader to prevent silent stale-data corruption."
    )


def log_loader_execution(
    loader_name,
    table_name,
    status,
    records_loaded=0,
    records_updated=0,
    error_msg=None,
    duration_seconds=0,
):
    """Log loader execution to data_loader_runs table for monitoring."""
    try:
        with DatabaseContext("write") as cur:
            # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
            run_date = datetime.now(EASTERN_TZ).date()
            cur.execute(
                """
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
            """,
                (
                    loader_name,
                    table_name,
                    run_date,
                    status,
                    records_loaded,
                    records_updated,
                    error_msg,
                    duration_seconds,
                ),
            )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.critical(f"[LOADER_EXECUTION_LOG] Failed to log execution to data_loader_runs: {e}")
        raise


def main():
    """Read config from environment variables (set by ECS task definition)."""
    start_time = time.time()

    # Setup socket-level timeouts to prevent hanging on network operations
    from loaders.loader_helper import setup_loader_timeouts

    setup_loader_timeouts(socket_timeout_sec=30.0)

    logger.info(f"[{_correlation_id}] [MAIN] Starting price loader instance")

    try:
        logger.info(f"[{_correlation_id}] [MAIN] Environment loaded successfully")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[MAIN] Failed to load environment: {e}", exc_info=True)
        try:
            _invalidate_phase1_cache()
        except RuntimeError as cache_err:
            logger.critical(f"[MAIN] Cache invalidation failed on environment error: {cache_err}")
        try:
            log_loader_execution(
                "loadpricedaily",
                "price_daily",
                "failed",
                error_msg=str(e),
                duration_seconds=round(time.time() - start_time, 2),
            )
        except Exception as log_err:
            raise RuntimeError(
                f"[MAIN] Could not log environment loading failure to audit trail: {log_err}. "
                "Audit trail integrity is mandatory for Phase 7 reconciliation."
            )

    # Read from environment variables (no CLI args, cleaner for containerized execution)
    intervals_str = os.getenv("LOADER_INTERVALS", "1d,1wk,1mo")
    asset_classes_str = os.getenv("LOADER_ASSET_CLASSES", "stock,etf")
    symbols_str = os.getenv("LOADER_SYMBOLS", "")
    # CRITICAL: Use higher parallelism for stock_prices_daily to complete in reasonable time
    # Loading 5000 symbols Ã— 3 intervals = 15000+ records; parallelism=2 takes 6+ hours
    # parallelism=8 reduces to ~2 hours while RDS Proxy handles connection pooling
    # FIXED Issue #13: Read parallelism from DynamoDB (dynamic), fallback to env var
    parallelism = get_parallelism("stock_prices_daily")
    max_symbols_limit = int(os.getenv("LOADER_MAX_SYMBOLS", "0"))  # 0 = no limit (loads all symbols)

    # Parse comma-separated values
    intervals = [x.strip() for x in intervals_str.split(",")]
    asset_classes = [x.strip() for x in asset_classes_str.split(",")]

    # Set execution timeout (ECS task timeout for price loader is 7200s = 2h)
    # BLOCK-006 FIX: Add timeout enforcement with signal handler to prevent hanging
    execution_timeout_sec = 7200

    import signal

    def timeout_handler(signum, frame):
        logger.critical(f"[TIMEOUT] Price loader exceeded {execution_timeout_sec}s timeout. Killing process.")
        raise TimeoutError(f"Execution exceeded {execution_timeout_sec}s timeout")

    # SIGALRM only available on Unix; skip on Windows
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(execution_timeout_sec)
    else:
        logger.debug("[TIMEOUT] SIGALRM not available (Windows). Using process-level timeout instead.")

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
        from utils.db.connection import get_db_connection

        _lock_conn = get_db_connection(timeout=30)
        _lock_conn.autocommit = True
        with _lock_conn.cursor() as _cur:
            _cur.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s)::bigint)",
                ("stock_prices_daily",),
            )
            acquired = _cur.fetchone()[0]
        if not acquired:
            logger.warning("[MAIN] Skipping: another stock_prices_daily instance already running (advisory lock held)")
            try:
                _lock_conn.close()
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as close_err:
                logger.debug(f"Could not close lock connection: {close_err}")
            _lock_conn = None
            return 0
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as _lock_err:
        logger.warning(
            "[MAIN] Advisory lock check failed (%s) â€” proceeding without lock",
            _lock_err,
        )
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
                try:
                    log_loader_execution(
                        "loadpricedaily",
                        "price_daily",
                        "failed",
                        error_msg="No symbols found",
                        duration_seconds=round(time.time() - start_time, 2),
                    )
                except (ValueError, ZeroDivisionError, TypeError) as log_err:
                    logger.critical(f"[MAIN] Could not log loader failure to audit trail: {log_err}")
                return 1
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"[MAIN] Failed to get symbols: {e}", exc_info=True)
        try:
            _invalidate_phase1_cache()
        except RuntimeError as cache_err:
            logger.critical(f"[MAIN] Cache invalidation failed on symbols error: {cache_err}")
        try:
            log_loader_execution(
                "loadpricedaily",
                "price_daily",
                "failed",
                error_msg=str(e),
                duration_seconds=round(time.time() - start_time, 2),
            )
        except (ValueError, ZeroDivisionError, TypeError) as log_err:
            raise RuntimeError(
                f"[MAIN] Could not log symbols loading failure to audit trail: {log_err}. "
                "Audit trail integrity is mandatory for Phase 7 reconciliation."
            )

    # Essential symbols that must be present in price_daily regardless of what stock_symbols contains.
    # stock_symbols excludes ETFs, so these never appear via get_active_symbols().
    # SPY is required by: load_technical_data_daily (Mansfield RS), load_seasonality,
    #   load_market_health_daily breadth check, and algo_market_exposure yield-curve factor.
    # GLD/TLT are used by the correlation matrix endpoint and macro regime logic.
    essential_stock_price_daily = ["SPY", "QQQ", "IWM", "DIA", "GLD", "TLT"]

    # Sector ETFs: required by load_sector_performance (YTD returns), SectorHeatMap,
    # and the prices route /api/prices/history/{etf} called by the frontend.
    # These land in etf_price_daily (the prices route falls back to this table).
    essential_etf_symbols = [
        "SPY",
        "QQQ",
        "IWM",
        "DIA",  # Index ETFs â€” IndicesStrip sparklines
        "XLK",
        "XLF",
        "XLV",
        "XLY",
        "XLC",  # Sector ETFs â€” SectorHeatMap + sector_performance
        "XLI",
        "XLP",
        "XLE",
        "XLU",
        "XLRE",
        "XLB",
        "GLD",
        "TLT",
        "IVV",
        "VXX",  # Macro ETFs â€” correlation matrix
    ]

    # CREATIVE FIX #5: Interval staggering with time delays
    # Instead of loading 1d, 1wk, 1mo sequentially (causing API load spike),
    # stagger them with delays to spread pressure over time and prevent rate limiting.
    # This is especially effective because 1mo is less critical than 1d and can tolerate delay.
    interval_stagger_delays = {
        "1d": 0,  # Load 1d immediately (most critical)
        "1wk": 60,  # Stagger weekly 60s later (spreads API load)
        "1mo": 120,  # Stagger monthly 120s later (least critical)
    }

    # Run price loader for each interval + asset_class combination
    total_stats = {"symbols_loaded": 0, "symbols_failed": 0, "rows_inserted": 0}
    fail_count = 0

    from utils.infrastructure.timeout import ExecutionTimeout

    try:
        with ExecutionTimeout(max_seconds=execution_timeout_sec, label="stock_prices_daily"):
            for asset_class in asset_classes:
                for interval in intervals:
                    try:
                        # CREATIVE FIX #5: Apply interval staggering delay
                        stagger_delay = interval_stagger_delays.get(interval, 0)
                        if stagger_delay > 0:
                            logger.info(
                                f"[CREATIVE FIX #5] Staggering {interval} load by {stagger_delay}s to spread API pressure..."
                            )
                            time.sleep(stagger_delay)

                        # Build per-asset-class symbol list.
                        # dict.fromkeys preserves insertion order and deduplicates.
                        if asset_class == "stock":
                            run_symbols = list(dict.fromkeys(symbols + essential_stock_price_daily))
                            logger.info(
                                f"[MAIN] stock symbols: {len(symbols)} from DB + {len(essential_stock_price_daily)} essential ETFs = {len(run_symbols)} total"
                            )
                        else:  # etf
                            # ETF tables (etf_price_daily/weekly/monthly) should only contain ETF symbols,
                            # not the 5000+ non-ETF stocks. Loading all non-ETF stocks into ETF tables
                            # was doubling the data load (~600 extra batches), causing the ECS task to
                            # time out before completing stock price updates for L-Z symbols.
                            run_symbols = list(dict.fromkeys(essential_etf_symbols))
                            logger.info(
                                f"[MAIN] etf symbols: {len(run_symbols)} essential ETFs only (sector, index, macro ETFs)"
                            )

                        loader = PriceLoader(interval=interval, asset_class=asset_class)
                        logger.info(
                            f"[MAIN] Starting: interval={interval}, asset_class={asset_class}, parallelism={parallelism}"
                        )
                        with TimeBlock(f"loadpricedaily_{asset_class}_{interval}"):
                            stats = loader.run(run_symbols, parallelism=parallelism)

                        logger.info(f"[MAIN] Completed {asset_class}/{interval}: {stats}")
                        # Validate stats dict has required keys
                        for required_key in ["symbols_processed", "symbols_failed", "rows_inserted"]:
                            if required_key not in stats:
                                raise RuntimeError(f"Stats dict missing required key '{required_key}': {stats}")

                        total_stats["symbols_loaded"] += stats["symbols_processed"]
                        total_stats["symbols_failed"] += stats["symbols_failed"]
                        total_stats["rows_inserted"] += stats["rows_inserted"]

                        fail_rate = stats["symbols_failed"] / max(len(run_symbols), 1)
                        if fail_rate > 0.10:
                            logger.error(
                                f"Too many failures for {asset_class}/{interval}: {stats['symbols_failed']}/{len(run_symbols)} ({fail_rate * 100:.1f}%)"
                            )
                            fail_count += 1
                        else:
                            logger.info(
                                f"Acceptable failure rate for {asset_class}/{interval}: {stats['symbols_failed']}/{len(run_symbols)} ({fail_rate * 100:.1f}%)"
                            )

                        loader.close()
                    except Exception as e:
                        logger.error(
                            f"[MAIN] Loader failed for {asset_class}/{interval}: {e}",
                            exc_info=True,
                        )
                        try:
                            _invalidate_phase1_cache()
                        except RuntimeError as cache_err:
                            logger.critical(f"[MAIN] Cache invalidation failed on loader error: {cache_err}")
                        raise RuntimeError(
                            f"[MAIN] Loader failed for {asset_class}/{interval}: {e}. "
                            "Cannot proceed with price loading if an interval fails."
                        )
    except Exception as timeout_err:
        logger.critical(f"[MAIN] Loader execution timeout exceeded: {timeout_err}")
        try:
            _invalidate_phase1_cache()
        except RuntimeError as cache_err:
            logger.critical(f"[MAIN] Cache invalidation failed on timeout error: {cache_err}")
        duration_seconds = round(time.time() - start_time, 2)
        try:
            log_loader_execution(
                "loadpricedaily",
                "price_daily",
                "failed",
                error_msg=f"Execution timeout: {timeout_err}",
                duration_seconds=duration_seconds,
            )
        except Exception as log_err:
            raise RuntimeError(
                f"[MAIN] Could not log timeout failure to audit trail: {log_err}. "
                "Audit trail integrity is mandatory for Phase 7 reconciliation."
            )

    logger.info(f"[MAIN] All intervals completed. Total: {total_stats}")

    duration_seconds = round(time.time() - start_time, 2)
    if fail_count > 0:
        logger.error(f"[MAIN] {fail_count} interval(s) had too many failures")
        try:
            _invalidate_phase1_cache()
        except RuntimeError as cache_err:
            logger.critical(f"[MAIN] Cache invalidation failed on final failure: {cache_err}")
        try:
            if "rows_inserted" not in total_stats:
                raise RuntimeError("total_stats missing 'rows_inserted' key")
            log_loader_execution(
                "loadpricedaily",
                "price_daily",
                "failed",
                records_loaded=total_stats["rows_inserted"],
                error_msg=f"{fail_count} interval(s) failed",
                duration_seconds=duration_seconds,
            )
        except Exception as log_err:
            raise RuntimeError(
                f"[MAIN] Could not log multi-interval failure to audit trail: {log_err}. "
                "Audit trail integrity is mandatory for Phase 7 reconciliation."
            )

    try:
        if "rows_inserted" not in total_stats:
            raise RuntimeError("total_stats missing 'rows_inserted' key")
        log_loader_execution(
            "loadpricedaily",
            "price_daily",
            "completed",
            records_loaded=total_stats["rows_inserted"],
            duration_seconds=duration_seconds,
        )
    except Exception as log_err:
        raise RuntimeError(
            f"[MAIN] Could not log loader completion to audit trail: {log_err}. "
            "Audit trail integrity is mandatory for Phase 7 reconciliation."
        )
    if _lock_conn:
        try:
            _lock_conn.close()
        except Exception as close_err:
            logger.debug(f"Could not close lock connection: {close_err}")
    return 0


if __name__ == "__main__":
    try:
        result = main()
        sys.exit(result if result is not None else 0)
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)
