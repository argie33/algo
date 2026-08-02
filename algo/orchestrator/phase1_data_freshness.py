#!/usr/bin/env python3
"""
PHASE 1: DATA FRESHNESS CHECK

Verify pipeline-loaded tables are fresh before trading. "Fresh" = LAST TRADING DAY data:
- If today is a trading day (Mon-Fri): require today's data
- If today is weekend/holiday: require most recent trading day's data
- NO multi-day lookback windows (Session 223 fix: stale data bypass)

Tables verified (all must have LAST-TRADING-DAY data with non-NULL prices):

HALT IF STALE (core to signal generation):
1. price_daily: Stock prices (75%+ symbol coverage required)
2. market_health_daily: Market breadth metrics (regime detection)
3. earnings_calendar: Earnings dates (blackout window gating)

WARNING IF STALE (enrichment only, website/portfolio analysis, not core signals):
4. market_exposure_daily: Market regime / exposure limits (EOD loader, morning runs lag 1d)
5. growth_metrics: Multi-year revenue/EPS growth metrics
6. quality_metrics: Financial quality metrics (ROE/margins/ratios)
7. value_metrics: Valuation metrics (P/E, P/B, etc.)
8. positioning_metrics: Ownership and short interest
9. stability_metrics: Volatility and beta metrics
10. trend_template_data: Minervini/Weinstein criteria
11. sector_ranking: Sector data for last trading day
(swing_trader_scores: removed in Session 14, no longer checked)

NOTE: Metric loaders (growth, quality, value, positioning, stability) are ENRICHMENT ONLY.
They're used for website display and portfolio analysis, not core signal generation (which uses
price_daily + technical_data_daily). Phase 5 generates stock_scores on-the-fly from price_daily;
metrics are not required for trading. Stale metrics = WARNING only, trading continues.

Phase 5 generates stock_scores and signals on-the-fly from price_daily input.
Excluded: stock_scores (orchestrator output), technical_data_daily, buy_sell_daily (pipeline-loaded, Phase 1 just validates).

TIMEZONE REQUIREMENT: All dates passed to phases are ET (Eastern Time) dates, not UTC.
Market trading hours are 9:30 AM - 4:00 PM ET. The orchestrator ensures run_date is always ET.
Phases should NOT convert run_date to UTC or use UTC timestamps for trading logic.
"""

import logging
import time
from collections.abc import Callable
from datetime import date as _date
from typing import Any

import psycopg2

from algo.orchestrator.config_validator import validate_phase_config
from algo.orchestrator.phase1_failsafe_retry import check_and_retry_incomplete_loaders
from algo.orchestrator.phase_data_contract import validate_phase_data
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)


def _check_health_column_coverage(
    total_rows: int | None,
    pcr_rows: int | None,
    vix_rows: int | None,
    health_max_date: _date,
) -> None:
    """Validate market_health_daily's optional-column coverage for health_max_date.

    total_rows == 0 halts (the whole row is missing, not just an optional column).
    put_call_ratio/vix_level being fully null only warns - see the inline note below,
    this used to be a hard RuntimeError (commit c6862e04a fixed a live incident where
    a missing put_call_ratio - an optional 8pt sentiment enrichment Phase 2 already
    skips gracefully - halted Phase 1/2/4/5/7 entirely). Extracted from run() so this
    decision has direct unit test coverage instead of relying on live reproduction.
    """
    if not total_rows:
        raise RuntimeError(f"[PHASE 1] market_health_daily has no rows for {health_max_date}")

    if not pcr_rows:
        # NOTE: put_call_ratio is OPTIONAL in Phase 2 (algo/risk/market_exposure.py,
        # commit 6a94934d4, "Make put_call_ratio truly optional") - it's an unofficial
        # yfinance-options-chain-derived sentiment enrichment (8pt of 100), explicitly
        # excluded from market_exposure's required_factors and gracefully skipped when
        # missing. This used to be a hard RuntimeError halting the entire orchestrator
        # (Phase 1/2/4/5/7 all skip), which contradicted that same-day optionality
        # decision and would halt real trading whenever this one non-critical field
        # was null - which happens routinely (e.g. before the daily options-chain
        # fetch completes). Downgraded to a warning, matching vix_rows below.
        logger.warning(
            f"[PHASE 1] WARNING: market_health_daily missing put_call_ratio data for {health_max_date}. "
            "Optional sentiment enrichment (Phase 2 skips it gracefully) - not halting. "
            "Check market_health_daily loader if this persists."
        )

    if not vix_rows:
        logger.warning(
            f"[PHASE 1] WARNING: market_health_daily missing VIX data for {health_max_date}. "
            "VIX is optional if provided by other means, but check market_health_daily loader."
        )


def _check_failsafe_retry_result(
    failsafe_result: dict[str, Any],
    log_phase_result_fn: Callable[..., Any],
) -> PhaseResult | None:
    """Check failsafe retry result and return early if halt required.

    Args:
        failsafe_result: Result dict from check_and_retry_incomplete_loaders
        log_phase_result_fn: Logging callback

    Returns:
        PhaseResult if halt required, None if can proceed
    """
    # Validate failsafe result structure (fail-fast if corrupted)
    required_keys = {"incomplete_loaders", "retried", "recovered", "still_failing", "halt_required"}
    missing_keys = required_keys - set(failsafe_result.keys())
    if missing_keys:
        logger.critical(
            f"[PHASE 1] FATAL: failsafe_result missing required keys: {missing_keys}. "
            f"Received keys: {set(failsafe_result.keys())}. This indicates corruption in failsafe retry logic."
        )
        raise RuntimeError(
            f"[PHASE 1] Failsafe retry result corrupted - missing keys: {missing_keys}. "
            "Cannot proceed with freshness validation."
        )

    # Log failsafe results for visibility (explicit key access, no defaults)
    logger.info(
        f"[PHASE 1] Failsafe retry check: "
        f"incomplete={len(failsafe_result['incomplete_loaders'])} "
        f"retried={len(failsafe_result['retried'])} "
        f"recovered={len(failsafe_result['recovered'])} "
        f"still_failing={len(failsafe_result['still_failing'])} "
        f"halt_required={failsafe_result['halt_required']}"
    )

    still_failing = failsafe_result["still_failing"]
    price_tables = {
        "price_daily",
        "price_weekly",
        "price_monthly",
        "etf_price_daily",
        "etf_price_weekly",
        "etf_price_monthly",
    }
    if any(table in price_tables for table in still_failing):
        price_coverage_pct = None
        try:
            with DatabaseContext("read") as cur:
                cur.execute("""SELECT completion_pct FROM data_loader_status
                       WHERE table_name='price_daily' ORDER BY last_updated DESC LIMIT 1""")
                row = cur.fetchone()
                if row and row[0] is not None:
                    price_coverage_pct = row[0]
        except Exception as e:
            logger.warning(f"[PHASE 1] Could not check price coverage: {e}")

        coverage_str = f"{price_coverage_pct:.1f}%" if price_coverage_pct else "unknown"
        logger.critical(
            f"[PHASE 1] CRITICAL: price_daily still incomplete after retry ({coverage_str} coverage). "
            f"Cannot proceed without complete price data."
        )
        log_phase_result_fn(
            1,
            "incomplete_price_data_after_retry",
            "halt",
            f"price_daily {coverage_str} coverage after retry",
        )
        return PhaseResult(
            1,
            "incomplete_price_data_after_retry",
            "halted",
            failsafe_result,
            True,
            f"Price data incomplete after retry ({coverage_str}). Run recovery script: python scripts/recover_incomplete_loader.py",
        )

    if failsafe_result.get("halt_required"):
        logger.critical(
            "[PHASE 1] CRITICAL: Other critical loaders incomplete even after failsafe retry. "
            "Cannot proceed with data processing."
        )
        still_failing = failsafe_result.get("still_failing")
        if still_failing is None:
            raise RuntimeError(
                "[PHASE 1] FATAL: failsafe_result missing 'still_failing' field. "
                "Cannot determine which loaders failed. This indicates corruption in failsafe retry logic. "
                "Verify failsafe_retry.py returns complete result dict with all required fields."
            )
        log_phase_result_fn(
            1,
            "incomplete_loaders_after_retry",
            "halt",
            f"Still incomplete after retry: {still_failing}",
        )
        still_failing_first = still_failing[0] if still_failing else "unknown"
        return PhaseResult(
            1,
            "incomplete_loaders_after_retry",
            "halted",
            failsafe_result,
            True,
            f"Critical loaders incomplete after retry: {still_failing_first}",
        )

    return None


