#!/usr/bin/env python3
"""
PHASE 1 HELPERS: PRICE_DAILY FRESHNESS RESOLUTION

Pure extract-method split of phase1_data_freshness.py's run() (see that module's docstring
for the overall Phase 1 contract). This file holds the sequence of steps that determine
whether price_daily is fresh enough to trade on:

1. Resolve price_daily's reference MAX(date) and sanity-check it (phantom NULL-price rows,
   stock_symbols pre-flight).
2. Compute "last trading day" / "acceptable min date" per the MORNING/INTRADAY/EOD pipeline
   context, including the data-provider-delay grace periods around market close.
3. Resolve the active-symbol coverage count for the appropriate date.
4. Compute final coverage_pct against the active symbol universe and decide whether Phase 1
   must halt on insufficient price coverage.

Two closely related pieces - the SESSION 89 stale-reprocessing fallback query and the EOD
today's-price completeness check - stay defined in phase1_data_freshness.py itself rather than
here: several regression tests scan that file's source text directly for them by name/pattern
(test_phase1_stale_reprocessing_fallback_query_bounded_20260831.py,
test_phase1_afternoon_revalidation_fix.py), so moving them would break whitebox tests without
changing any real behavior.

NO BEHAVIOR CHANGE: every function here is a verbatim relocation of code that used to live
inline in run() - control flow, thresholds, log messages, and return values are unchanged.
"""

import logging
import time
from collections.abc import Callable
from datetime import date as _date
from datetime import datetime as dt
from datetime import timedelta as td
from typing import Any

import psycopg2

from algo.orchestrator.phase_result import PhaseResult
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


