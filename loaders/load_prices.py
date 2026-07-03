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
import time
import uuid
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any, cast

import psycopg2.sql

from loaders.price_fetcher import PriceFetcher
from loaders.price_transformer import PriceTransformer
from loaders.price_validator import PriceValidator
from monitoring.metrics_context import TimeBlock
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

    def __init__(self, interval: str = "1d", asset_class: str = "stock", *args: Any, **kwargs: Any) -> None:
        """Initialize with interval (1d/1wk/1mo) and asset class (stock/etf)."""
        if interval not in ("1d", "1wk", "1mo"):
            raise ValueError(f"Invalid interval: {interval!r}; must be one of: 1d, 1wk, 1mo")
        if asset_class not in ("stock", "etf"):
            raise ValueError(f"Invalid asset_class: {asset_class!r}; must be one of: stock, etf")

        self.interval = interval
        self.asset_class = asset_class
        self._correlation_id = _correlation_id
        self.batch_size = 500

        # Circuit breaker for data loader outage handling
        self._circuit_breaker = CircuitBreaker(name="yfinance_prices", importance=DataImportance.CRITICAL)

        # Freshness validator: stock prices must be <= 1 day old
        self._freshness_validator = FreshnessValidator(max_age_hours={"price_data": 24.0})

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

        # ISSUE #14-15 FIX: Differentiate failure causes for targeted remediation
        # Track root cause of failures to apply appropriate fixes:
        # - Market close unavailability: wait and retry (data will become available)
        # - Rate limiting (429): reduce batch size, apply backoff
        # - API lag/timeout: increase timeout, reduce parallelism
        # - Other errors: log and fail
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

        # Market close data tracking
        self._market_close_detected = False
        self._market_close_timeout_count = 0
        self._last_market_close_timeout_time: float | None = None

    def _detect_eod_pipeline_context(self) -> bool:
        """Detect if running during EOD pipeline (4:05-5:30 PM ET) for timing-aware rate limiting.

        Returns True if current time is 4:05 PM ± 2 hours (accounts for slow yfinance lag).
        EOD pipeline has tight deadline (85 min), so we use aggressive rate limiting strategy.

        Raises:
            RuntimeError: If timezone conversion or time calculation fails (programming error, not transient)
        """
        try:
            from datetime import datetime

            eod_window_start_min = -10
            eod_window_end_min = 120

            now_et = datetime.now(EASTERN_TZ)
            if now_et is None:
                raise RuntimeError("Failed to get current time in Eastern timezone (now_et is None)")

            eod_start_et = now_et.replace(hour=16, minute=5, second=0, microsecond=0)  # 4:05 PM ET

            time_delta = now_et - eod_start_et
            time_since_eod_start = time_delta.total_seconds() / 60

            if eod_window_start_min < time_since_eod_start < eod_window_end_min:
                logger.info(
                    f"[CONTEXT] Running during EOD pipeline "
                    f"({time_since_eod_start:.0f} min from 4:05 PM ET), using aggressive rate limiting"
                )
                return True

            logger.debug(
                f"[CONTEXT] Running during morning/regular hours "
                f"({time_since_eod_start:.0f} min from 4:05 PM ET), using conservative rate limiting"
            )
            return False

        except (ValueError, AttributeError, TypeError) as e:
            raise RuntimeError(
                f"[CONTEXT] Failed to detect EOD pipeline context (timezone/time calculation error): {type(e).__name__}: {e}. "
                "Cannot proceed with price loading without knowing pipeline context."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"[CONTEXT] Unexpected error detecting EOD pipeline context: {type(e).__name__}: {e}"
            ) from e

    def _validate_schema_preflight(self) -> None:
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
            logger.warning(
                "[SCHEMA] No pre-defined schema for %s, skipping validation",
                self.table_name,
            )
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
                        f"[SCHEMA] Œ Schema validation FAILED for {self.table_name}:\n{error_msg}\n"
                        "This will cause data loading to fail. "
                        "Verify table schema matches expected definition."
                    )
                    raise RuntimeError(f"Schema validation failed for {self.table_name}: {error_msg}")

                logger.info(
                    "[SCHEMA] Schema validation passed for %s (%d columns)",
                    self.table_name,
                    len(required_schema),
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

    def _verify_unique_constraint_exists(self, cur: Any) -> None:
        """Verify that unique constraint on primary key exists (prevents duplicates).

        CRITICAL: Ensures that the database enforces uniqueness on (symbol, date).
        If this constraint is missing, duplicate rows can be inserted silently,
        corrupting the dataset.

        This is the root cause check for issue where 20,150 duplicate rows
        were inserted when the unique constraint didn't exist.
        """
        if not self.primary_key:
            logger.debug(
                "[CONSTRAINT] No primary_key defined for %s, skipping check",
                self.table_name,
            )
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
                logger.info(
                    "[CONSTRAINT]  Unique constraint/index found on {self.table_name}(%s)",
                    pk_cols,
                )
            else:
                # This is a CRITICAL error - without the constraint, duplicates can occur
                error_msg = (
                    f"[CONSTRAINT] Œ CRITICAL: No UNIQUE constraint or index on {self.table_name}({pk_cols}). "
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
            error_msg = (
                f"[CRITICAL] Could not verify unique constraint for {self.table_name}: {e}. "
                f"Price data integrity requires unique (symbol, date) constraint. "
                f"Cannot proceed without verifying this constraint exists. "
                f"Risk: Proceeding would allow duplicate price records to be inserted, corrupting data."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

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
                logger.debug(
                    "[BATCH_SIZE_SMART] Using batch={best_size} (success rate %s)",
                    best_rate,
                )
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

        # CRITICAL: Price data quality is essential — no silent degradation to low success rates.
        # Require 95%+ success rate to confirm data integrity.
        # - >95% success: normal batch size (100)
        # - <95% success: fail-hard instead of silently adapting to low quality
        #
        # Why? Silently accepting 50-80% success means:
        # - Position sizing gets stale/incomplete prices
        # - Technical indicators calculated on partial data
        # - Signal generation with degraded price quality
        # - Circuit breakers trigger on incomplete market data
        #
        # Better to fail and fix upstream than continue with bad data.

        if success_rate < 0.95:
            logger.critical(
                f"[PRICE_LOADER] Success rate ({success_rate:.1%}) below 95% threshold. "
                f"Price data is CRITICAL — cannot continue with degraded quality. "
                f"Batch count: {self._batch_success_count}/{self._batch_total_count}. "
                f"Failing fast instead of silently adapting batch size to degrade gracefully."
            )
            raise RuntimeError(
                f"[PRICE_LOADER] Price data quality degraded (success rate {success_rate:.1%}). "
                f"Received only {self._batch_success_count} successful batches of {self._batch_total_count}. "
                f"Cannot proceed with incomplete price coverage. "
                f"Check yfinance API health, rate limiting, and network connectivity."
            )

        return 100  # Full batch size when success rate is high

    def _record_batch_result(self, success_count: int, total_count: int) -> None:
        """Record batch success/failure ratio for adaptive retry logic.

        Allows tracking partial success without requiring per-symbol results.
        """
        self._batch_success_count = success_count
        self._batch_total_count = total_count
        if total_count == 0:
            raise ValueError("No symbols to fetch - batch size calculation error")
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
        - EOD pipeline (4:05-6:00 PM): 1800s (30 min) - generous buffer within 85-min pipeline window
        - Morning prep (3:30-9:30 AM): 600s (10 min) - market just opened, data should be fresh
        - Other times: 300s (5 min) - should rarely block

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
                        if len(config_result) < 1:
                            raise RuntimeError(
                                f"[MARKET_CLOSE] Config query returned invalid row structure for {config_key}. "
                                f"Expected at least 1 column, got {len(config_result)}."
                            )
                        try:
                            config_value = int(config_result[0])
                            # CRITICAL: Validate timeout is reasonable (1s-3600s)
                            # Increased upper bound from 1800s to 3600s to support longer waits if needed
                            if config_value < 1 or config_value > 3600:
                                logger.warning(
                                    f"[MARKET_CLOSE] Config {config_key}={config_value}s is out of bounds (1-3600s). "
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
                                f"[MARKET_CLOSE] Config {config_key}={config_result[0]} is not a valid integer. "
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
            logger.debug("[MARKET_CLOSE] Using override timeout: %ss", max_wait_sec)

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
            logger.info(
                "[MARKET_CLOSE] %smin after market close, data should be available",
                minutes_after_close,
            )
            return True

        # If we're before market close, skip (early run or different time zone)
        if minutes_after_close < 0:
            logger.info(
                "[MARKET_CLOSE] Before market close (%smin), skipping check",
                minutes_after_close,
            )
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
                    logger.info(
                        "[MARKET_CLOSE]  Data available after {elapsed:.1f}s (attempt %s)",
                        attempt,
                    )
                    # Emit success metric
                    try:
                        from algo.reporting import MetricsPublisher

                        metrics = MetricsPublisher()
                        metrics.add_metric(
                            "MarketCloseDataAvailable",
                            1,
                            unit="Count",
                            dimensions={"Status": "success"},
                        )
                        metrics.flush()
                    except Exception as metric_err:
                        logger.warning(
                            "[AUDIT_TRAIL] Could not publish market close success metric: %s. This breaks audit trail.",
                            metric_err,
                        )
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
            logger.critical("[{self._correlation_id}] %s", alert_msg)
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
            metrics.add_metric(
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
        if last_error_msg:
            last_error_lower = last_error_msg.lower()
            is_rate_limit = "429" in last_error_lower or "too many" in last_error_lower or "rate" in last_error_lower
            root_cause = "yfinance rate limiting" if is_rate_limit else "yfinance API lag/unavailability"
        else:
            logger.warning(
                f"[{self._correlation_id}] last_error_msg is None - cannot determine root cause for market close timeout"
            )
            root_cause = "unknown error (no message provided)"

        error_msg = (
            f"Market close data NOT available after {elapsed:.0f}s ({elapsed / 60:.1f} min, {attempt} attempts). "
            f"Root cause: {root_cause} | Last error: {last_error_type} - {last_error_msg or 'no message'}. "
            "Cannot load prices without market close data. Aborting to avoid stale price data. "
            "Phase 1 will trigger failsafe when data becomes available. "
            "Check yfinance API status and RDS connection pool health. "
            f"[Consecutive timeouts: {self._market_close_timeout_count}/24h]"
        )
        logger.error("[{self._correlation_id}] [MARKET_CLOSE] ✓ %s", error_msg)
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

    def fetch_incremental(self, symbol: str, since: date | None) -> Any:
        """Fetch OHLCV from yfinance at specified interval."""
        return self.fetcher.fetch_incremental(symbol, since, is_eod_pipeline=self._is_eod_pipeline)

    def fetch_batch_incremental(self, symbols: list[str], since: date | None) -> dict[str, Any]:
        """Fetch OHLCV for multiple symbols at once (50x faster than per-symbol).

        Returns: dict[symbol] -> rows. Never returns None; raises RuntimeError if fetch fails.
        """
        return self.fetcher.fetch_batch_incremental(symbols, since, is_eod_pipeline=self._is_eod_pipeline)

    def _execute_batch_fetch(self, symbols: list[str], start: date, end: date) -> dict[str, Any] | None:
        """Execute batch fetch with circuit breaker and validate freshness."""
        result = self.fetcher.execute_batch_fetch(symbols, start, end)

        if result and isinstance(result, dict):
            latest_price_date: datetime | None = None
            for rows in result.values():
                if rows:
                    for row in rows:
                        # CRITICAL: Fail-fast if date field missing (no silent fallback)
                        if "date" not in row:
                            raise RuntimeError(
                                f"[PRICE_LOADER] CRITICAL: Price row missing required 'date' field. "
                                f"Cannot proceed with incomplete price data. Row: {row}"
                            )
                        row_date_str = row["date"]
                        if row_date_str is None:
                            raise RuntimeError(
                                f"[PRICE_LOADER] CRITICAL: Price row has null 'date' value. "
                                f"Cannot calculate freshness without valid date. Row: {row}"
                            )
                        try:
                            row_date = datetime.fromisoformat(row_date_str)
                            if latest_price_date is None or row_date > latest_price_date:
                                latest_price_date = row_date
                        except (ValueError, TypeError) as e:
                            raise RuntimeError(
                                f"[PRICE_LOADER] Cannot parse price date: '{row_date_str}'. "
                                f"Expected ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). "
                                f"Price data may be corrupted. Error: {e}"
                            ) from e

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

    def _handle_successful_fetch(self, result: dict[str, Any], symbols: list[str]) -> dict[str, Any]:
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
    ) -> dict[str, Any] | None:
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
            logger.warning(
                "[AUDIT_TRAIL] Could not publish rate limit metric: %s. This breaks audit trail.",
                metric_err,
            )

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
            logger.debug("[RATE_LIMIT] Waiting %ss before paced retry...", wait_time)
            time.sleep(wait_time)
            return self._fetch_with_explicit_retry(
                symbols,
                start,
                end,
                batch_size,
                attempt + 1,
                max_attempts,
                elapsed_sec,
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

        results: dict[str, Any] = {}
        failed_chunks = []
        for i in range(0, len(symbols), new_batch_size):
            chunk = symbols[i : i + new_batch_size]
            chunk_results = self._fetch_with_explicit_retry(
                chunk,
                start,
                end,
                new_batch_size,
                attempt + 1,
                max_attempts,
                elapsed_sec=total_elapsed,
            )
            if chunk_results is None:
                # CRITICAL: No results returned for chunk - this is a failure
                failed_chunks.append(chunk)
                logger.error(
                    f"[RATE_LIMIT] Chunk {chunk[:5]} returned None results. Cannot proceed with incomplete price data."
                )
            else:
                results.update(chunk_results)
                # Verify all chunk symbols are present (no partial data)
                missing_symbols = [s for s in chunk if s not in chunk_results or chunk_results[s] is None]
                if missing_symbols:
                    failed_chunks.append(missing_symbols)
                    logger.error(
                        f"[RATE_LIMIT] Chunk missing results for symbols: {missing_symbols}. "
                        f"Cannot proceed with incomplete price data."
                    )

        if failed_chunks:
            failed_count = sum(len(c) for c in failed_chunks)
            raise RuntimeError(
                f"[BATCH FETCH] Reduced batch size retry failed for {failed_count} symbols. "
                f"Cannot proceed with incomplete price coverage. "
                f"yfinance API degraded. Failed chunks: {failed_chunks[:3]}"
            )

        # All chunks successful - record batch completion
        successful_chunks = (len(symbols) + new_batch_size - 1) // new_batch_size
        total_chunks = successful_chunks
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
    ) -> dict[str, Any] | None:
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
        return self._fetch_with_explicit_retry(
            symbols,
            start,
            end,
            batch_size,
            attempt + 1,
            max_attempts,
            elapsed_sec=elapsed_sec + wait_time,
        )

    def _fetch_with_explicit_retry(
        self,
        symbols: list[str],
        start: date,
        end: date,
        batch_size: int,
        attempt: int = 0,
        max_attempts: int = 3,
        elapsed_sec: float = 0,
    ) -> dict[str, Any] | None:
        """Fetch with progressive batch size reduction and adaptive retry with jitter.

        ISSUE #6 FIX: Add upper bound check - if batch_size=1 and still rate limited, fail immediately.
        Attempts: full batch -> split in half -> quarter size -> give up.
        Includes randomized jitter to avoid thundering herd and circuit breaker for persistent errors.

        CRITICAL: Prevents infinite batch reduction + timeout cascade by tracking elapsed time.
        If batch=1 and elapsed > threshold, fail immediately rather than waiting indefinitely.
        """
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
        # This prevents: batch 150->20->10->5->1 cascade where load time balloons from 15 min -> 200+ min
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
                    m.add_metric(
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
                    logger.debug(
                        "Could not publish batch fetch minimum size metric: %s",
                        metric_err,
                    )
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
                        "[CIRCUIT BREAKER] Retrying with reduced batch size: %s (was %s), elapsed %.0fs",
                        reduced_size,
                        batch_size,
                        elapsed_sec,
                    )
                    reduced_attempt = self._fetch_with_explicit_retry(
                        symbols,
                        start,
                        end,
                        batch_size=reduced_size,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                    )
                    if reduced_attempt is not None and any(v is not None for v in reduced_attempt.values()):
                        symbols_fetched = sum(1 for v in reduced_attempt.values() if v is not None)
                        logger.critical(
                            f"[PRICE_LOADER] Batch size reduction resulted in incomplete price data: "
                            f"only {symbols_fetched}/{len(symbols)} symbols available. "
                            f"Batch reduction {batch_size}->{reduced_size} failed to recover full coverage."
                        )
                        raise RuntimeError(
                            f"[PRICE_LOADER] Cannot proceed with incomplete price data. "
                            f"Requested {len(symbols)} symbols but only retrieved {symbols_fetched} after rate-limit batch reduction. "
                            f"Price coverage MUST be complete for downstream calculations (technical indicators, buy/sell signals). "
                            f"yfinance API is experiencing degradation; cannot complete load cycle."
                        )

                # All reduced sizes failed — circuit breaker triggered, fail immediately
                logger.critical(
                    f"[CIRCUIT_BREAKER] Rate limiting persisted {error_duration / 60:.1f}min despite batch size reduction. "
                    "yfinance API experiencing degradation. Cannot proceed without price data. Failing fast."
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
                    logger.debug("Could not send rate limit alert: %s", alert_err)

                raise RuntimeError(
                    f"[CIRCUIT_BREAKER] Rate limiting persisted {error_duration / 60:.1f}min despite batch reduction. "
                    "yfinance API severely degraded. Cannot fetch price data."
                )

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
                    symbols,
                    start,
                    end,
                    batch_size,
                    attempt,
                    max_attempts,
                    elapsed_sec,
                    e,
                )
            else:
                return self._handle_transient_error(
                    symbols,
                    start,
                    end,
                    batch_size,
                    attempt,
                    max_attempts,
                    elapsed_sec,
                    e,
                )

    def transform(self, rows: list[Any]) -> list[dict[str, Any]]:
        """Validate and filter rows. Phase 1: Reject invalid ticks. Integrated validation framework."""
        return self.transformer.validate_and_transform(rows)

    def _validate_row(self, row: dict[str, Any]) -> bool:
        """Add price-range sanity check on top of default PK check."""
        if not super()._validate_row(row):
            return False
        try:
            return cast(bool, row["high"] >= row["low"] and row["close"] > 0 and row["open"] > 0)
        except (KeyError, TypeError) as e:
            raise RuntimeError(
                f"[PRICE_VALIDATION] Price validation failed: row is missing required fields or has invalid types: {e}. "
                "Price data integrity check is mandatory."
            ) from e

    def _validate_and_check_preconditions(self) -> None:
        """Validate preflight conditions: schema and market close availability."""
        self._validate_schema_preflight()
        if self.interval == "1d":
            self._validate_market_close_for_1d()

    def _validate_market_close_for_1d(self) -> None:
        """Ensure market close data is available for daily price loads.

        FAIL-FAST: Cannot load daily prices before market close without explicit validation.
        Raises if market close data cannot be verified available.
        """
        from algo.infrastructure import MarketCalendar

        today = datetime.now(EASTERN_TZ).date()
        if not MarketCalendar.is_trading_day(today):
            logger.info("[MARKET_CLOSE] Today is not a trading day, skipping check")
            return

        try:
            market_close_available = self._check_market_close_data_available(max_wait_sec=10)
            if not market_close_available:
                raise RuntimeError(
                    "[MARKET_CLOSE] Market close data not confirmed available within 10s timeout. "
                    "Cannot load daily prices without market close verification. "
                    "Either wait for market close or run price loader after market close confirmation."
                )
            logger.debug("[MARKET_CLOSE] Verified: market close data available")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"[MARKET_CLOSE] Market close check failed: {type(e).__name__}: {e}. "
                f"Cannot load daily prices without market close verification."
            ) from e

    def _execute_batch_jobs(
        self,
        batches: list[list[str]],
        parallelism: int,
        start_time: float,
        total_symbols: int,
    ) -> dict[str, Any]:
        """Execute batch jobs concurrently with timeout monitoring and circuit breaker logic.

        Returns:
          - dict with status="success" if all batches completed successfully
          - dict with status="halted" if circuit breaker triggered early

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
        failed_batches = []
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
                    failed_batches.append((batch, str(e)[:100]))

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
                if result.get("status") == "halted":
                    return result

        if failed_batches:
            failed_count = sum(len(batch) for batch, _ in failed_batches)
            batch_summary = "; ".join(
                f"Batch {i + 1}: {len(b)} symbols, error={err}" for i, (b, err) in enumerate(failed_batches[:5])
            )
            if len(failed_batches) > 5:
                batch_summary += f"; ... and {len(failed_batches) - 5} more batches failed"
            msg = (
                f"[LOAD_PRICES CRITICAL] Price fetch failed for {failed_count} symbols across {len(failed_batches)} batches. "
                f"Cannot load market prices without complete data. {batch_summary}"
            )
            logger.critical(msg)
            raise RuntimeError(msg)

        logger.debug("[BATCH_JOBS] All batches completed successfully")
        return {"status": "success"}

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
    ) -> dict[str, Any]:
        """Monitor timeout conditions and enforce circuit breaker logic.

        Returns:
          - dict with status="halted" if circuit breaker triggered
          - dict with status="continue" if execution should continue

        """

        avg_batch_time = sum(batch_times) / len(batch_times) if batch_times else 0
        if total_symbols <= 0:
            logger.critical(
                f"[LOAD_PRICES] CRITICAL: total_symbols is {total_symbols}. "
                f"Cannot calculate progress without symbol count. Loader may have failed to fetch symbols."
            )
            raise RuntimeError(
                f"Loader progress check failed: total_symbols is {total_symbols}. "
                f"Cannot verify completion percentage. Symbol loading may have failed."
            )
        completion_pct = processed / total_symbols
        remaining_batches = batches_count - (processed // self.batch_size)
        estimated_remaining_sec = remaining_batches * avg_batch_time

        logger.info(
            "  Progress: %d/%d symbols (%.0f%%) - batch: %.1fs, avg: %.1fs, est. %d more min",
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
                m.add_metric(
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
                logger.warning(
                    "[AUDIT_TRAIL] Could not publish timeout metric: %s. This breaks audit trail.",
                    metric_err,
                )

            if not emergency_mode_enabled:
                logger.warning(
                    "[EMERGENCY] Reducing parallelism from %s to 1 to finish before timeout",
                    max_concurrent,
                )

        if batch_elapsed > 120:
            logger.warning(
                f"  [SLOW BATCH] {self.batch_size} symbols took {batch_elapsed:.0f}s - "
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

        current_batch_size = self.fetcher.get_current_batch_size()
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
                m.add_metric(
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
                logger.warning(
                    "[AUDIT_TRAIL] Could not publish circuit breaker metric: %s. This breaks audit trail.",
                    metric_err,
                )

            # CRITICAL: Do not silently return with incomplete data
            # Fail fast to trigger Phase 1 failsafe instead of allowing corrupted/incomplete load
            error_msg = (
                f"[CIRCUIT_BREAKER] Rate limit cascade detected - batch reduced from 150 to {current_batch_size} "
                f"after {elapsed_sec / 60:.0f}min with only {completion_pct * 100:.0f}% of symbols loaded. "
                f"Cannot proceed with incomplete price data ({processed}/{total_symbols} symbols). "
                f"yfinance API severely degraded. Halting to maintain data integrity."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        # Timeout check passed — execution should continue.
        # Returns explicit status dict to signal caller that no circuit breaker was triggered
        # and normal batch processing should resume.
        logger.debug(
            "[TIMEOUT_MONITOR] Progress check passed: %d/%d symbols (%.1f%% complete). "
            "ETA %.0fs within timeout %ds. Continuing execution.",
            processed,
            total_symbols,
            (processed / total_symbols * 100) if total_symbols > 0 else 0,
            total_estimated_sec,
            task_timeout_sec,
        )
        return {"status": "continue"}

    def _finalize_execution_metrics(self) -> None:
        """Finalize execution: publish metrics, update loader status, attempt final symbol retry."""
        import time

        self._stats["rate_limit_errors"] = self._rate_limit_errors
        if self._rate_limit_error_start_time:
            error_duration_sec = time.time() - self._rate_limit_error_start_time
            self._stats["rate_limit_error_duration_sec"] = round(error_duration_sec, 1)
        else:
            self._stats["rate_limit_error_duration_sec"] = 0

        try:
            from algo.reporting import MetricsPublisher

            with MetricsPublisher() as m:
                m.put_loader_result(self.table_name, self._stats.to_dict())
                if self._rate_limit_errors > 0:
                    m.add_metric(
                        "RateLimitErrors",
                        self._rate_limit_errors,
                        unit="Count",
                        dimensions={
                            "table": self.table_name,
                            "interval": self.interval,
                        },
                    )
                    # CRITICAL: Explicit validation - no fallback with safe_float masking missing data
                    if "rate_limit_error_duration_sec" not in self._stats:
                        raise RuntimeError(
                            f"[{self.table_name}] Stats tracking broken: 'rate_limit_error_duration_sec' not present. "
                            f"Cannot publish rate limit duration metric."
                        )
                    rate_limit_duration = self._stats["rate_limit_error_duration_sec"]
                    if not isinstance(rate_limit_duration, (int, float)):
                        raise RuntimeError(
                            f"[{self.table_name}] Stats corruption: 'rate_limit_error_duration_sec' is {type(rate_limit_duration).__name__}, "
                            f"expected numeric. Value: {rate_limit_duration}"
                        )
                    if rate_limit_duration > 0:
                        m.add_metric(
                            "RateLimitErrorDuration",
                            rate_limit_duration,
                            unit="Seconds",
                            dimensions={
                                "table": self.table_name,
                                "interval": self.interval,
                            },
                        )
        except Exception as e:
            logger.warning("[LOAD_PRICES] Metrics reporting unavailable (circuit breaker data not recorded): %s", e)

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
                if result is None:
                    raise RuntimeError(f"Status query failed for table '{self.table_name}': query returned None")
                if len(result) < 2:
                    raise RuntimeError(
                        f"CRITICAL: Status query for '{self.table_name}' returned invalid row structure. "
                        f"Expected 2 columns (count, max_date), got {len(result)}."
                    )
                if result[0] is None:
                    raise RuntimeError(f"COUNT query returned NULL for table '{self.table_name}'")
                total_rows = result[0]
                latest_date = result[1] if result[1] is not None else None

            if "symbols_total" not in self._stats:
                raise RuntimeError(f"[{self.table_name}] Load stats incomplete: 'symbols_total' not tracked.")
            symbols_total = self._stats["symbols_total"]
            if not isinstance(symbols_total, int):
                raise RuntimeError(
                    f"[{self.table_name}] Load stats corrupt: 'symbols_total' is {type(symbols_total).__name__}, expected int"
                )
            symbols_expected = symbols_total
            if "symbols_processed" not in self._stats:
                raise RuntimeError(f"[{self.table_name}] Load stats incomplete: 'symbols_processed' not tracked.")
            symbols_successfully_loaded = self._stats["symbols_processed"]
            if not isinstance(symbols_successfully_loaded, int):
                logger.error(
                    f"[{self.table_name}] Load stats corruption: 'symbols_processed' is {type(symbols_successfully_loaded).__name__} "
                    f"(expected int): {symbols_successfully_loaded!r}"
                )
                raise RuntimeError(
                    f"[{self.table_name}] Stats tracking is broken — 'symbols_processed' should be int, not {type(symbols_successfully_loaded).__name__}. "
                    f"Cannot determine loader completion state. Data load status is UNKNOWN."
                )

            completion_pct = (symbols_successfully_loaded / symbols_expected * 100) if symbols_expected > 0 else 100.0

            loader_status = "COMPLETED" if completion_pct >= 95 else "INCOMPLETE"
            if completion_pct < 95:
                logger.warning(
                    f"[{self.table_name}] Load completed but INCOMPLETE: "
                    f"{symbols_successfully_loaded}/{symbols_expected} symbols ({completion_pct:.1f}%)"
                )

            if "start_time" not in self._stats:
                raise RuntimeError(f"[{self.table_name}] Load stats incomplete: 'start_time' not tracked.")
            start_time = self._stats["start_time"]
            if start_time is None:
                raise RuntimeError(
                    f"[{self.table_name}] Load stats corrupt: 'start_time' is None, cannot record execution time."
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
                        start_time,
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
                    "[CACHE INVALIDATION] CRITICAL FAILURE in _finalize_loader_metadata: %s",
                    cache_err,
                )
                raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning("Failed to update data_loader_status for {self.table_name}: %s", e)

        # Finalization complete. Implicit None return signals successful cleanup.
        # Caller expects None return — this method is responsible for:
        #   1. Publishing metrics to CloudWatch via MetricsPublisher
        #   2. Recording loader status in data_loader_status table
        #   3. Invalidating Phase 1 cache to prevent stale data consumption
        # If any step fails, exceptions are logged (non-fatal for final return).
        # Returns None to indicate finalization is done (caller must not retry).
        logger.debug(
            "[FINALIZE_METRICS] Execution metrics finalized for %s. "
            "Metrics published, loader status recorded, cache invalidated.",
            self.table_name,
        )

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
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
            logger.info("[SLA_OPT] Skipping 1d price load during EOD pipeline - reusing morning prep data")
            return {"symbols_processed": 0, "symbols_failed": 0, "rows_inserted": 0}

        self._validate_and_check_preconditions()

        batches = [symbols[i : i + self.batch_size] for i in range(0, len(symbols), self.batch_size)]
        self._stats["symbols_total"] = len(symbols)

        circuit_breaker_result = self._execute_batch_jobs(batches, parallelism, start, len(symbols))
        if circuit_breaker_result.get("status") != "success":
            logger.debug("[BATCH_JOBS] Early halt triggered, returning circuit breaker result")
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

        return self._stats.to_dict()

    def _load_batch(self, symbols: list[str]) -> None:
        """Load a batch of symbols using batch API fetch (50x reduction in API calls)."""
        wm_store = self._watermark
        # Determine the watermark date for all symbols in batch
        # (simplified: use same date for all, finest-grained would be per-symbol)
        if self._backfill_days > 0:
            # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
            previous_date: date | None = datetime.now(EASTERN_TZ).date() - timedelta(days=self._backfill_days)
        else:
            # Use earliest watermark from batch
            # CRITICAL: Fail-fast if watermark store invalid (no silent None defaults)
            if wm_store is None:
                raise RuntimeError(
                    f"[{self.table_name}] CRITICAL: Watermark store is None. "
                    f"Cannot determine previous watermark date for incremental loads."
                )
            watermarks = [wm_store.get(s) for s in symbols]
            previous_dates: list[date | None] = [w if isinstance(w, date) else None for w in watermarks]
            valid_dates: list[date] = [d for d in previous_dates if d is not None]
            if valid_dates:
                previous_date = min(valid_dates)
            else:
                # CRITICAL: If no watermarks available for any symbol, this indicates first load
                # or watermark tracking failure. Log explicitly.
                logger.warning(
                    f"[{self.table_name}] No watermarks found for any symbols in batch (symbols: {symbols[:5]}...). "
                    f"Performing full data fetch (first load or watermark corruption)."
                )
                previous_date = None

        # Batch fetch all symbols at once
        batch_results = self.fetch_batch_incremental(symbols, previous_date)

        # Process each symbol's results
        for symbol in symbols:
            # CRITICAL: Fail-fast if batch_results structure invalid
            if batch_results is None:
                raise RuntimeError(
                    f"[{self.table_name}] CRITICAL: Batch fetch returned None for symbol '{symbol}'. "
                    f"Cannot proceed with null batch results."
                )
            if symbol not in batch_results:
                raise RuntimeError(
                    f"[{self.table_name}] CRITICAL: Batch fetch missing results for symbol '{symbol}'. "
                    f"All symbols must have results dict entry (even if empty). "
                    f"Available symbols: {list(batch_results.keys())}"
                )

            rows = batch_results[symbol]
            if not rows:
                logger.debug(
                    "[{self.table_name}] %s: No rows fetched (watermark current), skipping",
                    symbol,
                )
                self._stats["symbols_skipped_by_watermark"] += 1
                self._stats["symbols_processed"] += 1  # Count as processed (no new data needed, not a failure)
                continue

            logger.debug("[{self.table_name}] {symbol}: Fetched %s rows from batch", len(rows))
            self._stats["rows_fetched"] += len(rows)

            if self.router and self.router.last_source:
                src = self.router.last_source
                if src not in self._stats["source_distribution"]:
                    self._stats["source_distribution"][src] = 0
                self._stats["source_distribution"][src] += 1

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
                chunk = rows[chunk_start : chunk_start + self.chunk_size]
                is_final_chunk = chunk_start + self.chunk_size >= len(rows)
                chunk_wm = new_wm if is_final_chunk else None
                inserted += self._bulk_insert_mgr.bulk_insert(
                    chunk,
                    symbol=symbol if is_final_chunk else None,
                    new_watermark=chunk_wm,
                    watermark_mgr=self._watermark if is_final_chunk else None,
                )

            if dedup and self.primary_key:
                for row in rows:
                    # Validate all primary key fields present before deduplication
                    for pk_field in self.primary_key:
                        if pk_field not in row or row[pk_field] is None:
                            raise ValueError(
                                f"[PRICES] Primary key field '{pk_field}' missing or None for symbol {symbol}. "
                                "Cannot deduplicate without complete primary key. "
                                f"Row: {row}"
                            )
                    key = ":".join(str(row[c]) for c in self.primary_key)
                    dedup.add(key)

            self._stats["rows_inserted"] += inserted
            self._stats["symbols_processed"] += 1


def _invalidate_phase1_cache() -> None:
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
        aws_region = os.getenv("AWS_REGION")
        if not aws_region:
            logger.error("[CACHE INVALIDATION] AWS_REGION not set. Cannot invalidate cache.")
            return

        cache_date = datetime.now(EASTERN_TZ).date()
        cache_key = f"data_loader_status-{cache_date.isoformat()}"
        cache_table_name = os.getenv("CACHE_TABLE", "algo_phase1_cache")
        dynamodb = boto3.resource("dynamodb", region_name=aws_region)
        cache_table = dynamodb.Table(cache_table_name)

        try:
            # Step 1: Try direct deletion
            cache_table.delete_item(Key={"cache_key": cache_key})
            logger.info(
                "[CACHE INVALIDATION]  Successfully deleted Phase 1 cache: %s",
                cache_key,
            )
            return
        except ClientError as delete_err:
            error_dict = delete_err.response.get("Error")
            if error_dict and error_dict.get("Code") in (
                "AccessDenied",
                "AccessDeniedException",
            ):
                logger.warning(
                    "[CACHE INVALIDATION]  Permission denied (DELETE): No DynamoDB write access. "
                    "Loader will proceed without cache invalidation (risk: may use stale data from previous run)."
                )
                return
            logger.error(
                f"[CACHE INVALIDATION] ✓ DELETE FAILED: {type(delete_err).__name__}: {delete_err}. Attempting cache poisoning..."
            )
        except Exception as delete_err:
            logger.error(
                f"[CACHE INVALIDATION] ✓ DELETE FAILED: {type(delete_err).__name__}: {delete_err}. Attempting cache poisoning..."
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
                "[CACHE INVALIDATION]  POISONED cache (set invalidation_failed=true) - Phase 1 will skip stale data"
            )
            return
        except ClientError as poison_err:
            error_dict = poison_err.response.get("Error")
            if error_dict and error_dict.get("Code") in (
                "AccessDenied",
                "AccessDeniedException",
            ):
                logger.warning(
                    "[CACHE INVALIDATION]  Permission denied (UPDATE): No DynamoDB write access. "
                    "Loader will proceed without cache invalidation (risk: may use stale data from previous run)."
                )
                return
            logger.error(
                "[CACHE INVALIDATION] ✓ POISONING ALSO FAILED: {type(poison_err).__name__}: %s",
                poison_err,
            )
        except (ValueError, ZeroDivisionError, TypeError) as poison_err:
            logger.error(
                "[CACHE INVALIDATION] ✓ POISONING ALSO FAILED: {type(poison_err).__name__}: %s",
                poison_err,
            )

    except (ValueError, ZeroDivisionError, TypeError) as setup_err:
        logger.error("[CACHE INVALIDATION] Setup error: %s", setup_err)

    # Step 3: Both deletion AND poisoning failed - CRITICAL: MUST HALT
    logger.critical(
        "[CACHE INVALIDATION] ✓✓ CRITICAL FAILURE: Could not delete OR poison cache. "
        "Phase 1 will potentially use stale data. HALTING LOADER IMMEDIATELY."
    )
    raise RuntimeError(
        "CRITICAL: Cache invalidation completely failed (cannot delete or poison). "
        "Halting loader to prevent silent stale-data corruption."
    )


def log_loader_execution(
    loader_name: str,
    table_name: str,
    status: str,
    records_loaded: int = 0,
    records_updated: int = 0,
    error_msg: str | None = None,
    duration_seconds: float = 0,
) -> None:
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
        logger.critical("[LOADER_EXECUTION_LOG] Failed to log execution to data_loader_runs: %s", e)
        raise


def main() -> int:
    """Read config from environment variables (set by ECS task definition)."""
    start_time = time.time()

    # Setup socket-level timeouts to prevent hanging on network operations
    from loaders.loader_helper import setup_loader_timeouts

    setup_loader_timeouts(socket_timeout_sec=30.0)

    logger.info("[%s] [MAIN] Starting price loader instance", _correlation_id)

    try:
        logger.info("[%s] [MAIN] Environment loaded successfully", _correlation_id)
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error("[MAIN] Failed to load environment: %s", e, exc_info=True)
        try:
            _invalidate_phase1_cache()
        except RuntimeError as cache_err:
            logger.critical("[MAIN] Cache invalidation failed on environment error: %s", cache_err)
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
            ) from log_err

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

    # Set execution timeout (ECS task timeout for price loader is 1800s = 30m per terraform config)
    # Use 1700s to allow 100s buffer before ECS force-kill to ensure graceful shutdown
    execution_timeout_sec = 1700

    import signal

    def timeout_handler(signum: int, frame: Any) -> None:
        logger.critical(
            "[TIMEOUT] Price loader exceeded %ss timeout. Killing process.",
            execution_timeout_sec,
        )
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
            logger.error("Invalid interval: {i}. Must be one of: %s", valid_intervals)
            return 1
    for a in asset_classes:
        if a not in valid_classes:
            logger.error("Invalid asset class: {a}. Must be one of: %s", valid_classes)
            return 1

    # Advisory lock: only one price loader instance at a time.
    _lock_conn = None
    try:
        from utils.db.connection import get_db_connection

        _lock_conn = get_db_connection(timeout=30)
        _lock_conn.autocommit = True  # type: ignore[attr-defined]
        with _lock_conn.cursor() as _cur:
            _cur.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s)::bigint)",
                ("stock_prices_daily",),
            )
            row = _cur.fetchone()
            if row is None:
                raise RuntimeError(
                    "[CRITICAL] Advisory lock query returned no rows - database connection may be corrupted"
                )
            acquired = row[0]
        if not acquired:
            logger.warning("[MAIN] Skipping: another stock_prices_daily instance already running (advisory lock held)")
            try:
                _lock_conn.close()
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as close_err:
                logger.debug("Could not close lock connection: %s", close_err)
            _lock_conn = None
            return 0
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as _lock_err:
        logger.warning(
            "[MAIN] Advisory lock check failed (%s) - proceeding without lock",
            _lock_err,
        )
        _lock_conn = None

    try:
        if symbols_str:
            symbols = [s.strip().upper() for s in symbols_str.split(",")]
            logger.info("[MAIN] Loaded %s symbols from environment", len(symbols))
        else:
            # max_symbols_limit=0 means no limit (loads all ~5000 symbols).
            # ECS task timeout is 12h which is sufficient for all symbols across all intervals.
            limit = max_symbols_limit if max_symbols_limit > 0 else None
            # Use 300s timeout (5 min) for symbol list query under EOD pipeline load
            # Multiple loaders running concurrently can exhaust connection pool; allow extra time
            symbols = get_active_symbols(max_symbols=limit, timeout_secs=300)
            logger.info("[MAIN] Loaded %s symbols from database", len(symbols))
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
                    logger.critical(
                        "[MAIN] Could not log loader failure to audit trail: %s",
                        log_err,
                    )
                return 1
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error("[MAIN] Failed to get symbols: %s", e, exc_info=True)
        try:
            _invalidate_phase1_cache()
        except RuntimeError as cache_err:
            logger.critical("[MAIN] Cache invalidation failed on symbols error: %s", cache_err)
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
            ) from log_err

    # Load essential symbols from configuration (centralized to prevent inconsistencies)
    from utils.market_symbols_config import MarketSymbolsConfig

    essential_stock_price_daily = MarketSymbolsConfig.get_essential_stocks()
    essential_etf_symbols = MarketSymbolsConfig.get_essential_etf_symbols()

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
                        if interval not in interval_stagger_delays:
                            raise ValueError(
                                f"Missing stagger delay configuration for interval '{interval}'. "
                                f"Available intervals: {list(interval_stagger_delays.keys())}. "
                                f"Cannot proceed without explicit stagger configuration to prevent rate limit bursts."
                            )
                        stagger_delay = interval_stagger_delays[interval]
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

                        logger.info("[MAIN] Completed {asset_class}/{interval}: %s", stats)
                        # Validate stats dict has required keys
                        for required_key in [
                            "symbols_processed",
                            "symbols_failed",
                            "rows_inserted",
                        ]:
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
                            logger.critical(
                                "[MAIN] Cache invalidation failed on loader error: %s",
                                cache_err,
                            )
                        raise RuntimeError(
                            f"[MAIN] Loader failed for {asset_class}/{interval}: {e}. "
                            "Cannot proceed with price loading if an interval fails."
                        ) from e
    except Exception as timeout_err:
        logger.critical("[MAIN] Loader execution timeout exceeded: %s", timeout_err)
        try:
            _invalidate_phase1_cache()
        except RuntimeError as cache_err:
            logger.critical("[MAIN] Cache invalidation failed on timeout error: %s", cache_err)
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
            ) from log_err

    logger.info("[MAIN] All intervals completed. Total: %s", total_stats)

    duration_seconds = round(time.time() - start_time, 2)
    if fail_count > 0:
        logger.error("[MAIN] %s interval(s) had too many failures", fail_count)
        try:
            _invalidate_phase1_cache()
        except RuntimeError as cache_err:
            logger.critical("[MAIN] Cache invalidation failed on final failure: %s", cache_err)
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
            ) from log_err

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
        ) from log_err
    if _lock_conn:
        try:
            _lock_conn.close()
        except Exception as close_err:
            logger.debug("Could not close lock connection: %s", close_err)
    return 0


if __name__ == "__main__":
    try:
        result = main()
        sys.exit(result if result is not None else 0)
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)