def _validate_config(config: Any) -> tuple[int, int, int, int, int]:
    """Extract and validate required configuration parameters.

    Args:
        config: Configuration dict from algo_config table

    Returns:
        Tuple of (min_coverage_pct, min_symbol_count, recent_cutoff, prior_cutoff, halt_tolerance)

    Raises:
        RuntimeError: If config is missing required keys
    """
    if not config:
        raise RuntimeError(
            "[PHASE 1] Config not provided: cannot proceed without phase1_min_coverage_pct "
            "and phase1_min_symbol_count thresholds. Config must be passed from algo_config table."
        )

    try:
        min_coverage_pct = config["phase1_min_coverage_pct"]
    except KeyError as e:
        raise RuntimeError(
            "[PHASE 1] Config missing required key 'phase1_min_coverage_pct'. "
            "Cannot proceed without explicit data freshness threshold (no hardcoded fallback)."
        ) from e

    try:
        min_symbol_count = config["phase1_min_symbol_count"]
    except KeyError as e:
        raise RuntimeError(
            "[PHASE 1] Config missing required key 'phase1_min_symbol_count'. "
            "Cannot proceed without explicit symbol count threshold (no hardcoded fallback)."
        ) from e

    # CRITICAL FIX: Require explicit config for all timing parameters - no silent fallbacks
    # These timing thresholds directly affect whether we halt trading for stale data
    required_keys = ["phase1_recent_cutoff_days", "phase1_prior_cutoff_days", "phase1_halt_table_max_tolerance_days"]
    missing = [k for k in required_keys if k not in config]
    if missing:
        raise RuntimeError(
            f"[PHASE 1] Config missing required timing thresholds: {missing}. "
            "Data staleness tolerance thresholds must be explicit in algo_config table. "
            "Cannot use hardcoded fallbacks for trading safety decisions."
        )

    try:
        phase1_recent_cutoff_days = config["phase1_recent_cutoff_days"]
        phase1_prior_cutoff_days = config["phase1_prior_cutoff_days"]
        phase1_halt_table_max_tolerance_days = config["phase1_halt_table_max_tolerance_days"]
    except (KeyError, TypeError) as e:
        raise RuntimeError(f"[PHASE 1] Config error reading staleness thresholds: {e}") from e

    return (
        min_coverage_pct,
        min_symbol_count,
        phase1_recent_cutoff_days,
        phase1_prior_cutoff_days,
        phase1_halt_table_max_tolerance_days,
    )