def preflight_verify_stock_symbols_table(log_phase_result_fn: Callable[..., Any]) -> PhaseResult | None:
    """Pre-validate stock_symbols table is populated before any other Phase 1 checks.

    CRITICAL FIX: Pre-validate stock_symbols table is populated
    If symbols loader failed, all downstream phases will fail
    Better to catch this early with clear error message

    Returns a halting PhaseResult if the table is missing/empty or a database/code error
    occurred, else None to proceed.
    """
    try:
        with DatabaseContext("read") as pre_check_cur:
            pre_check_cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
            # CRITICAL FIX: Check if query returned results before indexing
            result = pre_check_cur.fetchone()
            if result is None or len(result) < 1:
                error_msg = (
                    "[PHASE 1 CRITICAL] stock_symbols COUNT query failed (no results or empty tuple). "
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
                return PhaseResult(
                    1, "data_freshness", "halted", {"status": "halted", "reason": "no active symbols"}, True, error_msg
                )
            logger.info(f"[PHASE 1] Pre-flight: stock_symbols table OK ({symbol_count:,} active symbols)")
            return None
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as db_err:
        error_msg = (
            f"[PHASE 1 CRITICAL] Pre-flight validation failed - database error: {type(db_err).__name__}: {db_err}. "
            f"This prevents all downstream phases from running correctly. "
            f"Check: database connectivity, RDS credentials, or schema consistency."
        )
        logger.critical(error_msg)
        log_phase_result_fn(1, "data_freshness", "halt", error_msg)
        return PhaseResult(
            1,
            "data_freshness",
            "halted",
            {"status": "halted", "reason": "database error during pre-flight"},
            True,
            error_msg,
        )
    except (ValueError, TypeError, AttributeError) as code_err:
        error_msg = (
            f"[PHASE 1 CRITICAL] Pre-flight validation failed - code error: {type(code_err).__name__}: {code_err}. "
            f"This indicates a bug in Phase 1 pre-flight logic. Report to developers."
        )
        logger.critical(error_msg)
        log_phase_result_fn(1, "data_freshness", "halt", error_msg)
        return PhaseResult(
            1, "data_freshness", "halted", {"status": "halted", "reason": "code error in pre-flight"}, True, error_msg
        )
    except Exception as unknown_err:
        error_msg = (
            f"[PHASE 1 CRITICAL] Pre-flight validation failed - unexpected error: {type(unknown_err).__name__}: {unknown_err}. "
            f"This prevents all downstream phases from running correctly. "
            f"Fail-fast: halting Phase 1 to surface unknown issue."
        )
        logger.critical(error_msg)
        log_phase_result_fn(1, "data_freshness", "halt", error_msg)
        return PhaseResult(
            1,
            "data_freshness",
            "halted",
            {"status": "halted", "reason": "unknown error in pre-flight"},
            True,
            error_msg,
        )


def resolve_price_daily_max_date(
    cur: Any, log_phase_result_fn: Callable[..., Any]
) -> tuple[_date | None, PhaseResult | None]:
    """Find price_daily's reference MAX(date), excluding index tickers.

    NOTE: stock_scores is NOT validated here; it's an orchestrator OUTPUT (Phase 5),
    not a pipeline loader INPUT. Validating orchestrator outputs in Phase 1 breaks first-run.
    Phase 7 (Signal Generation) will handle missing stock_scores when it runs.
    CRITICAL FIX 2026-08-02: Exclude index tickers (^VIX, etc) from MAX(date)
    Index tickers update pre-market before equity prices, skewing freshness check

    Returns (max_date, None) on success, or (None, PhaseResult) to halt immediately.
    """
    cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol NOT LIKE '^%%'")
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            "[PHASE 1] price_daily MAX(date) query returned NULL. Query malformed or database connection failed."
        )
    max_date = row[0]
    if max_date is None:
        logger.critical("[PHASE 1] price_daily table is empty")
        log_phase_result_fn(1, "price_data", "halt", "price_daily table is empty")
        return None, PhaseResult(
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

    return max_date, None


def verify_active_symbol_list(
    cur: Any, log_phase_result_fn: Callable[..., Any]
) -> tuple[int | None, PhaseResult | None]:
    """Verify stock_symbols table is pre-loaded (required for ALL loaders).

    Session 299 FIX: More robust symbol check with better error diagnostics
    Only retry on transient errors (lock timeouts, connection issues), not structural issues

    Returns (symbol_count, None) on success, or (None, PhaseResult) to halt.
    """
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
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as query_err:
            error_str = str(query_err).lower()
            is_transient = any(kw in error_str for kw in transient_error_keywords)

            if is_transient and attempt < max_retries - 1:
                logger.warning(f"[PHASE 1] Transient stock_symbols check error (attempt {attempt + 1}): {query_err}")
                time.sleep(0.3)
                continue
            else:
                # Permanent error or last attempt
                logger.error(f"[PHASE 1] stock_symbols check failed (attempt {attempt + 1}): {query_err}")
                last_error = f"{type(query_err).__name__}: {str(query_err)[:500]}"
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
        return None, PhaseResult(
            1,
            "symbol_list_missing",
            "halted",
            {},
            True,
            f"stock_symbols table is empty - symbols must be loaded before trading. Error: {error_detail}",
        )
    logger.info(f"[PHASE 1] Symbol list verified: {symbol_count} active symbols")
    return symbol_count, None


def detect_phantom_price_rows(cur: Any) -> None:
    """Detect phantom rows in price_daily (NULL prices counted as fresh data).

    CRITICAL FIX: Detect phantom rows in price_daily (NULL prices counted as fresh data)
    These bypass the freshness check by inflating MAX(date) and symbol count
    CRITICAL FIX 2026-08-02: Exclude index tickers from MAX(date) in nested SELECT
    """
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


def compute_last_trading_day(run_date_obj: _date, pipeline_context: str) -> _date:
    """Determine the "last trading day" whose data we require, per pipeline context.

    Market hours: 9:30 AM - 4:00 PM ET.
    If orchestrator runs DURING market hours (before 16:00 ET), expect previous trading day's data.
    If orchestrator runs AFTER market close (16:00+ ET), expect same-day data.
    """
    from algo.infrastructure import MarketCalendar

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

    return last_trading_day


def compute_acceptable_min_date_with_grace(
    now_et: Any, market_close_time: Any, pipeline_context: str, last_trading_day: _date
) -> _date:
    """Apply the post-close data-provider-delay grace period to acceptable_min_date.

    TOLERANCE for data provider delays: if we're in IMMEDIATE EOD context (4:00-4:30 PM),
    allow previous trading day's data as acceptable (data providers may not have
    same-day data ready immediately after market close).
    CRITICAL FIX: This tolerance should NOT apply hours later (after 4:30 PM).
    By 5:00 PM+, all data providers should have same-day prices ready.

    CRITICAL FIX: `now_et.hour` is always an integer, so comparing it against the
    float 16.5 can never distinguish "before 4:30 PM" from "after" within the same
    clock hour - `16 <= 16 < 16.5` and `16 >= 16.5` are True/False respectively for
    EVERY minute from 16:00:00 through 16:59:59, not just the first 30. Confirmed live
    2026-07-27: for any EOD-context run landing in that hour (e.g. a late/retried run,
    not the fixed morning/afternoon/preclose/evening schedule), the grace period would
    silently stay active the entire hour instead of expiring at 16:30 as the comments
    below and the log line at 16:36 both claim - stale same-day data would be masked by
    falling back to the prior trading day for up to 30 extra minutes. Compare against
    an actual time boundary instead of an hour/float mismatch.
    BUG FIX 2026-08-24: same early-close blindness as is_after_market_close above -
    hardcoded to 16:00/16:30 regardless of day, so on a real 1:00 PM early close this
    30-minute data-provider-delay grace period fired 3 hours late (4:00-4:30 PM,
    when providers already had same-day data ready) instead of the actual post-close
    window (1:00-1:30 PM) when it would matter. Reuses market_close_time computed
    above from MarketCalendar, not a fresh hardcoded hour=16.
    """
    from algo.infrastructure import MarketCalendar

    acceptable_min_date = last_trading_day
    market_close = now_et.replace(hour=market_close_time.hour, minute=market_close_time.minute, second=0, microsecond=0)
    grace_period_end = market_close + td(minutes=30)
    if pipeline_context == "EOD" and market_close <= now_et < grace_period_end:
        # Allow previous trading day as fallback if same-day not yet available
        # (ONLY in immediate aftermath of market close, within 30 min)
        prev_trading_day = last_trading_day - td(days=1)
        while prev_trading_day > last_trading_day - td(days=10):
            if MarketCalendar.is_trading_day(prev_trading_day):
                acceptable_min_date = prev_trading_day
                logger.info(f"[PHASE 1] Grace period active (4:00-4:30 PM): accepting {prev_trading_day} as valid")
                break
            prev_trading_day -= td(days=1)
    elif pipeline_context == "EOD" and now_et >= grace_period_end:
        # After 4:30 PM: must have same-day data
        logger.info(f"[PHASE 1] Grace period expired (> 4:30 PM): requiring {last_trading_day} data")

    return acceptable_min_date


def apply_eod_yesterday_price_grace(
    pipeline_context: str, max_date: _date, acceptable_min_date: _date, now_et: Any, last_trading_day: _date
) -> _date:
    """During EOD context before 6 PM, accept yesterday's prices if today's haven't loaded yet.

    CRITICAL FIX 2026-08-06: During EOD context, if we're still before 6 PM ET and only have yesterday's prices,
    accept them gracefully instead of halting. EOD prices may take 1-2 hours to load after market close.
    This allows afternoon/evening orchestrator runs to proceed with position monitoring and exit execution
    while waiting for same-day price_daily to load. Legitimate halts (circuit breakers) are still enforced.
    """
    if (
        pipeline_context == "EOD" and max_date == acceptable_min_date - td(days=1) and now_et.hour < 18
    ):  # Before 6 PM ET
        logger.info(
            f"[PHASE 1] EOD context grace: Using {max_date} (yesterday) instead of {last_trading_day} "
            f"(today). EOD prices may still be loading. Will accept for up to 2h after market close."
        )
        return max_date  # Accept yesterday as valid during this grace period
    return acceptable_min_date


def check_price_staleness_halt(
    max_date: _date, acceptable_min_date: _date, last_trading_day: _date, log_phase_result_fn: Callable[..., Any]
) -> PhaseResult | None:
    """Halt if price_daily's MAX(date) is older than the acceptable minimum date.

    CRITICAL FIX: Require LAST-TRADING-DAY data with actual non-NULL prices
    "Last trading day" = TODAY if today is a trading day (Mon-Fri), otherwise most recent trading day
    Reject multi-day window (allows trading on stale data)
    Reject phantom rows (NULL prices counted as fresh data)
    This is the RIGHT thing: require data for the most recent market close, always
    """
    if max_date >= acceptable_min_date:
        return None

    from algo.orchestrator.phase_error_handling import ErrorCategory, PhaseError, log_phase_error

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


def resolve_coverage_check_date_and_symbols_loaded(
    cur: Any, pipeline_context: str, now_et: Any, last_trading_day: _date
) -> tuple[_date, int]:
    """Resolve which date to use for the active-symbol coverage count, and query it.

    CRITICAL FIX 2026-07-29: For afternoon runs, we also need to check TODAY's data
    because the orchestrator needs today's prices for Phase 6 exit execution.
    The loader should have completed by mid-day, so lack of today's data indicates
    loader failure, not normal lag. Check both yesterday (for intraday validation)
    and today (for afternoon orchestrator requirements).

    Both counts are scoped to symbols currently marked active in stock_symbols.
    price_daily retains history for ~10.6K symbols total, but only ~5.5K are
    still active - the other ~5.1K are delisted/removed tickers whose rows stop
    getting new dates entirely. An unscoped COUNT(DISTINCT symbol) against the
    full table (as this used to be) compares today's genuinely-active fetch
    against that inflated historical figure, permanently capping coverage_pct
    around 45-50% no matter how complete today's load is - confirmed live
    2026-07-20 (real coverage 85.5% scoped to active symbols, computed as 42.8%
    unscoped, incorrectly halting Phase 1 on every EOD-context run since the
    active universe last shrank).
    CRITICAL FIX 2026-08-06: For EOD runs before 6 PM, if today's prices haven't loaded,
    check yesterday's coverage instead of today's (which will be 0).
    This allows exit execution to proceed while waiting for EOD prices to load.
    """
    from algo.infrastructure import MarketCalendar

    coverage_check_date = last_trading_day
    if pipeline_context == "EOD" and now_et.hour < 18:
        # Try today's data first, but fall back to yesterday if not available
        cur.execute(
            """SELECT COUNT(DISTINCT pd.symbol)
               FROM price_daily pd
               JOIN stock_symbols ss ON ss.symbol = pd.symbol AND ss.active = true
               WHERE pd.date = %s AND pd.close IS NOT NULL AND pd.open IS NOT NULL""",
            (last_trading_day,),
        )
        today_coverage_row = cur.fetchone()
        today_coverage = today_coverage_row[0] if today_coverage_row and today_coverage_row[0] is not None else 0

        if today_coverage == 0:
            # Today's prices not loaded - check yesterday
            yesterday = last_trading_day - td(days=1)
            while yesterday > last_trading_day - td(days=5):
                if MarketCalendar.is_trading_day(yesterday):
                    coverage_check_date = yesterday
                    break
                yesterday -= td(days=1)
            logger.info(
                f"[PHASE 1] EOD grace (< 6 PM): Today's prices not loaded, checking {coverage_check_date} instead"
            )

    cur.execute(
        """SELECT COUNT(DISTINCT pd.symbol)
           FROM price_daily pd
           JOIN stock_symbols ss ON ss.symbol = pd.symbol AND ss.active = true
           WHERE pd.date = %s AND pd.close IS NOT NULL AND pd.open IS NOT NULL""",
        (coverage_check_date,),
    )
    row = cur.fetchone()
    if row is None or row[0] is None:
        raise RuntimeError(f"Symbol count query failed for coverage check date ({coverage_check_date})")
    symbols_loaded = row[0]

    return coverage_check_date, symbols_loaded


def verify_loader_status_completion_integrity(cur: Any, log_phase_result_fn: Callable[..., Any]) -> PhaseResult | None:
    """Validate that data_loader_status.completion_pct matches actual symbol count.

    CRITICAL FIX: Validate that data_loader_status.completion_pct matches actual symbol count
    Session 344: Found that completion_pct was calculated on row_count, not symbol_count,
    causing false "100% complete" when only 1 symbol out of 5000+ was actually loaded.
    This check catches that mismatch and fails fast rather than proceeding with incomplete data.
    CRITICAL FIX 2026-08-02: Fail-fast on data integrity mismatch (was just logging)
    """
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

    return None


def compute_coverage_pct(cur: Any, symbols_loaded: int) -> tuple[float, int]:
    """Compute coverage_pct against the CURRENT ACTIVE SYMBOL COUNT from stock_symbols.

    For coverage baseline: use CURRENT ACTIVE SYMBOL COUNT from stock_symbols
    (not prior day's count, which can be lower/higher due to symbol list changes)
    CRITICAL FIX (Session 365): Using prior_count instead of active_symbol_count
    caused coverage > 100% when new symbols started trading. Changed to use
    current active symbols as denominator to get true coverage percentage.
    """
    cur.execute("""SELECT COUNT(*) FROM stock_symbols WHERE active = true""")
    row = cur.fetchone()
    if row is None or row[0] is None:
        total_active_symbols = 0
    else:
        total_active_symbols = row[0]

    coverage_pct = (symbols_loaded / max(total_active_symbols, 1)) * 100
    return coverage_pct, total_active_symbols


def check_price_coverage_halt(
    cur: Any,
    symbols_loaded: int,
    coverage_pct: float,
    min_symbol_count: int,
    min_coverage_pct: float,
    max_date: _date,
    phase1_recent_cutoff_days: int,
    log_phase_result_fn: Callable[..., Any],
) -> PhaseResult | None:
    """Halt if price coverage is below the configured symbol-count/percentage thresholds."""
    if symbols_loaded >= min_symbol_count and coverage_pct >= min_coverage_pct:
        return None

    from algo.orchestrator.phase_error_handling import ErrorCategory, PhaseError, log_phase_error

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
            "SELECT date, COUNT(DISTINCT symbol) FROM price_daily WHERE date >= %s GROUP BY date ORDER BY date DESC LIMIT 7",
            (max_date - td(days=7),),
        )
        diag_rows = cur.fetchall()
        logger.critical(
            f"[PHASE 1 DIAGNOSTIC] max_date={max_date} recent_cutoff={phase1_recent_cutoff_days} "
            f"per-date distribution (last 7 days with data): {list(diag_rows)}"
        )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as diag_err:
        logger.warning(f"[PHASE 1 DIAGNOSTIC] failed to gather date distribution (DB error): {diag_err}")
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