def run(  # noqa: C901
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable[..., Any],
) -> PhaseResult:
    """Execute Phase 1: Verify pipeline-loaded tables are fresh.

    ISSUE #6 FIX: Integrate DataPatrol checks to block Phase 1 if data quality issues found.

    DataPatrol runs independently and validates:
    - Staleness of critical tables (price_daily, market_health_daily, etc.)
    - Data coverage and completeness
    - Quality metrics (OHLC sanity, volume outliers, etc.)
    - Alignment between related tables

    Phase 1 now:
    1. Queries DataPatrol results from patrol_log table
    2. Fails if CRITICAL or ERROR issues found
    3. Warns if WARNING issues found but proceeds
    4. Performs traditional freshness checks (redundant but explicit fail-safe)

    Halts if price_daily, market_health_daily, or market_exposure_daily are stale -
    these are required for Phase 5 signal generation and regime gating.
    Issues warnings for trend_template_data and sector_ranking -
    stale but trading can continue.
    Excludes stock_scores (orchestrator-generated output, not pipeline input).
    """
    validate_phase_config(config, "phase_1_data_freshness")

    from datetime import timedelta as td

    phase_start = time.time()
    degraded_reason = None
    (
        min_coverage_pct,
        min_symbol_count,
        phase1_recent_cutoff_days,
        _phase1_prior_cutoff_days,
        phase1_halt_table_max_tolerance_days,
    ) = _validate_config(config)

    from datetime import datetime as dt

    now_et = dt.now(EASTERN_TZ)
    pipeline_context = "EOD" if now_et.hour >= 16 else "MORNING" if now_et.hour < 10 else "INTRADAY"

    logger.info(
        f"[PHASE 1] Starting comprehensive freshness check (Pipeline: {pipeline_context}, Time: {now_et.strftime('%H:%M:%S ET')})"
    )

    # PHASE 1 FAILSAFE: Check for and retry incomplete loaders before freshness check
    failsafe_result = check_and_retry_incomplete_loaders(dry_run=dry_run)
    failsafe_halt = _check_failsafe_retry_result(failsafe_result, log_phase_result_fn)
    if failsafe_halt:
        return failsafe_halt

    # CRITICAL FIX: Pre-validate stock_symbols table is populated
    # If symbols loader failed, all downstream phases will fail
    # Better to catch this early with clear error message
    try:
        with DatabaseContext("read") as pre_check_cur:
            pre_check_cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
            # CRITICAL FIX: Check if query returned results before indexing
            result = pre_check_cur.fetchone()
            if result is None:
                error_msg = (
                    "[PHASE 1 CRITICAL] stock_symbols COUNT query failed (no results). "
                    "Database connectivity or schema issue. Check database logs."
                )
                logger.critical(error_msg)
                log_phase_result_fn(1, "data_freshness", "error", error_msg)
                return PhaseResult(
                    phase_num=1,
                    phase_name="data_freshness",
                    status="error",
                    halted=True,
                    error=error_msg,
                )
            symbol_count = result[0]
            if not symbol_count or symbol_count == 0:
                error_msg = (
                    "[PHASE 1 CRITICAL] stock_symbols table has no active symbols. "
                    "The symbol loader failed or never ran. "
                    "Without trading symbols, all downstream phases will fail. "
                    "Check: (1) symbol loader status in data_loader_status, "
                    "(2) Lambda logs for loader errors, (3) Re-run: python3 scripts/run_local_orchestrator.py --morning"
                )
                logger.critical(error_msg)
                log_phase_result_fn(1, "data_freshness", "halt", error_msg)
                return PhaseResult(1, "data_freshness", "halted", {"status": "halted", "reason": "no active symbols"}, True, error_msg)
            logger.info(f"[PHASE 1] Pre-flight: stock_symbols table OK ({symbol_count:,} active symbols)")
    except Exception as pre_check_err:
        error_msg = (
            f"[PHASE 1 CRITICAL] Pre-flight validation failed - cannot verify stock_symbols table: {pre_check_err}. "
            f"This prevents all downstream phases from running correctly. "
            f"Fail-fast: halting Phase 1 to surface data quality issue."
        )
        logger.critical(error_msg)
        log_phase_result_fn(1, "data_freshness", "halt", error_msg)
        return PhaseResult(1, "data_freshness", "halted", {"status": "halted", "reason": "pre-flight validation failed"}, True, error_msg)

    try:
        with DatabaseContext("read") as cur:
            cur.execute("SET statement_timeout = 15000")  # 15s timeout for multi-table checks

            # Find reference date from price_daily (most reliable source)
            # NOTE: stock_scores is NOT validated here; it's an orchestrator OUTPUT (Phase 5),
            # not a pipeline loader INPUT. Validating orchestrator outputs in Phase 1 breaks first-run.
            # Phase 7 (Signal Generation) will handle missing stock_scores when it runs.
            # CRITICAL FIX 2026-08-02: Exclude index tickers (^VIX, etc) from MAX(date)
            # Index tickers update pre-market before equity prices, skewing freshness check
            cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol NOT LIKE '^%%'")
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(
                    "[PHASE 1] price_daily MAX(date) query returned NULL. "
                    "Query malformed or database connection failed."
                )
            max_date = row[0]
            if max_date is None:
                logger.critical("[PHASE 1] price_daily table is empty")
                log_phase_result_fn(1, "price_data", "halt", "price_daily table is empty")
                return PhaseResult(
                    1,
                    "price_data",
                    "halted",
                    {"status": "halted", "reason": "price_daily table is empty - no pricing data available"},
                    True,
                    "price_daily table is empty",
                )

            # CRITICAL FIX: Ensure max_date is a date object, not datetime
            # PostgreSQL date columns can return datetime.datetime from some drivers
            if isinstance(max_date, dt):
                max_date = max_date.date()

            # CRITICAL: Verify stock_symbols table is pre-loaded (required for ALL loaders)
            # Session 299 FIX: More robust symbol check with better error diagnostics
            # Only retry on transient errors (lock timeouts, connection issues), not structural issues
            symbol_count = None
            last_error = None
            max_retries = 2
            transient_error_keywords = ("timeout", "connection", "pool", "concurrent", "deadlock")

            for attempt in range(max_retries):
                try:
                    cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
                    symbol_count_row = cur.fetchone()
                    if symbol_count_row is not None and symbol_count_row[0] is not None:
                        symbol_count = symbol_count_row[0]
                        break
                    else:
                        # COUNT(*) should never return NULL; if it does, something is wrong
                        error_msg = f"stock_symbols query returned unexpected result: {symbol_count_row}"
                        logger.error(f"[PHASE 1] {error_msg}")
                        if attempt < max_retries - 1:
                            time.sleep(0.3)
                            continue
                        last_error = error_msg
                        break
                except Exception as query_err:
                    error_str = str(query_err).lower()
                    is_transient = any(kw in error_str for kw in transient_error_keywords)

                    if is_transient and attempt < max_retries - 1:
                        logger.warning(
                            f"[PHASE 1] Transient stock_symbols check error (attempt {attempt + 1}): {query_err}"
                        )
                        time.sleep(0.3)
                        continue
                    else:
                        # Permanent error or last attempt
                        logger.error(f"[PHASE 1] stock_symbols check failed (attempt {attempt + 1}): {query_err}")
                        last_error = f"{type(query_err).__name__}: {str(query_err)[:100]}"
                        break

            if symbol_count is None or symbol_count == 0:
                error_detail = last_error or "(query returned 0 or NULL)"
                logger.critical(
                    "[PHASE 1] CRITICAL: stock_symbols table has no active symbols. "
                    f"Details: {error_detail}. "
                    "All loaders depend on symbol list being pre-loaded. "
                    "Run load_market_constituents.py first to populate NASDAQ/NYSE symbols."
                )
                log_phase_result_fn(
                    1, "symbol_list_missing", "halt", f"stock_symbols table empty or inaccessible: {error_detail}"
                )
                return PhaseResult(
                    1,
                    "symbol_list_missing",
                    "halted",
                    {},
                    True,
                    f"stock_symbols table is empty - symbols must be loaded before trading. Error: {error_detail}",
                )
            logger.info(f"[PHASE 1] Symbol list verified: {symbol_count} active symbols")

            # CRITICAL FIX: Detect phantom rows in price_daily (NULL prices counted as fresh data)
            # These bypass the freshness check by inflating MAX(date) and symbol count
            # CRITICAL FIX 2026-08-02: Exclude index tickers from MAX(date) in nested SELECT
            cur.execute("""SELECT COUNT(*) as phantom_count,
                          COUNT(CASE WHEN close IS NULL THEN 1 END) as null_close_count,
                          COUNT(CASE WHEN open IS NULL THEN 1 END) as null_open_count
                   FROM price_daily
                   WHERE date = (SELECT MAX(date) FROM price_daily WHERE symbol NOT LIKE '^%%')
                   AND symbol NOT LIKE '^%%'""")
            phantom_row = cur.fetchone()
            if phantom_row:
                phantom_count = phantom_row[0]
                null_close = phantom_row[1]
                null_open = phantom_row[2]
                if null_close > 0 or null_open > 0:
                    logger.warning(
                        f"[PHASE 1] PHANTOM ROWS DETECTED on MAX date: "
                        f"{phantom_count} total rows, {null_close} NULL close, {null_open} NULL open. "
                        f"These rows will be ignored - only rows with actual prices (open/close NOT NULL) count as fresh."
                    )

            from algo.infrastructure import MarketCalendar

            # Market hours: 9:30 AM - 4:00 PM ET.
            # If orchestrator runs DURING market hours (before 16:00 ET), expect previous trading day's data.
            # If orchestrator runs AFTER market close (16:00+ ET), expect same-day data.

            # CRITICAL: Ensure run_date is a date object, not datetime (can come from various sources)
            if isinstance(run_date, dt):
                run_date_obj = run_date.date()
            else:
                run_date_obj = run_date

            if pipeline_context == "MORNING" or pipeline_context == "INTRADAY":
                # During market hours (before close): expect the *previous* trading day's data
                # (today's not closed yet, so markets haven't published today's data)
                # This is the RIGHT thing: require most recent market close's data
                prev_date = run_date_obj - td(days=1)
                if MarketCalendar.is_trading_day(prev_date):
                    last_trading_day = prev_date
                else:
                    # Find the most recent trading day before today
                    # (e.g., if today is Monday, find Friday; if Monday is holiday, find Thursday)
                    last_trading_day = prev_date
                    while last_trading_day > run_date_obj - td(days=10):
                        if MarketCalendar.is_trading_day(last_trading_day):
                            break
                        last_trading_day -= td(days=1)
            else:
                # After market close (EOD context): expect same-day data if it's a trading day
                # If today is not a trading day (weekend/holiday): expect yesterday's data if it's trading day
                # This is the RIGHT thing: require most recent market close's data
                if MarketCalendar.is_trading_day(run_date_obj):
                    last_trading_day = run_date_obj
                else:
                    # Weekend/holiday: find most recent trading day
                    # (e.g., if today is Saturday, find Friday; if Friday was market close, use that)
                    last_trading_day = run_date_obj - td(days=1)
                    while last_trading_day > run_date_obj - td(days=10):
                        if MarketCalendar.is_trading_day(last_trading_day):
                            break
                        last_trading_day -= td(days=1)

            # TOLERANCE for data provider delays: if we're in IMMEDIATE EOD context (4:00-4:30 PM),
            # allow previous trading day's data as acceptable (data providers may not have
            # same-day data ready immediately after market close).
            # CRITICAL FIX: This tolerance should NOT apply hours later (after 4:30 PM).
            # By 5:00 PM+, all data providers should have same-day prices ready.
            acceptable_min_date = last_trading_day
            # CRITICAL FIX: `now_et.hour` is always an integer, so comparing it against the
            # float 16.5 can never distinguish "before 4:30 PM" from "after" within the same
            # clock hour - `16 <= 16 < 16.5` and `16 >= 16.5` are True/False respectively for
            # EVERY minute from 16:00:00 through 16:59:59, not just the first 30. Confirmed live
            # 2026-07-27: for any EOD-context run landing in that hour (e.g. a late/retried run,
            # not the fixed morning/afternoon/preclose/evening schedule), the grace period would
            # silently stay active the entire hour instead of expiring at 16:30 as the comments
            # below and the log line at 16:36 both claim - stale same-day data would be masked by
            # falling back to the prior trading day for up to 30 extra minutes. Compare against
            # an actual time boundary instead of an hour/float mismatch.
            grace_period_end = now_et.replace(hour=16, minute=30, second=0, microsecond=0)
            market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
            if pipeline_context == "EOD" and market_close <= now_et < grace_period_end:
                # Allow previous trading day as fallback if same-day not yet available
                # (ONLY in immediate aftermath of market close, within 30 min)
                prev_trading_day = last_trading_day - td(days=1)
                while prev_trading_day > last_trading_day - td(days=10):
                    if MarketCalendar.is_trading_day(prev_trading_day):
                        acceptable_min_date = prev_trading_day
                        logger.info(
                            f"[PHASE 1] Grace period active (4:00-4:30 PM): accepting {prev_trading_day} as valid"
                        )
                        break
                    prev_trading_day -= td(days=1)
            elif pipeline_context == "EOD" and now_et >= grace_period_end:
                # After 4:30 PM: must have same-day data
                logger.info(f"[PHASE 1] Grace period expired (> 4:30 PM): requiring {last_trading_day} data")

            if max_date < acceptable_min_date:
                from algo.orchestrator.phase_error_handling import (
                    ErrorCategory,
                    PhaseError,
                    log_phase_error,
                )

                days_stale = (acceptable_min_date - max_date).days
                logger.critical(f"[PHASE 1] Price data stale: {max_date} vs expected {acceptable_min_date} (or later)")

                # CRITICAL FIX: Remove "emergency loader" workaround that doesn't work in production
                # Session 124 discovered this never worked:
                # - Hardcoded localhost connection cannot reach RDS from Lambda
                # - Portfolio symbols fallback is too narrow (missing most universe)
                # - dry_run flag bypasses the halt anyway
                # The REAL fix is proper loader scheduling + Phase 1 failsafe retry (above).
                # Halt here forces operators to investigate root cause and fix the pipeline.

                error = PhaseError(
                    category=ErrorCategory.DATA_STALE,
                    message=f"Price data is {days_stale} day(s) stale (latest: {max_date}, expected: {last_trading_day})",
                    root_cause="Scheduled morning pipeline failed to load prices. Check price_daily loader logs, yfinance access, network connectivity, and EventBridge Scheduler status.",
                    recoverable=False,
                    log_level="critical",
                )
                log_phase_error(1, error, log_phase_result_fn)

                return PhaseResult(
                    1,
                    "price_staleness",
                    "halted",
                    {},
                    True,
                    f"Price data too old: {max_date} vs {acceptable_min_date}. Check price_daily loader and EventBridge Scheduler.",
                )

            # CRITICAL FIX: Require LAST-TRADING-DAY data with actual non-NULL prices
            # "Last trading day" = TODAY if today is a trading day (Mon-Fri), otherwise most recent trading day
            # Reject multi-day window (allows trading on stale data)
            # Reject phantom rows (NULL prices counted as fresh data)
            # This is the RIGHT thing: require data for the most recent market close, always

            # CRITICAL FIX 2026-07-29: For afternoon runs, we also need to check TODAY's data
            # because the orchestrator needs today's prices for Phase 6 exit execution.
            # The loader should have completed by mid-day, so lack of today's data indicates
            # loader failure, not normal lag. Check both yesterday (for intraday validation)
            # and today (for afternoon orchestrator requirements).

            # Both counts are scoped to symbols currently marked active in stock_symbols.
            # price_daily retains history for ~10.6K symbols total, but only ~5.5K are
            # still active - the other ~5.1K are delisted/removed tickers whose rows stop
            # getting new dates entirely. An unscoped COUNT(DISTINCT symbol) against the
            # full table (as this used to be) compares today's genuinely-active fetch
            # against that inflated historical figure, permanently capping coverage_pct
            # around 45-50% no matter how complete today's load is - confirmed live
            # 2026-07-20 (real coverage 85.5% scoped to active symbols, computed as 42.8%
            # unscoped, incorrectly halting Phase 1 on every EOD-context run since the
            # active universe last shrank).
            cur.execute(
                """SELECT COUNT(DISTINCT pd.symbol)
                   FROM price_daily pd
                   JOIN stock_symbols ss ON ss.symbol = pd.symbol AND ss.active = true
                   WHERE pd.date = %s AND pd.close IS NOT NULL AND pd.open IS NOT NULL""",
                (last_trading_day,),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise RuntimeError(f"Symbol count query failed for last trading day ({last_trading_day})")
            symbols_loaded = row[0]

            # CRITICAL: For afternoon/evening runs, also validate TODAY's price data
            # If we're past early morning and don't have today's data, loader failed
            if pipeline_context in ("AFTERNOON", "EVENING"):
                cur.execute(
                    """SELECT COUNT(DISTINCT pd.symbol)
                       FROM price_daily pd
                       JOIN stock_symbols ss ON ss.symbol = pd.symbol AND ss.active = true
                       WHERE pd.date = %s AND pd.close IS NOT NULL AND pd.open IS NOT NULL""",
                    (run_date_obj,),
                )
                today_row = cur.fetchone()
                today_symbols = today_row[0] if today_row and today_row[0] is not None else 0

                if today_symbols < min_symbol_count:
                    logger.critical(
                        f"[PHASE 1] CRITICAL: Today's ({run_date_obj}) price data incomplete: {today_symbols} symbols loaded. "
                        f"Loader appears to have failed. Require at least {min_symbol_count} symbols for exit execution."
                    )
                    log_phase_result_fn(
                        1,
                        "today_price_data_missing",
                        "halt",
                        f"Today's price data incomplete: only {today_symbols}/{min_symbol_count} symbols",
                    )
                    return PhaseResult(
                        1,
                        "today_price_data_missing",
                        "halted",
                        {},
                        True,
                        f"Loader failed: only {today_symbols} symbols for {run_date_obj}. Check price_daily loader logs.",
                    )

            # CRITICAL FIX: Validate that data_loader_status.completion_pct matches actual symbol count
            # Session 344: Found that completion_pct was calculated on row_count, not symbol_count,
            # causing false "100% complete" when only 1 symbol out of 5000+ was actually loaded.
            # This check catches that mismatch and fails fast rather than proceeding with incomplete data.
            # CRITICAL FIX 2026-08-02: Fail-fast on data integrity mismatch (was just logging)
            try:
                cur.execute("""SELECT completion_pct, symbols_loaded, symbol_count
                       FROM data_loader_status
                       WHERE table_name = 'price_daily'
                       ORDER BY last_updated DESC LIMIT 1""")
                loader_status_row = cur.fetchone()
                if loader_status_row:
                    reported_pct, reported_loaded, reported_expected = loader_status_row
                    # If loader reports 90%+ but actual loaded count is significantly lower, that's data integrity failure
                    if reported_pct and reported_pct >= 90 and reported_loaded and reported_expected:
                        actual_coverage = (reported_loaded / max(reported_expected, 1)) * 100
                        if actual_coverage < 50:
                            error_msg = (
                                f"[PHASE 1 CRITICAL] Data integrity failure: data_loader_status reports "
                                f"{reported_pct:.0f}% completion but actual coverage is {actual_coverage:.1f}% "
                                f"({reported_loaded} symbols loaded, {reported_expected} expected). "
                                f"This indicates the loader's completion_pct calculation is broken. "
                                f"Cannot proceed with analysis on corrupted completion metrics. "
                                f"Check data_loader_status.completion_pct calculation logic."
                            )
                            logger.critical(error_msg)
                            log_phase_result_fn(1, "data_loader_status", "halt", error_msg)
                            return PhaseResult(
                                1,
                                "data_freshness",
                                "halted",
                                {"status": "halted", "reason": error_msg},
                                True,
                                error_msg,
                            )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as status_check_err:
                logger.warning(f"[PHASE 1] Could not validate loader status accuracy (database error): {status_check_err}")

            # For coverage baseline: use CURRENT ACTIVE SYMBOL COUNT from stock_symbols
            # (not prior day's count, which can be lower/higher due to symbol list changes)
            # CRITICAL FIX (Session 365): Using prior_count instead of active_symbol_count
            # caused coverage > 100% when new symbols started trading. Changed to use
            # current active symbols as denominator to get true coverage percentage.
            cur.execute("""SELECT COUNT(*) FROM stock_symbols WHERE active = true""")
            row = cur.fetchone()
            if row is None or row[0] is None:
                total_active_symbols = 0
            else:
                total_active_symbols = row[0]

            coverage_pct = (symbols_loaded / max(total_active_symbols, 1)) * 100

            if symbols_loaded < min_symbol_count or coverage_pct < min_coverage_pct:
                from algo.orchestrator.phase_error_handling import (
                    ErrorCategory,
                    PhaseError,
                    log_phase_error,
                )

                # DIAGNOSTIC (temporary, session 130): this halt has fired with an
                # identical symbols_loaded count across many consecutive runs despite
                # price_daily loader tasks actively committing writes in the same
                # window (confirmed via their own CloudWatch logs) -- couldn't be
                # explained without seeing the real per-date distribution, and this
                # session had no direct SQL access to the production DB. Log it here
                # so the next halt makes the mechanism visible without needing that
                # access. Safe to remove once the underlying cause is confirmed.
                try:
                    cur.execute(
                        "SELECT date, COUNT(DISTINCT symbol) FROM price_daily "
                        "WHERE date >= %s GROUP BY date ORDER BY date DESC LIMIT 7",
                        (max_date - td(days=7),),
                    )
                    diag_rows = cur.fetchall()
                    logger.critical(
                        f"[PHASE 1 DIAGNOSTIC] max_date={max_date} recent_cutoff={phase1_recent_cutoff_days} "
                        f"per-date distribution (last 7 days with data): {list(diag_rows)}"
                    )
                except Exception as diag_err:
                    logger.warning(f"[PHASE 1 DIAGNOSTIC] failed to gather date distribution: {diag_err}")

                fail_reason = (
                    f"symbols {symbols_loaded} < min {min_symbol_count}"
                    if symbols_loaded < min_symbol_count
                    else f"coverage {coverage_pct:.1f}% < min {min_coverage_pct}%"
                )
                logger.critical(
                    f"[PHASE 1] Insufficient price coverage: {symbols_loaded} symbols ({coverage_pct:.1f}%) - {fail_reason}"
                )

                # CONSISTENCY: Use error categorization so operators know why trading halted
                error = PhaseError(
                    category=ErrorCategory.DATA_INCOMPLETE,
                    message=f"Price data coverage insufficient: {fail_reason}",
                    root_cause=f"Check that price_daily loader has loaded today's data (expected {min_symbol_count}+ symbols, got {symbols_loaded})",
                    recoverable=False,
                    log_level="critical",
                )
                log_phase_error(1, error, log_phase_result_fn)

                return PhaseResult(
                    1,
                    "price_coverage",
                    "halted",
                    {},
                    True,
                    f"Insufficient price data: {fail_reason}",
                )

            # Halt-critical tables: Core trading data - trading CANNOT proceed without these
            # - price_daily: Must have stock prices for all 10K+ symbols
            # - market_health_daily: Market breadth/regime (VIX, advance/decline, market breadth)
            # - market_exposure_daily: Market exposure policy limits (when to trade, position sizing)
            # - earnings_calendar: Earnings dates for trading blackout windows
            # NOTE: Metric enrichments (growth, quality, value, positioning, stability) are NOT
            # halt-critical. They're used for website display and portfolio analysis, not core signals.
            # Core signals come from price_daily + technical_data_daily. See Session 221.
            halt_tables = {
                "market_health_daily": "Market health (breadth/regime)",
                "earnings_calendar": "Earnings dates (blackout window gating)",
            }
            # Warning-only tables: enrichments + auxiliary data. Stale -> logged, trading continues.
            # Moved metric tables here (Session 221): they're website enrichments, not core to signals.
            # - growth_metrics, quality_metrics, value_metrics: Portfolio analysis only
            # - positioning_metrics, stability_metrics: Website enrichments only
            # Moved market_exposure_daily here (Session 239): loaded by separate EOD loader at 4:05 PM,
            # not orchestrator. Phase 5 reads via read_market_regime(date <= eval_date) so 1-day-old
            # data works fine. Morning orchestrator runs would false-halt without this move.
            warn_tables = {
                "market_exposure_daily": "Market exposure limits (EOD loader)",
                "trend_template_data": "Trend template (Minervini/Weinstein)",
                "sector_ranking": "Sector rankings",
                "growth_metrics": "Growth metrics (enrichment only)",
                "quality_metrics": "Quality metrics (enrichment only)",
                "value_metrics": "Value metrics (enrichment only)",
                "positioning_metrics": "Positioning metrics (enrichment only)",
                "stability_metrics": "Stability metrics (enrichment only)",
            }

            halt_stale = []  # pipeline-loaded tables - stale = HALT
            warn_stale = []  # auxiliary tables - stale = WARNING only
            # Structured (table_name, age) pairs mirroring halt_stale/warn_stale, kept separate
            # so the human-readable message strings above stay unchanged for existing callers
            # (notify_signal_staleness, log messages). This feeds the dashboard's PHASE EXECUTION
            # DETAILS panel (dashboard/panels/health.py, phase_num==1 branch), which reads
            # tables_validated/tables_fresh/tables_stale/stale_tables from PhaseResult.data - keys
            # this function never populated, so that panel section always rendered nothing.
            stale_table_details: list[dict[str, Any]] = []

            # Tables checked by MAX(date) vs price_daily latest date
            # Note: earnings_calendar uses earnings_date instead of date
            # Note: metrics tables (growth, quality, value, positioning, stability) use updated_at instead of date
            date_column_overrides = {
                "earnings_calendar": "earnings_date",
                "growth_metrics": "updated_at",
                "quality_metrics": "updated_at",
                "value_metrics": "updated_at",
                "positioning_metrics": "updated_at",
                "stability_metrics": "updated_at",
            }
            # Only check tables that have a date column for freshness
            date_checked_tables = {**halt_tables, **warn_tables}

            # Per-table reference dates: some tables have upstream dependencies that limit how
            # current they can be. Compare against the appropriate upstream date, not global max.
            # - market_health_daily: limited by VIX availability in price_daily (^VIX published EOD)
            # - market_exposure_daily: limited by market_health_daily availability
            # - all others: compare against global price_daily max_date
            vix_max_date: _date | None = None
            health_max_date: _date | None = None
            try:
                cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol = '^VIX'")
                vix_row = cur.fetchone()
                if not vix_row or vix_row[0] is None:
                    logger.error(
                        "[PHASE 1] CRITICAL: VIX data missing from price_daily. Cannot evaluate market health freshness."
                    )
                    raise RuntimeError(
                        "[PHASE 1] VIX price data unavailable. Check price_daily loader for ^VIX symbol."
                    )
                vix_max_date = vix_row[0]

                cur.execute("SELECT MAX(date) FROM market_health_daily")
                health_row = cur.fetchone()
                if not health_row or health_row[0] is None:
                    logger.error(
                        "[PHASE 1] CRITICAL: market_health_daily table is empty. Cannot evaluate market breadth."
                    )
                    raise RuntimeError("[PHASE 1] Market health data unavailable. Check market_health_daily loader.")
                health_max_date = health_row[0]

                # CRITICAL FIX: Verify market_health_daily has CRITICAL COLUMNS populated, not just the table exists
                # Early morning: table might exist but put_call_ratio not loaded yet
                cur.execute(
                    """
                    SELECT COUNT(*) as total_rows,
                           SUM(CASE WHEN put_call_ratio IS NOT NULL THEN 1 ELSE 0 END) as pcr_rows,
                           SUM(CASE WHEN vix_level IS NOT NULL THEN 1 ELSE 0 END) as vix_rows
                    FROM market_health_daily
                    WHERE date = %s
                    """,
                    (health_max_date,),
                )
                health_col_row = cur.fetchone()
                total_rows, pcr_rows, vix_rows = health_col_row if health_col_row else (0, 0, 0)
                _check_health_column_coverage(total_rows, pcr_rows, vix_rows, health_max_date)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"[PHASE 1] CRITICAL: Database error fetching VIX/health reference dates: {e}")
                raise RuntimeError(f"[PHASE 1] Cannot fetch market reference dates from database: {e}") from e

            # CRITICAL FIX (Session 288): Validate UPSTREAM reference tables are fresh
            # before using them to validate downstream tables.
            # Previous bug: if market_health_daily was 9 days stale, and market_exposure_daily
            # was also 9 days stale, comparing them to each other would pass (both same age).
            # Solution: Compare upstream tables (market_health_daily, etc.) to expected trading day.

            if health_max_date < acceptable_min_date:
                days_behind = (acceptable_min_date - health_max_date).days
                logger.critical(
                    f"[PHASE 1] UPSTREAM TABLE STALE: market_health_daily is {days_behind} day(s) old "
                    f"(expected {acceptable_min_date}, got {health_max_date}). "
                    f"Cannot use stale upstream table to validate downstream tables."
                )
                halt_stale.append(f"market_health_daily is {days_behind} day(s) stale (upstream reference invalid)")

            # Map each table to its upstream reference date for staleness comparison
            # CRITICAL FIX: Must include all tables that will be checked below
            table_reference_dates = {
                "market_health_daily": vix_max_date,
                "market_exposure_daily": health_max_date,
                "earnings_calendar": run_date,  # Earnings calendar reference is the run date itself
                "earnings_calendar_sec": run_date,
                "price_daily": run_date,
                "technical_data_daily": run_date,
                "stock_scores": run_date,
                "trend_template_data": run_date,
                "sector_ranking": run_date,
                "growth_metrics": run_date,
                "quality_metrics": run_date,
                "value_metrics": run_date,
                "positioning_metrics": run_date,
                "stability_metrics": run_date,
            }

            try:
                union_parts = []
                for table_name in date_checked_tables.keys():
                    date_col = date_column_overrides.get(table_name, "date")
                    if date_col is None:
                        raise RuntimeError(
                            f"[PHASE 1] Table {table_name} missing date_column_override - cannot determine date column"
                        )
                    union_parts.append(f"SELECT '{table_name}' as tbl, MAX({date_col}) as max_dt FROM {table_name}")

                union_query = " UNION ALL ".join(union_parts)
                cur.execute(union_query)

                max_dates = {}
                for row in cur.fetchall():
                    if row is None or len(row) < 2:
                        raise RuntimeError(
                            f"[PHASE 1] Table freshness query returned incomplete row: {row}. "
                            "Expected (table_name, max_date) tuple."
                        )
                    table_name_val = row[0]
                    max_date_val = row[1]
                    if table_name_val is None:
                        raise RuntimeError(
                            "[PHASE 1] Table freshness query returned NULL table name. "
                            "Union query construction may be broken."
                        )
                    max_dates[table_name_val] = max_date_val

                for table_name, description in date_checked_tables.items():
                    is_halt_table = table_name in halt_tables
                    # Use per-table reference date where applicable (e.g., market_health uses VIX date)
                    # CRITICAL: Fail fast if table reference date not defined - prevents staleness misreporting
                    if table_name not in table_reference_dates:
                        raise RuntimeError(
                            f"[PHASE 1] CRITICAL: Table {table_name} missing reference date in table_reference_dates. "
                            f"Cannot determine staleness baseline. This table must have an explicit reference date."
                        )
                    ref_date = table_reference_dates[table_name]
                    try:
                        table_max_date = max_dates.get(table_name)

                        # CRITICAL FIX: Ensure datetime to date conversion for all table max dates
                        if table_max_date is not None and isinstance(table_max_date, dt):
                            table_max_date = table_max_date.date()

                        if table_max_date is None:
                            msg = f"{description} is empty"
                            if is_halt_table:
                                logger.critical(f"[PHASE 1] {msg}")
                                halt_stale.append(msg)
                            else:
                                logger.warning(f"[PHASE 1] {msg}")
                                warn_stale.append(msg)
                            stale_table_details.append({"table_name": table_name, "age": "empty"})
                            continue

                        if table_max_date < ref_date:
                            days_behind = (ref_date - table_max_date).days
                            max_tolerance_days = phase1_halt_table_max_tolerance_days if is_halt_table else 0
                            if days_behind > max_tolerance_days:
                                msg = f"{description} is {days_behind} day(s) stale"
                                if is_halt_table:
                                    logger.critical(f"[PHASE 1] {msg}")
                                    halt_stale.append(msg)
                                else:
                                    logger.warning(f"[PHASE 1] {msg}")
                                    warn_stale.append(msg)
                                stale_table_details.append({"table_name": table_name, "age": f"{days_behind}d"})
                            else:
                                msg = f"{description} is {days_behind} day(s) behind (within 1-day tolerance)"
                                logger.info(f"[PHASE 1] {msg}")

                    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                        msg = f"{description} check failed: {str(e)[:50]}"
                        if is_halt_table:
                            logger.critical(f"[PHASE 1] {msg} - FAIL-CLOSED")
                            halt_stale.append(msg)
                        else:
                            logger.warning(f"[PHASE 1] {msg}")
                            warn_stale.append(msg)
                        stale_table_details.append({"table_name": table_name, "age": "check failed"})
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.critical(
                    f"[PHASE 1] CRITICAL: Failed to check table freshness - cannot verify data integrity: {e}",
                    exc_info=True,
                )
                log_phase_result_fn(
                    1,
                    "table_freshness_check_error",
                    "halt",
                    f"Could not verify table freshness: {str(e)[:100]}",
                )
                return PhaseResult(
                    1,
                    "table_freshness_check_error",
                    "halted",
                    {},
                    True,
                    f"Table freshness check failed (cannot distinguish stale from error): {str(e)[:100]}",
                )

            if warn_stale:
                logger.warning(
                    f"[PHASE 1] Non-critical staleness (auxiliary tables, trading continues): {'; '.join(warn_stale)}"
                )

            if halt_stale:
                # CRITICAL FIX: NEVER bypass halt on critical data gaps, even in dry_run mode
                # dry_run mode is for testing - it should still validate and report halts,
                # just not actually trigger downstream consequences. But Phase 1 freshness checks
                # are safety gates - they must always execute fully and report halt status.
                logger.critical(f"[PHASE 1] CRITICAL DATA GAPS (pipeline tables): {'; '.join(halt_stale)}")
                log_phase_result_fn(
                    1,
                    "signal_tables_stale",
                    "halt",
                    f"Stale/missing pipeline data: {'; '.join(halt_stale[:3])}",
                )
                from algo.reporting.notifications import notify_signal_staleness

                notify_signal_staleness(halt_stale)
                tables_validated = 1 + len(date_checked_tables)
                return PhaseResult(
                    1,
                    "signal_tables_stale",
                    "halted",
                    {
                        "tables_validated": tables_validated,
                        "tables_fresh": tables_validated - len(stale_table_details),
                        "tables_stale": len(stale_table_details),
                        "stale_tables": stale_table_details,
                        "validation_status": "HALTED",
                    },
                    True,
                    f"Critical pipeline tables stale/missing: {halt_stale[0]}",
                )

            elapsed = time.time() - phase_start
            phase1_end_et = dt.now(EASTERN_TZ)

            sla_status = ""
            if pipeline_context == "MORNING":
                sla_deadline = phase1_end_et.replace(hour=9, minute=30, second=0, microsecond=0)
                if phase1_end_et < sla_deadline:
                    minutes_until_sla = (sla_deadline - phase1_end_et).total_seconds() / 60
                    sla_status = f" [SLA OK: {minutes_until_sla:.0f}m until 9:30 AM]"
                else:
                    sla_status = " [SLA WARNING: Past 9:30 AM]"

            warn_suffix = f" ({len(warn_stale)} auxiliary warnings)" if warn_stale else ""
            logger.info(f"[PHASE 1] PASS - PIPELINE DATA FRESH{sla_status}{warn_suffix}")
            logger.info(f"  - Prices: {max_date} ({symbols_loaded} symbols, {coverage_pct:.1f}%)")
            if not warn_stale:
                logger.info("  - All pipeline tables (market_health, trend_template, market_exposure) fresh")
            else:
                logger.info(
                    "  - Critical pipeline tables (market_health, market_exposure) fresh; auxiliary warnings above"
                )
            logger.info(f"  - Check completed in {elapsed:.1f}s")

            # CRITICAL FIX 2026-07-05: Validate that metric loaders are ready before Phase 7 signal generation
            # These loaders (quality, growth, value, positioning, stability, momentum) feed into stock_scores
            # which feed into signal generation. If metrics are all-unavailable, stock_scores will fail.
            logger.info("[PHASE 1] Validating upstream metric loaders ready for stock_scores...")
            degraded_reason = None
            try:
                from loaders.load_stock_scores import StockScoresLoader

                metric_validator = StockScoresLoader()
                metric_validator.validate_upstream_metrics_ready()
                logger.info("[PHASE 1] Metric loaders validation: PASS - All metric loaders ready")

                # FIXED 2026-07-15: Add stock_scores data completeness check (Issue #6 from Session 166 audit)
                # Validate that scores have sufficient completeness (60%+ avg for available scores)
                # FIXED 2026-07-18: Only average AVAILABLE scores (data_unavailable=FALSE)
                # Stocks with 0% completeness are legitimately unavailable due to missing metrics,
                # and should not drag down the average or halt trading for all other stocks.
                try:
                    # CRITICAL: stock_scores.updated_at is `timestamp without time zone`, written via
                    # datetime.now(timezone.utc) in load_stock_scores.py (i.e. the stored digits ARE
                    # UTC wall-clock). TRADING-DAY FIX: Don't check "last 24 hours" (fails on Monday
                    # morning when Friday's EOD scores are 48h old). Instead check if max score date
                    # matches the most recent trading day in the DB (which stock_scores depends on for
                    # underlying metric data). Stock scores have no date column, so check updated_at
                    # against price_daily's max date (latest trading day with prices).
                    cur.execute("""
                        SELECT AVG(data_completeness) as avg_completeness,
                               COUNT(*) as total_available_scores,
                               COUNT(CASE WHEN data_completeness >= 70 THEN 1 END) as complete_scores,
                               COUNT(*) FILTER (WHERE data_unavailable = FALSE) as available_count,
                               MAX(updated_at) as max_updated
                        FROM stock_scores
                        WHERE data_unavailable = FALSE
                    """)
                    completeness_row = cur.fetchone()

                    # Verify stock_scores were computed for the latest trading day available in price data
                    cur.execute("SELECT MAX(date) FROM price_daily")
                    price_row = cur.fetchone()
                    if not price_row or price_row[0] is None:
                        raise RuntimeError("[PHASE 1] price_daily table is empty - cannot verify stock_scores freshness")
                    latest_price_date = price_row[0]

                    # Stock scores should have been updated AFTER the latest price date (they're computed
                    # end-of-day). Allow up to 48 hours for EOD pipelines to run (covering overnight + weekend scenarios).
                    scores_age_hours = None
                    if completeness_row and completeness_row[4] and latest_price_date:
                        from datetime import datetime, timezone
                        now_utc = datetime.now(timezone.utc)
                        max_updated = completeness_row[4]
                        if max_updated.tzinfo is None:
                            max_updated = max_updated.replace(tzinfo=timezone.utc)
                        scores_age_hours = (now_utc - max_updated).total_seconds() / 3600

                    if completeness_row and completeness_row[0] is not None and scores_age_hours is not None and scores_age_hours < 48:
                        avg_completeness = float(completeness_row[0])
                        total_available = completeness_row[1]
                        complete_scores = completeness_row[2]

                        logger.info(
                            f"[PHASE 1] Stock scores completeness: {avg_completeness:.1f}% avg "
                            f"({complete_scores}/{total_available} available symbols >= 70%)"
                        )

                        # GOVERNANCE: Allow proceeding if 60%+ of available scores are complete
                        # Stocks with insufficient metrics are properly marked data_unavailable
                        # and excluded from signal generation, so degradation is contained
                        if avg_completeness < 60:
                            logger.warning(
                                f"[PHASE 1] DEGRADED: Stock scores avg completeness only {avg_completeness:.1f}%. "
                                f"Position sizing may use incomplete metric data. "
                                f"If this persists, check: {[t for t in halt_tables if 'metric' in t]}"
                            )
                            degraded_reason = (
                                f"Stock scores only {avg_completeness:.1f}% complete "
                                f"(missing positioning/stability/growth metrics)"
                            )
                    else:
                        # Stale, missing, or incompute able scores
                        if completeness_row and completeness_row[4] is not None and scores_age_hours is not None and scores_age_hours >= 48:
                            logger.warning(
                                f"[PHASE 1] stock_scores stale: computed {scores_age_hours:.1f}h ago "
                                f"(max_updated={completeness_row[4]}). "
                                f"Latest price data is from {latest_price_date}. "
                                f"Scores are older than 48h threshold. "
                                f"Check if end-of-day pipeline has run."
                            )
                        else:
                            logger.warning(
                                "[PHASE 1] stock_scores data unavailable or no available symbols. "
                                "Proceeding but scores will be unavailable for signal generation."
                            )
                except Exception as completeness_err:
                    logger.warning(
                        f"[PHASE 1] Could not check stock_scores completeness: {completeness_err}. "
                        "Will proceed with signal generation using available scores."
                    )
            except RuntimeError as e:
                metric_error = str(e)
                logger.warning(f"[PHASE 1] Metric loaders validation failed: {metric_error}")
                try:
                    cur.execute("""
                        SELECT COUNT(*) FROM quality_metrics WHERE updated_at > NOW() - INTERVAL '7 days'
                        UNION ALL SELECT COUNT(*) FROM growth_metrics WHERE updated_at > NOW() - INTERVAL '7 days'
                        UNION ALL SELECT COUNT(*) FROM stability_metrics WHERE updated_at > NOW() - INTERVAL '7 days'
                    """)
                    metric_counts = cur.fetchall()
                    has_recent_metrics = any(row[0] > 0 for row in metric_counts)

                    if has_recent_metrics:
                        logger.critical(
                            f"[PHASE 1] CRITICAL: Metrics exist but validation failed. {metric_error}. "
                            f"GOVERNANCE requires fail-fast on metric validation failure. "
                            f"Root cause must be resolved before trading resumes."
                        )
                        halt_reason = f"Metric loader validation failed: {metric_error[:100]}"
                        log_phase_result_fn(1, "metric_validation_failed", "halt", halt_reason)
                        return PhaseResult(
                            1,
                            "metric_validation_failed",
                            "halted",
                            {},
                            True,
                            halt_reason,
                        )
                    else:
                        logger.critical(f"[PHASE 1] CRITICAL: Metric loaders validation failed: {metric_error}")
                        halt_reason = f"Required metric loaders not ready: {metric_error[:100]}"
                        log_phase_result_fn(1, "metric_loaders_not_ready", "halt", halt_reason)
                        return PhaseResult(
                            1,
                            "metric_loaders_not_ready",
                            "halted",
                            {},
                            True,
                            halt_reason,
                        )
                except Exception as check_err:
                    halt_reason = f"Could not verify metric availability: {str(check_err)[:100]}"
                    logger.error(f"[PHASE 1] {halt_reason}")
                    logger.critical(f"[PHASE 1] CRITICAL: Metric loaders validation failed: {metric_error}")
                    log_phase_result_fn(1, "metric_verification_error", "halt", halt_reason)
                    return PhaseResult(
                        1,
                        "metric_verification_error",
                        "halted",
                        {},
                        True,
                        halt_reason,
                    )

            log_phase_result_fn(
                1,
                "all_tables_fresh",
                "success",
                f"All critical tables fresh: prices={max_date}, coverage={coverage_pct:.1f}%"
                + (f" [DEGRADED MODE: {degraded_reason}]" if degraded_reason else ""),
            )

            # GOVERNANCE COMPLIANCE: Halt on degraded data (never allow incomplete metrics for trading)
            # Ref: GOVERNANCE.md - "Never accept scores with <50% data completeness"
            if degraded_reason:
                logger.critical(
                    f"[PHASE 1] HALTING: Degraded data not allowed for trading. "
                    f"Reason: {degraded_reason}. "
                    f"Fix: Ensure all metric loaders complete with >70% symbol coverage before trading."
                )
                log_phase_result_fn(1, "degraded_data_halt", "halt", degraded_reason)
                phase_data: dict[str, Any] = {
                    "status": "halted",
                    "reason": degraded_reason,
                }
                validate_phase_data(1, phase_data)
                return PhaseResult(
                    1,
                    "degraded_data_halt",
                    "halted",
                    phase_data,
                    True,  # HALT on degraded data
                    degraded_reason,
                )

            # Return with ok status when all data is complete
            tables_validated = 1 + len(date_checked_tables)
            phase_data: dict[str, Any] = {  # type: ignore[no-redef]
                "status": "ok",
                "price_date": str(max_date),
                "symbols_loaded": symbols_loaded,
                "coverage_pct": coverage_pct,
                "tables_validated": tables_validated,
                "tables_fresh": tables_validated - len(stale_table_details),
                "tables_stale": len(stale_table_details),
                "stale_tables": stale_table_details,
                "validation_status": "PASS" if not stale_table_details else "PASS (with warnings)",
            }
            validate_phase_data(1, phase_data)
            return PhaseResult(
                1,
                "all_tables_fresh",
                "ok",
                phase_data,
                False,  # Not halted
                "All critical data fresh and complete",
            )

    except Exception as e:
        # FIXED 2026-07-07: Include exception type and full message, not just truncated str(e)
        exception_type = type(e).__name__
        exception_msg = str(e) if str(e) else "(no message)"
        error_summary = f"{exception_type}: {exception_msg}"[:200]
        logger.error(f"[PHASE 1] ERROR: {error_summary}", exc_info=True)
        log_phase_result_fn(1, "error", "error", error_summary)
        phase_data = {"status": "error", "reason": f"Phase 1 failed: {error_summary}"}
        validate_phase_data(1, phase_data)
        return PhaseResult(1, "error", "error", phase_data, True, error_summary)
