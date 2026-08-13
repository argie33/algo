#!/usr/bin/env python3
"""
Phase 1 Failsafe: Automatic Retry for Incomplete Loaders

Detects loaders that fail to meet their configured completion threshold and triggers
automatic retries to recover. This prevents cascading failures downstream due to incomplete data.

Strategy:
1. After initial Phase 1 freshness check passes, query data_loader_status
2. Find any loaders with INCOMPLETE status or completion_pct below their configured threshold
3. For each incomplete loader:
   - Log diagnostic info (how many symbols missing, last error, etc.)
   - Trigger a retry by starting the loader's ECS task (via algo-trigger-loaders,
     the same mechanism the regular schedule uses) - runs independently of this Lambda
   - Briefly poll status (up to RETRY_MONITOR_TIMEOUT_SECONDS) in case it finishes fast
   - If retry reaches the loader's minimum completion threshold within that window, mark as recovered and proceed
   - Otherwise mark as still incomplete for THIS run (halt if critical, warn if
     auxiliary) - the ECS task keeps running in the background and the next
     scheduled orchestrator run will see the completed data

Completion thresholds (configured per loader via loaders/config.py):
- price: 2% max_fail_rate → needs 98%+ completion
- sec, financial, earnings: 5% max_fail_rate → needs 95%+ completion
- others: varies by loader type
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import psycopg2
from botocore.exceptions import BotoCoreError, ClientError

from loaders.config import get_loader_max_fail_rate
from loaders.loader_registry import all_tables, normalize_loader_name
from loaders.loader_timeout_config import get_loader_timeouts
from utils.data_tiers import is_critical
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.status_manager import LoaderStatusManager

logger = logging.getLogger(__name__)


def _get_table_date_column(table_name: str) -> str | None:
    """Get the date/timestamp column name for a table.

    Different tables have different column naming conventions:
    - Most: 'date' (price_daily, technical_data_daily, etc.)
    - Symbol-based without date: no date column (use None)
    - Static reference tables: 'created_at' or 'updated_at'
    - SEC/Financial: 'report_date', 'filed_date', 'fiscal_date', or 'updated_at'

    CRITICAL SESSION 99 FIX: Many tables don't have a 'date' column, causing
    "column 'date' does not exist" errors in Phase 1. This mapping ensures
    each table's freshness is checked via its actual date column.

    Args:
        table_name: Name of the table

    Returns:
        Column name to use for freshness checks, or None if table doesn't track date
    """
    # Mapping of table names to their date/timestamp column names
    # Session 98 identified 14 tables failing with "column date does not exist"
    date_column_map = {
        # Price & market data (have 'date' column)
        "price_daily": "date",
        "price_weekly": "date",
        "price_monthly": "date",
        "etf_price_daily": "date",
        "etf_price_weekly": "date",
        "etf_price_monthly": "date",
        # Technical & signals (have 'date' column)
        "technical_data_daily": "date",
        "trend_template_data": "date",
        "buy_sell_daily": "date",
        "stock_scores": "updated_at",  # orchestrator output, updated via Phase 5
        "signal_quality_scores": "date",
        # Market metrics (have 'date' column)
        "market_health_daily": "date",
        "market_exposure_daily": "date",
        "market_sentiment": "date",
        "sector_ranking": "date",
        "sector_performance": "date",
        "industry_ranking": "date",
        "naaim": "date",
        "aaii": "date",
        "aaii_sentiment": "date",
        # These don't have 'date' or 'updated_at' - no temporal freshness check
        "earnings_calendar": "created_at",  # forward-looking announcements
        "earnings_calendar_sec": "created_at",  # SEC version
        # Company info & SEC data (use 'updated_at' for load recency)
        "company_info_sec": "updated_at",  # Session 98: fixed from 'date'
        "company_profile": "updated_at",  # yfinance-sourced, no date column
        "sec_valuations": "updated_at",  # SEC API queries, use update time
        "sec_segment_info": "updated_at",  # XBRL data, use update time
        "sec_segment_metrics": "updated_at",  # Computed metrics
        "sec_reports": "filed_date",  # 8-K/10-K/10-Q filing dates
        # Financial statements (no 'date' - multiple period types)
        "annual_income_statement": "updated_at",  # multi-year, one row per symbol
        "annual_balance_sheet": "updated_at",
        "annual_cash_flow": "updated_at",
        "quarterly_income_statement": "updated_at",
        "quarterly_balance_sheet": "updated_at",
        "quarterly_cash_flow": "updated_at",
        "ttm_income_statement": "updated_at",
        "ttm_cash_flow": "updated_at",
        # Dividend & fundamental data
        "dividend_data": "updated_at",  # yfinance-sourced, may be historical
        "sec_dividends": "updated_at",  # SEC filing data
        # Analyst data (use 'updated_at' for load recency)
        "analyst_sentiment_analysis": "updated_at",
        "analyst_upgrade_downgrade": "updated_at",  # yfinance-sourced
        "analyst_earnings_estimates": "updated_at",
        # Metrics & rankings (computed daily or updated on schedule)
        "value_metrics": "date",
        "quality_metrics": "date",
        "growth_metrics": "date",
        "momentum_metrics": "date",
        "positioning_metrics": "updated_at",  # 13F/short interest data
        "institutional_holdings_13f": "updated_at",
        "insider_holdings_sec": "updated_at",  # Form 4/5 filings
        "insider_transaction_velocity": "updated_at",
        "insider_velocity": "updated_at",
        "short_interest_finra": "updated_at",
        # Economic data
        "economic_data": "date",
        # Symbols/reference (use created_at for existence check)
        "stock_symbols": "created_at",
        "etf_symbols": "created_at",
        # Current reports
        "current_reports_8k": "filed_date",
    }

    return date_column_map.get(table_name)


def _mark_loader_failed_after_crash(loader_key: str, error_message: str) -> None:
    """Best-effort: mark every table a crashed/timed-out force-refresh subprocess owns as
    FAILED, matching scripts/local_loader_scheduler.py's identical fix for the same bug
    class (see that module's own _mark_loader_failed_after_crash docstring).

    run_loader.py --force-refresh marks its tables RUNNING before doing any real work
    (main()'s own "Mark loaders as RUNNING if force-refresh" step). If the subprocess is
    then killed by subprocess.run(timeout=300) or crashes with an uncaught exception before
    reaching its own terminal-status logic, that RUNNING row is never corrected here either -
    live-confirmed 2026-08-10: price_daily/etf_price_daily/price_monthly/price_weekly/
    etf_price_monthly/etf_price_weekly (load_prices.py's full output set) all stuck RUNNING
    from a failsafe-retry invocation whose subprocess died with no owning process left. Only
    reap_stale_running_loaders()'s later, coarser check would have ever caught this
    otherwise.

    Only touches tables still showing RUNNING - a non-zero exit can also mean the child's
    own run() already recorded a real terminal FAILED status (see run_loader.py's own
    force-refresh fix), which must not be clobbered. Safe to call unconditionally from every
    failure branch (non-zero exit, timeout, or a subprocess.run() call that couldn't even
    start) for exactly that reason. Deliberately swallows its own errors - a failure to
    record the failure must never mask the original timeout/crash already being logged by
    the caller.
    """
    try:
        loader_filename = normalize_loader_name(loader_key)
        for table in all_tables(loader_filename):
            status_mgr = LoaderStatusManager(table)
            current = status_mgr.get_status()
            if current and current.get("status") == "RUNNING":
                status_mgr.mark_failed(error_message)
    except Exception as mark_err:
        logger.warning(f"[PHASE 1 FAILSAFE LOCAL] Could not mark {loader_key} tables FAILED after crash: {mark_err}")


# Critical vs. auxiliary classification for retry decisions below comes from
# utils.data_tiers.is_critical() (backed by CRITICAL_DATA/AUXILIARY_DATA there) - this
# module previously duplicated that classification in two local sets
# (CRITICAL_INCOMPLETE_LOADERS/AUXILIARY_INCOMPLETE_LOADERS) that were never actually
# read by any retry logic here (is_critical(table_name) at the actual decision point
# below has always been the live source), had already drifted from data_tiers.py (e.g.
# listed a stale "economic_metrics_daily" name that has never matched the real loader's
# table_name, "economic_data"), and were only referenced by one test asserting their own
# static content. Removed 2026-07-21 (loader-review audit); see
# tests/integration/test_complete_aws_deployment.py::test_growth_metrics_marked_enrichment,
# repointed at the real utils.data_tiers.CRITICAL_DATA set.

# Time to wait before retrying. Retries now trigger an independent ECS task
# (see invoke_loader_retry) instead of making API calls in-process, so there's
# no in-process throttling to wait out - this is just a brief settling delay.
RETRY_WAIT_SECONDS = 5

# Timeout for monitoring retry (how long THIS phase blocks waiting to see if the
# retry already completed, before giving up and letting the run proceed/halt on
# current data). Real loaders (positioning_metrics, value_metrics, etc.) can take
# 20-40 minutes on ECS - this Lambda cannot wait that long: its own configured
# timeout is 300s (terraform.tfvars algo_lambda_timeout) shared with phases 2,6,9
# which always run afterward. So this is a short best-effort poll, not a real wait
# for completion: invoke_loader_retry() already fired the ECS task asynchronously;
# if it doesn't finish within this window, status_reason="timeout" is returned,
# the loader is left "still_failing" for this run (existing halt_required handling
# applies), and the NEXT scheduled orchestrator run picks up the by-then-completed
# data. Multiple incomplete critical loaders are retried sequentially in the
# calling loop, so keep this window reasonable but not so small it times out before
# "quick" loaders (analyst_earnings: 20 min, small-to-medium loaders) have a chance.
# SESSION 93 CRITICAL FIX: Increased from 300s (5 min) to 1800s (30 min).
# The 5-minute timeout was causing a race condition in LOCAL_MODE:
# - Phase 1 starts subprocess with 30-min timeout
# - Monitors it for only 5 minutes, then gives up
# - Subprocess keeps running in background (still marked RUNNING in DB)
# - Phase 1's next data freshness check sees >5min RUNNING, marks as FAILED
# - Loader never actually completes because Phase 1 keeps failing it
# This affected: sec_valuations (20m), insider_holdings_sec (30m), sec_segment_info (30m).
# 30 minutes accommodates company_info_sec (120m is AWS-only; local subprocess 30m is safe).
RETRY_MONITOR_TIMEOUT_SECONDS = 1800


def _get_expected_data_date(run_date: _date | None = None, pipeline_context: str | None = None) -> tuple[_date, str]:
    """Calculate expected data date based on pipeline context and run_date.

    CRITICAL FIX (Session 54 PATCH 2): Accept pipeline_context from caller to avoid recalculating
    from system time (which is wrong when run_date != system date). When context is passed, use it
    directly. When None (AWS mode), recalculate from system time as fallback.

    Args:
        run_date: Orchestrator run_date. If None, uses system date (fallback for AWS Lambda mode).
        pipeline_context: One of "MORNING", "INTRADAY", or "EOD". If provided, use directly
                         instead of recalculating from system time.

    Returns:
        Tuple of (expected_data_date, freshness_context_str)
    """
    from datetime import timedelta as td

    from algo.infrastructure import MarketCalendar

    now_et = datetime.now(EASTERN_TZ)
    # Use orchestrator's run_date if provided, else system date
    run_date_et = run_date if run_date else now_et.date()

    # If pipeline_context provided, use it directly (avoids system time logic issues in LOCAL mode)
    # Otherwise, calculate from system time (fallback for AWS Lambda runs)
    if pipeline_context and pipeline_context in ("MORNING", "INTRADAY", "EOD"):
        is_intraday_context = pipeline_context in ("MORNING", "INTRADAY")
    else:
        # Fallback: calculate from system time
        is_intraday_context = now_et.hour < 16

    if is_intraday_context:
        # During market hours: expect previous trading day's data
        prev_date = run_date_et - td(days=1)
        expected_data_date = prev_date
        while expected_data_date > run_date_et - td(days=10):
            if MarketCalendar.is_trading_day(expected_data_date):
                break
            expected_data_date -= td(days=1)
        context = f"INTRADAY - expecting previous trading day ({expected_data_date})"
    else:
        # After market close: expect same-day or recent trading day's data
        if MarketCalendar.is_trading_day(run_date_et):
            expected_data_date = run_date_et
        else:
            expected_data_date = run_date_et - td(days=1)
            while expected_data_date > run_date_et - td(days=10):
                if MarketCalendar.is_trading_day(expected_data_date):
                    break
                expected_data_date -= td(days=1)
        context = f"EOD - expecting same/recent trading day ({expected_data_date})"

    return expected_data_date, context


def _check_and_refresh_local(  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
    run_date: _date | None = None, pipeline_context: str | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """In LOCAL_MODE, check for stale DATA and refresh loaders locally.

    Runs loaders directly using Python imports instead of AWS Lambda/ECS.
    Checks actual data freshness (MAX(date) in tables), not loader status timestamps.
    This catches cases where the loader ran recently but produced stale data.

    CRITICAL FIX 2026-08-12: Also checks for loaders marked FAILED and retries them,
    matching AWS mode behavior (Session 92 fix). Previously LOCAL mode only checked data
    freshness, so loaders that crashed (marked FAILED) but had recent data never got retried,
    causing Monday brittleness when Friday failures persisted.

    Uses MARKET-AWARE freshness checks (same logic as phase1_data_freshness.py):
    - During intraday (before 4 PM ET): previous trading day's data is CORRECT
    - After market close (4 PM+ ET): same-day data is CORRECT
    Does NOT use naive 24-hour checks which fail at market holidays/weekends.

    Args:
        run_date: Orchestrator run_date. If None, uses system date.
        pipeline_context: One of "MORNING", "INTRADAY", or "EOD" (passed from caller to avoid
                         system-time-based recalculation in LOCAL mode).
        dry_run: If True, don't actually run loaders, just report what would run

    Returns:
        Dict with refresh results (same format as AWS retry)
    """
    results: dict[str, Any] = {
        "incomplete_loaders": [],
        "retried": [],
        "recovered": [],
        "still_failing": [],
        "halt_required": False,
    }

    # CRITICAL FIX 2026-08-12: First pass - check for FAILED loaders and retry them
    # Loaders marked FAILED on Friday are ignored by Monday because they're not "stale" (data is recent)
    # but they DO need retry to recover from the crash/timeout that caused the FAILED status
    # SESSION 93 FIX: Also check TIMEOUT status (AWS mode handles it at line 815)
    failed_loaders_to_retry = []
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    table_name,
                    consecutive_failures,
                    error_message
                FROM data_loader_status
                WHERE UPPER(status) IN ('ERROR', 'FAILED', 'TIMEOUT')
                ORDER BY table_name
            """)
            failed_loaders = cur.fetchall()

            for table_name, consecutive_failures, error_msg in failed_loaders:
                logger.warning(
                    f"[PHASE 1 FAILSAFE LOCAL] Found FAILED loader (will retry): {table_name} "
                    f"(consecutive_failures={consecutive_failures}, error={error_msg[:60] if error_msg else 'none'})"
                )
                results["incomplete_loaders"].append(table_name)
                failed_loaders_to_retry.append(table_name)
    except Exception as e:
        logger.warning(
            f"[PHASE 1 FAILSAFE LOCAL] Could not check for FAILED loaders: {e}. Continuing with staleness checks."
        )

    # Critical loaders to refresh in local mode (table_name: loader_script_key)
    # SESSION 94 CRITICAL FIX: Add ALL Phase 1 critical loaders, not just hardcoded subset
    # Previously missed loaders: company_info_sec, dividend_data, sec_segment_info, company_profile, etc.
    # These weren't being checked at all → stayed FAILED indefinitely → cascaded Monday failures
    loaders_to_refresh = {
        # Core pricing
        "price_daily": "prices",
        "etf_price_daily": "prices",
        # Technical & signals
        "technical_data_daily": "technical",
        "stock_scores": "scores",
        "buy_sell_daily": "buy_sell",
        # Market data
        "market_health_daily": "market_status",
        "trend_template_data": "trend_analysis",
        # Earnings & calendar
        "earnings_calendar": "earnings_calendar",
        # SEC/Financial data (SESSION 94+ FIX: Correct table-name mismatches)
        "company_info_sec": "company_info",
        "company_profile": "profile",
        "sec_valuations": "valuations",
        # Financial statements - individual tables from financial_statements loader
        "annual_income_statement": "financial_statements",
        "annual_balance_sheet": "financial_statements",
        "annual_cash_flow": "financial_statements",
        "quarterly_income_statement": "financial_statements",
        "quarterly_balance_sheet": "financial_statements",
        "quarterly_cash_flow": "financial_statements",
        # Earnings SEC
        "earnings_calendar_sec": "earnings_sec",
        # Segment data - use actual table names
        "sec_segment_info": "segment_info",
        "sec_segment_metrics": "segment_metrics",
        # Dividends & fundamentals - use actual output table names
        "dividend_data": "dividends",
        "value_metrics": "value_quality_growth",
        "quality_metrics": "enhanced_quality_growth",
        # Analyst data - use actual table names
        "analyst_earnings_estimates": "analyst_earnings_estimates",
        "analyst_sentiment_analysis": "analyst_sentiment",
        "analyst_upgrade_downgrade": "analyst_upgrades",
        # Holdings & positioning
        "institutional_holdings_13f": "institutional",
        "insider_holdings_sec": "insider_holdings",
        "insider_transaction_velocity": "insider_velocity",
        "short_interest_finra": "short_interest",
        "positioning_metrics": "positioning",
        # Other critical tables
        "industry_ranking": "sector_industry",
    }

    try:
        # Check actual data freshness (MAX(date) in each table), not loader status
        # This catches when loader ran recently but data is stale
        stale_loaders = []

        # Market-aware freshness check: determine expected data date based on pipeline context + run_date
        # CRITICAL FIX (Session 54 PATCH 2): Pass pipeline_context to avoid recalculating from system time
        # When system date != run_date (LOCAL testing), using system time would give wrong expectations
        expected_data_date, freshness_context = _get_expected_data_date(
            run_date=run_date, pipeline_context=pipeline_context
        )
        logger.info(f"[PHASE 1 FAILSAFE LOCAL] {freshness_context}")

        def _check_data_completeness(table_name: str, check_date: _date) -> tuple[bool, str]:
            """Check if table has sufficient data completeness (95%+ non-NULL in critical column).

            Args:
                check_date: The date to check completeness for - the table's own actual latest
                    date (table_max_date from the staleness check above), NOT necessarily
                    expected_data_date. For stock_scores/earnings_calendar, which track
                    freshness via updated_at (a loader-run timestamp, not a trading-day
                    column), these are only the same value when the loader happens to run
                    exactly on expected_data_date - which the staleness check above already
                    established is NOT required (updated_at from a same-day-or-later refresh
                    correctly reads as "not stale", since it's ahead of, not behind, the
                    expected historical trading day). Bug found 2026-08-10 (live-reproduced
                    on every MORNING/INTRADAY orchestrator run today): this used to always
                    check against expected_data_date regardless, so a same-day stock_scores
                    refresh's updated_at (today) could never match expected_data_date
                    (yesterday) - COUNT(*) for that date was always 0, permanently reporting
                    "No rows for {expected_data_date}" and re-triggering a full stock_scores
                    reload on every single intraday run, even seconds after a fresh,
                    successful, 100%-complete refresh.

            Returns: (is_complete, reason_if_incomplete)
            """
            if table_name == "stock_scores":
                # stock_scores: check that symbol column is non-NULL (composite_score can be NULL for unavailable stocks)
                critical_col = "symbol"
            elif table_name in ("price_daily", "etf_price_daily"):
                # price_daily/etf_price_daily: check close price is populated (same schema)
                critical_col = "close"
            elif table_name == "technical_data_daily":
                # technical_data_daily: check rsi_14 (core technical indicator)
                critical_col = "rsi_14"
            elif table_name == "buy_sell_daily":
                # buy_sell_daily: check signal_type is populated
                critical_col = "signal_type"
            elif table_name == "market_health_daily":
                # market_health_daily: check vix_level is populated
                critical_col = "vix_level"
            elif table_name == "trend_template_data":
                # trend_template_data: check trend_direction is populated (key field for regime detection)
                critical_col = "trend_direction"
            elif table_name == "earnings_calendar":
                # earnings_calendar: check earnings_date is populated (gates earnings_blackout entry blocking)
                critical_col = "earnings_date"
            else:
                return True, ""  # Unknown table, skip completeness check

            try:
                # stock_scores doesn't have a date column, use updated_at instead
                if table_name == "stock_scores":
                    date_filter = "updated_at::date = %s"
                    params: tuple[Any, ...] = (check_date,)
                # trend_template_data: check only today's data by date column, not by created_at
                # (created_at fallback included old backfilled data, making completeness check too strict)
                elif table_name == "trend_template_data":
                    date_filter = "date = %s"
                    params = (check_date,)
                # earnings_calendar: uses updated_at to track loader freshness (not earnings_date, which is forward-looking)
                elif table_name == "earnings_calendar":
                    date_filter = "updated_at::date = %s"
                    params = (check_date,)
                else:
                    date_filter = "date = %s OR updated_at::date = %s"
                    params = (check_date, check_date)

                # Technical_data_daily validation requires multiple indicators, not just one.
                # Session 81: Partial loads were missed before when a loader crash wrote RSI-14
                # but crashed before writing ATR, SMA, etc. Phase 8 uses ATR for position sizing,
                # so sparse technical_data causes entry failures later. Validate all 4 required
                # indicators are present for 95%+ of symbols.
                if table_name == "technical_data_daily":
                    cur.execute(
                        f"""
                        SELECT
                            COUNT(*) as total_rows,
                            COUNT(rsi_14) as rsi_count,
                            COUNT(atr_14) as atr_count,
                            COUNT(sma_50) as sma_count,
                            COUNT(bb_upper) as bb_count
                        FROM {table_name}
                        WHERE {date_filter}
                    """,
                        params,
                    )
                    row = cur.fetchone()
                    if not row or row[0] == 0:
                        return False, f"No rows for {check_date}"
                    total, rsi_count, atr_count, sma_count, bb_count = row
                    # All 4 indicators should be present in >= 95% of rows
                    indicator_pcts = [
                        (rsi_count / total * 100) if total > 0 else 0,
                        (atr_count / total * 100) if total > 0 else 0,
                        (sma_count / total * 100) if total > 0 else 0,
                        (bb_count / total * 100) if total > 0 else 0,
                    ]
                    min_indicator_pct = min(indicator_pcts)
                    if min_indicator_pct < 95.0:
                        return (
                            False,
                            f"Technical indicators incomplete: RSI {indicator_pcts[0]:.0f}%, ATR {indicator_pcts[1]:.0f}%, SMA {indicator_pcts[2]:.0f}%, BB {indicator_pcts[3]:.0f}% (need 95%+)",
                        )
                    return True, ""

                cur.execute(
                    f"""
                    SELECT
                        COUNT(*) as total_rows,
                        COUNT({critical_col}) as non_null_rows
                    FROM {table_name}
                    WHERE {date_filter}
                """,
                    params,
                )

                row = cur.fetchone()
                if not row or row[0] == 0:
                    return False, f"No rows for {check_date}"

                total, non_null = row[0], row[1]
                completeness_pct = (non_null / total * 100) if total > 0 else 0

                min_completeness = 92.0 if table_name == "trend_template_data" else 95.0
                if completeness_pct < min_completeness:
                    return (
                        False,
                        f"Completeness {completeness_pct:.1f}% (need {min_completeness}%+ of {critical_col} non-NULL)",
                    )
                return True, ""
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                # This is a failsafe retry helper: its whole job is deciding whether a table
                # needs a refresh. Treating a completeness-check failure as "complete" silently
                # skips a table we couldn't actually verify - the same fail-open-and-fabricate
                # shape this codebase's governance rules forbid elsewhere. Fail closed instead:
                # an unverifiable table is treated as incomplete, so it gets refreshed (cheap)
                # rather than possibly staying silently sparse (expensive/invisible).
                logger.warning(
                    f"[PHASE 1 FAILSAFE LOCAL] Could not check completeness for {table_name} (DB error): {e}. Treating as incomplete."
                )
                return False, f"Completeness check failed (DB error): {e}"
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(
                    f"[PHASE 1 FAILSAFE LOCAL] Could not check completeness for {table_name} (data error): {e}. Treating as incomplete."
                )
                return False, f"Completeness check failed (data error): {e}"

        for table_name, loader_key in loaders_to_refresh.items():
            # CRITICAL FIX (Session 96): Create new DatabaseContext for EACH table
            # Bug: Single context for entire loop caused transaction abort cascade
            # When one table's query failed (e.g., company_info_sec), ALL subsequent
            # queries in same transaction failed with "InFailedSqlTransaction"
            # Fix: Isolate each table's check in its own transaction
            with DatabaseContext("read") as cur:
                try:
                    # SESSION 99 FIX: Use proper date column for each table (14 tables had "column date does not exist")
                    date_col = _get_table_date_column(table_name)
                    if date_col is None:
                        # Table has no date column - skip freshness check
                        logger.info(
                            f"[PHASE 1 FAILSAFE LOCAL] {table_name} has no date column - skipping freshness check"
                        )
                        continue

                    # Type guard: date_col is now guaranteed str (not None)
                    cur.execute(f"SELECT MAX({date_col}) FROM {table_name}")

                    row = cur.fetchone()
                    if row and row[0]:
                        max_date = row[0]
                        # Convert date/datetime to date for comparison
                        from datetime import date as date_type

                        if isinstance(max_date, date_type) and not isinstance(max_date, datetime):
                            table_max_date = max_date
                        elif isinstance(max_date, datetime):
                            table_max_date = max_date.date()
                        else:
                            logger.warning(
                                f"[PHASE 1 FAILSAFE LOCAL] Unexpected date type for {table_name}: {type(max_date)}"
                            )
                            continue

                        # Market-aware staleness check: allow up to 10 days behind (covers weekends/holidays)
                        # Don't use naive hours checks which fail at multi-day gaps
                        days_behind = (expected_data_date - table_max_date).days
                        is_stale = days_behind > 0  # Stale if behind expected date

                        if is_stale:
                            stale_loaders.append((table_name, loader_key, days_behind))
                            results["incomplete_loaders"].append(table_name)
                            logger.warning(
                                f"[PHASE 1 FAILSAFE LOCAL] {table_name} data stale: "
                                f"{table_max_date} vs expected {expected_data_date} "
                                f"({days_behind} day(s) behind)"
                            )
                        else:
                            # CRITICAL: Also check data completeness (not just date freshness)
                            # A table can have MAX(date)=today but be 95% NULL values
                            is_complete, incomplete_reason = _check_data_completeness(table_name, table_max_date)
                            if not is_complete:
                                stale_loaders.append((table_name, loader_key, 0))
                                results["incomplete_loaders"].append(table_name)
                                logger.warning(
                                    f"[PHASE 1 FAILSAFE LOCAL] {table_name} data sparse despite fresh date: {incomplete_reason}. "
                                    f"Loader may have completed with insufficient data quality. Triggering refresh."
                                )
                            else:
                                logger.info(
                                    f"[PHASE 1 FAILSAFE LOCAL] {table_name} fresh and complete: {table_max_date}"
                                )
                    else:
                        # No data at all
                        stale_loaders.append((table_name, loader_key, 999))
                        results["incomplete_loaders"].append(table_name)
                        logger.warning(f"[PHASE 1 FAILSAFE LOCAL] {table_name} has no data")

                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.warning(f"[PHASE 1 FAILSAFE LOCAL] Could not check {table_name} (DB error): {e}")
                except (KeyError, ValueError, TypeError, AttributeError) as e:
                    logger.warning(f"[PHASE 1 FAILSAFE LOCAL] Could not check {table_name} (data error): {e}")

        # Combine FAILED loaders with stale loaders for retry
        # Map table names to loader keys - use registry for comprehensive mapping
        from loaders.loader_registry import table_to_loader_shorthand

        table_to_loader_key = dict(loaders_to_refresh)
        all_loaders_to_retry = []

        # Add FAILED loaders - use registry to find ANY loader, not just hardcoded ones
        for table_name in failed_loaders_to_retry:
            key_for_failed: str | None = table_to_loader_key.get(table_name)
            # If not in hardcoded dict, try dynamic lookup from registry
            if not key_for_failed:
                key_for_failed = table_to_loader_shorthand(table_name)

            if key_for_failed:
                all_loaders_to_retry.append((table_name, key_for_failed, 0))  # age=0 for FAILED
                logger.info(f"[PHASE 1 FAILSAFE LOCAL] FAILED loader {table_name} → {key_for_failed}")
            else:
                logger.warning(
                    f"[PHASE 1 FAILSAFE LOCAL] FAILED loader {table_name} not found in registry - cannot retry"
                )

        # Add stale loaders
        all_loaders_to_retry.extend(stale_loaders)

        if not all_loaders_to_retry:
            logger.info("[PHASE 1 FAILSAFE LOCAL] All data current - no refresh needed")
            return results

        logger.info(
            f"[PHASE 1 FAILSAFE LOCAL] Found {len(failed_loaders_to_retry)} FAILED + {len(stale_loaders)} stale loaders to refresh"
        )

        if dry_run:
            all_names = [t[0] for t in all_loaders_to_retry]
            logger.info(f"[PHASE 1 FAILSAFE LOCAL] DRY RUN: Would refresh {all_names}")
            return results

        # CRITICAL FIX (SESSION 94): Import centralized timeout config to prevent mismatch-brittleness
        # SESSION 93 root cause: local_loader_scheduler had 75m for earnings_calendar while
        # phase1 retry had 45m, causing Friday timeouts to never recover by Monday. Now
        # both import from single source of truth (loaders/loader_timeout_config.py)

        # Run each loader (FAILED or stale) locally
        for table_name, loader_key, age_in_days in all_loaders_to_retry:
            try:
                if age_in_days == 0 and table_name in failed_loaders_to_retry:
                    logger.info(f"[PHASE 1 FAILSAFE LOCAL] Retrying FAILED loader: {table_name}")
                else:
                    logger.info(
                        f"[PHASE 1 FAILSAFE LOCAL] Refreshing stale {table_name} ({age_in_days:.0f} day(s) old)"
                    )
                results["retried"].append(table_name)

                # Run loader with force-refresh to bypass watermarks

                env = os.environ.copy()
                env["TECH_FULL_REFRESH"] = "true"  # Bypass watermark filters (read by technical_data_daily)

                # CRITICAL FIX (Session 54): Pass run_date to loader so it respects orchestrator's date, not system date
                # When orchestrator runs for 2026-08-12 but system date is 2026-08-08 (Saturday),
                # loader needs run_date to know which trading day data to expect
                from datetime import date as _date_class

                run_date_str = run_date.isoformat() if run_date else _date_class.today().isoformat()
                env["ORCHESTRATOR_RUN_DATE"] = run_date_str

                # BUG FOUND 2026-08-10: this used to invoke `scripts/run_loader.py {loader_key}
                # --force-refresh` - the exact "generic path bypasses main()" bug class
                # scripts/local_loader_scheduler.py was already rearchitected away from earlier
                # the same session ("ROOT-CAUSE FIX 2026-08-10: always invoke the loader module
                # directly... never scripts/run_loader.py's generic path" - see that module's
                # own comment, which names "prices" by name among the loaders whose main()-only
                # logic silently never ran through the generic path). run_loader.py's generic
                # dispatch imports the loader CLASS and calls `PriceLoader().run()` with default
                # constructor args (interval="1d", asset_class="stock") - it never reaches
                # load_prices.py's own main(), which is the ONLY code path that loops over all
                # 6 asset_class x interval combos (price_daily/weekly/monthly, etf_price_daily/
                # weekly/monthly). Live-reproduced: a "prices" refresh via the old path exited 0
                # ("refreshed successfully") while price_weekly/price_monthly/etf_price_daily/
                # etf_price_weekly/etf_price_monthly were ALL marked FAILED at 0.00% completion
                # (0/N symbols) - only price_daily (the one table matching the default
                # constructor args) ever actually loaded. This meant Phase 1's OWN self-healing
                # mechanism could never actually recover etf_price_daily even after correctly
                # detecting it as stale - every retry would silently "succeed" while leaving the
                # real data untouched. Fixed identically to local_loader_scheduler.py: invoke
                # `python loaders/{file}.py` directly so every loader's real production
                # entrypoint runs locally too, with no generic path left to diverge from it.
                loader_filename = normalize_loader_name(loader_key)
                if loader_key == "financial_statements":
                    # Matches local_loader_scheduler.py's identical special case: main() fans
                    # LOADER_STATEMENT_TYPE="all" out to all 6 statement/period combos; the
                    # class constructor alone requires one specific combo to already be named.
                    env["LOADER_STATEMENT_TYPE"] = "all"
                # SESSION 94 CRITICAL FIX: Run loader IN-PROCESS instead of subprocess
                # to eliminate file lock contention from concurrent execution.
                # Previously, subprocess would fail acquiring locks within ~96s even with
                # 120+ minute timeouts configured, causing cascading failures.
                # Now runs directly, inheriting parent orchestrator's lock context.
                # CRITICAL (SESSION 96): Use correct per-loader timeout from centralized config.
                # Raise immediately if loader not registered - silent fallback to 60min default
                # was truncating 180min loaders (company_info_sec).
                timeouts = get_loader_timeouts()
                if loader_key not in timeouts:
                    raise RuntimeError(
                        f"[PHASE 1 FAILSAFE] Loader {table_name} ({loader_key}) not registered in "
                        f"loaders/loader_timeout_config.py. This is a configuration error. "
                        f"Registered loaders: {sorted(timeouts.keys())}"
                    )
                loader_timeout = timeouts[loader_key]
                env["LOADER_TIMEOUT"] = str(max(1, loader_timeout))

                # Set environment for this loader run
                old_env = os.environ.copy()
                for key, value in env.items():
                    os.environ[key] = value

                try:
                    # Import and instantiate the loader class dynamically
                    # Use importlib to dynamically load the module and find the loader class
                    # This approach (from run_loader.py) is more robust than CamelCase guessing
                    import importlib

                    module_name = (
                        loader_filename.replace(".py", "") if loader_filename.endswith(".py") else loader_filename
                    )
                    loader_module = importlib.import_module(f"loaders.{module_name}")

                    # Find the loader class in the module (handles edge cases like CurrentReports8KLoader)
                    # First try to find any OptimalLoader subclass (primary pattern)
                    from utils.optimal_loader import OptimalLoader

                    loader_class = None
                    for attr_name in dir(loader_module):
                        obj = getattr(loader_module, attr_name)
                        if isinstance(obj, type) and issubclass(obj, OptimalLoader) and obj is not OptimalLoader:
                            loader_class = obj
                            break

                    # Fallback: if no OptimalLoader found, look for any class that looks like a loader
                    # (e.g., VectorizedTechnicalLoader, legacy loaders that predate OptimalLoader, SecLoaderBase subclasses)
                    if loader_class is None:
                        for attr_name in dir(loader_module):
                            obj = getattr(loader_module, attr_name)
                            if isinstance(obj, type) and "Loader" in attr_name and obj.__module__.startswith("loaders"):
                                loader_class = obj
                                logger.info(f"[PHASE 1 FAILSAFE LOCAL] Using fallback loader class: {attr_name}")
                                break

                    if loader_class is None:
                        raise RuntimeError(
                            f"Could not find any Loader subclass in loaders.{module_name}. "
                            f"Check that the loader file contains a proper Loader class."
                        )

                    # Direct instantiation
                    loader = loader_class()
                    result_status = loader.run([])  # Run for full universe
                    returncode = 0 if result_status else 1

                except Exception as e:
                    logger.error(
                        f"[PHASE 1 FAILSAFE LOCAL] {table_name} in-process run FAILED: {type(e).__name__}: {e}",
                        exc_info=True,
                    )
                    returncode = 1
                finally:
                    # Restore environment
                    os.environ.clear()
                    os.environ.update(old_env)

                # Now check the results (after environment restored)
                if returncode == 0:
                    # BUG FOUND 2026-08-10: exit code 0 only means the subprocess didn't
                    # crash - it says nothing about whether THIS SPECIFIC table's own load
                    # actually succeeded. Live-reproduced: a "prices" refresh exited 0 (the
                    # loader ran to completion without an uncaught exception) while
                    # etf_price_daily itself was marked FAILED at 0.00% completion by its own
                    # internal safety check (see the main()-bypass fix above) - reporting this
                    # as "refreshed successfully"/"recovered" would have been the same
                    # fail-open-and-fabricate-success shape this codebase's governance rules
                    # forbid elsewhere. Re-check the table's own terminal status before
                    # trusting the subprocess's exit code.
                    post_status = LoaderStatusManager(table_name).get_status()
                    if post_status and post_status.get("status") == "COMPLETED":
                        logger.info(f"[PHASE 1 FAILSAFE LOCAL] {table_name} refreshed successfully")
                        results["recovered"].append(table_name)
                    else:
                        actual_status = post_status.get("status") if post_status else "MISSING"
                        logger.error(
                            f"[PHASE 1 FAILSAFE LOCAL] {table_name} refresh in-process returned success but the "
                            f"table's own status is '{actual_status}', not COMPLETED (completion_pct="
                            f"{post_status.get('completion_pct') if post_status else 'N/A'}, error="
                            f"{post_status.get('error_message') if post_status else 'N/A'}). Not "
                            f"reporting as recovered."
                        )
                        results["still_failing"].append(table_name)
                        # SESSION 106 FIX: Add buy_sell_daily to critical deps - Phase 1 halts on stale buy_sell_daily
                        if table_name in {"price_daily", "technical_data_daily", "stock_scores", "buy_sell_daily"}:
                            results["halt_required"] = True
                else:
                    logger.error(
                        f"[PHASE 1 FAILSAFE LOCAL] {table_name} refresh FAILED (in-process execution returned non-zero). "
                        f"Loader: {loader_filename} ({loader_key}). Check logs above for details."
                    )
                    results["still_failing"].append(table_name)
                    _mark_loader_failed_after_crash(
                        loader_key, f"failsafe retry in-process execution failed (returncode={returncode})"
                    )
                    # SESSION 106 FIX: Add buy_sell_daily to critical deps
                    if table_name in {"price_daily", "technical_data_daily", "stock_scores", "buy_sell_daily"}:
                        results["halt_required"] = True

            except (OSError, RuntimeError) as e:
                logger.error(f"[PHASE 1 FAILSAFE LOCAL] Error refreshing {table_name} (execution error): {e}")
                results["still_failing"].append(table_name)
                _mark_loader_failed_after_crash(loader_key, f"failsafe retry execution error: {type(e).__name__}: {e}")
                # SESSION 106 FIX: Add buy_sell_daily to critical deps
                if table_name in {"price_daily", "technical_data_daily", "stock_scores", "buy_sell_daily"}:
                    results["halt_required"] = True
            except Exception as e:
                logger.error(f"[PHASE 1 FAILSAFE LOCAL] Unexpected error refreshing {table_name}: {e}")
                results["still_failing"].append(table_name)
                _mark_loader_failed_after_crash(loader_key, f"failsafe retry unexpected error: {type(e).__name__}: {e}")
                # SESSION 106 FIX: Add buy_sell_daily to critical deps
                if table_name in {"price_daily", "technical_data_daily", "stock_scores", "buy_sell_daily"}:
                    results["halt_required"] = True

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[PHASE 1 FAILSAFE LOCAL] Fatal database error in local refresh: {e}", exc_info=True)
        results["halt_required"] = True
    except Exception as e:
        logger.error(f"[PHASE 1 FAILSAFE LOCAL] Fatal error in local refresh: {e}", exc_info=True)
        results["halt_required"] = True

    return results


def check_and_retry_incomplete_loaders(  # noqa: C901
    run_date: _date | None = None, pipeline_context: str | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """Check for incomplete loaders and retry them.

    Args:
        run_date: Orchestrator run_date. If None, uses system date.
        pipeline_context: One of "MORNING", "INTRADAY", or "EOD". If provided, passed to
                         failsafe retry to avoid system-time-based recalculation in LOCAL mode.
        dry_run: If True, don't actually retry, just report what would be retried

    Returns:
        Dict with retry results:
        {
            "incomplete_loaders": [...],  # Loaders that were incomplete
            "retried": [...],              # Loaders that were retried
            "recovered": [...],            # Loaders that recovered successfully
            "still_failing": [...],        # Loaders that still failed after retry
            "halt_required": bool,         # True if critical loaders still failing
        }
    """
    results: dict[str, Any] = {
        "incomplete_loaders": [],
        "retried": [],
        "recovered": [],
        "still_failing": [],
        "halt_required": False,
    }

    # DEBUG: Log the parameters received
    logger.info(
        f"[PHASE 1 FAILSAFE DEBUG] check_and_retry_incomplete_loaders called with run_date={run_date}, pipeline_context={pipeline_context}"
    )

    # In LOCAL_MODE: run loaders locally instead of via AWS Lambda/ECS
    if os.getenv("LOCAL_MODE", "").lower() in ("1", "true", "yes"):
        logger.info("[PHASE 1 FAILSAFE] LOCAL_MODE enabled - triggering local loader refresh for stale data")
        results = _check_and_refresh_local(run_date=run_date, pipeline_context=pipeline_context, dry_run=dry_run)

        # SESSION 104 CRITICAL FIX: Add stall detection monitoring for LOCAL_MODE loaders
        # SESSION 106 ENHANCED: Now catches loaders stuck at ANY point, not just <5min old
        # _check_and_refresh_local() runs loaders and returns immediately, bypassing monitor_loader_retry()
        # which contains stall detection. Without this post-execution check, loaders stuck at 0% for 26+ hours
        # are never detected as stalled. Check for incomplete RUNNING loaders (0% for ANY duration) and mark them.
        try:
            with DatabaseContext("read") as cur:
                # SESSION 106 CRITICAL FIX: Detect RUNNING loaders at 0% regardless of last_updated age
                # Changed from "last_updated < 5min ago" to "execution_started exists" (has been running)
                # This catches loaders stuck at 0% for 5min, 30min, or even if somehow not updated since start
                cur.execute("""
                    SELECT table_name, completion_pct, execution_started, last_updated
                    FROM data_loader_status
                    WHERE UPPER(status) = 'RUNNING' AND completion_pct <= 0.0
                    AND execution_started IS NOT NULL
                """)
                stalled_loaders = cur.fetchall()

                for table_name, _completion_pct, execution_started, _last_updated in stalled_loaders:
                    stalled_duration = (
                        (datetime.now(timezone.utc) - execution_started.replace(tzinfo=timezone.utc)).total_seconds()
                        if execution_started
                        else 0
                    )
                    # SESSION 106 FIX: Only fail if stuck for >2 minutes (allow brief startup time)
                    # Loaders may take 1-2 min to initialize before first completion update
                    if stalled_duration > 120:
                        logger.critical(
                            f"[PHASE 1 FAILSAFE LOCAL] Loader stalled post-execution: {table_name} at 0% for {int(stalled_duration)}s. "
                            f"Marking FAILED to prevent Monday cascade."
                        )
                        try:
                            LoaderStatusManager(table_name).mark_failed(
                                f"[PHASE 1 FAILSAFE LOCAL] Loader stalled at 0% completion for {int(stalled_duration)}s (started {execution_started}). "
                                f"Subprocess likely hung or deadlocked."
                            )
                        except Exception as e:
                            logger.error(f"[PHASE 1 FAILSAFE LOCAL] Could not mark {table_name} FAILED: {e}")

                        # Mark as still failing in results so Phase 1 can halt if critical
                        if table_name not in results.get("still_failing", []):
                            results["still_failing"].append(table_name)
                            if is_critical(table_name):
                                results["halt_required"] = True
        except Exception as e:
            logger.warning(f"[PHASE 1 FAILSAFE LOCAL] Could not check for stalled loaders post-execution: {e}")

        return results

    try:
        with DatabaseContext("read") as cur:
            # Find loaders with low completion or error/failed status in the last 1 hour.
            # Query uses a conservative 85% threshold to catch any potentially problematic loader,
            # then Python code checks each against its configured max_fail_rate.
            # data_loader_status.status is written by multiple sources that don't share one
            # casing convention - utils/loader_infrastructure.py's update_loader_status()
            # writes canonical uppercase (RUNNING/COMPLETED/FAILED per utils/loaders/
            # status_enum.py), while other writers still use lowercase ("error"/"failed").
            # A plain `status IN ('error', 'failed')` only matches the lowercase writers -
            # any loader reporting canonical "FAILED" would be invisible to this OR clause
            # and only caught via the completion_pct threshold, silently narrowing failsafe
            # retry coverage. Compare case-insensitively so both vocabularies are caught.
            #
            # SESSION 100 FIX: Changed hardcoded 98% to 85% to match actual max_fail_rate configs.
            # Price loaders have max_fail_rate=5% (need 95% minimum, not 98%).
            # Query threshold 85% is conservative - it catches everything. Python-side validation
            # (line 987-1000) filters each against its configured max_fail_rate. This prevents
            # brittleness from query threshold drifting away from config changes.
            #
            # CRITICAL FIX 2026-08-12: Remove 1-hour window for explicitly FAILED loaders.
            # Loaders that fail on Friday were ignored by Monday because last_updated was
            # > 1 hour old. FAILED loaders should ALWAYS be retried regardless of age,
            # because they represent explicit failures needing recovery. Only incomplete
            # loaders (low completion_pct) are time-gated to avoid hammering ancient runs.
            #
            # CRITICAL FIX 2026-08-13: Include NOT_STARTED status in retry list.
            # NOT_STARTED status with an old execution_started timestamp indicates the
            # subprocess crashed before mark_running() was called (e.g., buy_sell_daily
            # stuck at NOT_STARTED for 34 hours). Must be retried immediately like FAILED.
            cur.execute("""
                SELECT
                    table_name,
                    status,
                    completion_pct,
                    symbols_loaded,
                    symbol_count,
                    error_message,
                    execution_started,
                    last_updated
                FROM data_loader_status
                WHERE (
                    UPPER(status) IN ('ERROR', 'FAILED', 'TIMEOUT', 'NOT_STARTED')  -- NOT_STARTED indicates crashed subprocess before mark_running()
                    OR (completion_pct < 85.0 AND last_updated >= CURRENT_TIMESTAMP - INTERVAL '1 hour')  -- Incomplete only if recent
                )
                ORDER BY completion_pct ASC, table_name
            """)

            incomplete_rows = cur.fetchall()

            for (
                table_name,
                _status,
                completion_pct,
                symbols_loaded,
                symbol_count,
                error_msg,
                _exec_started,
                _last_updated,
            ) in incomplete_rows:
                is_crit = is_critical(table_name)

                # CRITICAL FIX 2026-08-13: Log NOT_STARTED loaders with high completion_pct
                # This is a smoking gun for subprocess crash before mark_running() was called.
                # Completion_pct may show high value (from previous run) but status is NOT_STARTED
                # indicating this run's process never initialized. Must retry immediately.
                if _status and _status.upper() == "NOT_STARTED" and completion_pct and completion_pct > 50:
                    logger.warning(
                        f"[PHASE 1 FAILSAFE] CRITICAL SYMPTOM: {table_name} status=NOT_STARTED "
                        f"but completion_pct={completion_pct:.1f}% (subprocess likely crashed before mark_running). "
                        f"Forcing retry to recover."
                    )

                # Fail-fast if symbol counts are invalid for CRITICAL loaders only.
                # Non-critical loaders (aaii_sentiment, analyst_sentiment, etc.) may not track
                # symbol counts and should just be skipped/warned, not halted.
                if symbol_count is None:
                    if is_crit:
                        raise ValueError(
                            f"[PHASE 1 FAILSAFE] CRITICAL Loader {table_name}: symbol_count is NULL. "
                            "Cannot proceed with critical data. Data integrity issue."
                        )
                    else:
                        logger.debug(
                            f"[PHASE 1 FAILSAFE] Non-critical loader {table_name}: symbol_count is NULL, skipping"
                        )
                        continue

                if symbols_loaded is None:
                    if is_crit:
                        raise ValueError(
                            f"[PHASE 1 FAILSAFE] CRITICAL Loader {table_name}: symbols_loaded is NULL. "
                            "Data integrity issue."
                        )
                    else:
                        logger.debug(
                            f"[PHASE 1 FAILSAFE] Non-critical loader {table_name}: symbols_loaded is NULL, skipping"
                        )
                        continue

                symbols_missing = symbol_count - symbols_loaded

                if completion_pct is None:
                    logger.warning(
                        f"[PHASE 1 FAILSAFE] Incomplete loader detected: {table_name} "
                        f"status unknown ({symbols_loaded}/{symbol_count} symbols, {symbols_missing} missing) - loader may still be running"
                    )
                else:
                    logger.warning(
                        f"[PHASE 1 FAILSAFE] Incomplete loader detected: {table_name} "
                        f"{completion_pct:.1f}% ({symbols_loaded}/{symbol_count} symbols, {symbols_missing} missing)"
                    )

                # Check if this loader is actually below its configured threshold
                # (vs just being caught by the conservative query threshold)
                is_below_configured_threshold = False
                if completion_pct is not None:
                    max_fail_rate = get_loader_max_fail_rate(table_name)
                    min_completion_pct = 100.0 - max_fail_rate
                    is_below_configured_threshold = completion_pct < min_completion_pct
                    if (
                        not is_below_configured_threshold
                        and _status
                        and "FAILED" not in _status.upper()
                        and "ERROR" not in _status.upper()
                    ):
                        # Loader is above its configured threshold and has no error status - skip retry
                        logger.debug(
                            f"[PHASE 1 FAILSAFE] {table_name} {completion_pct:.1f}% is above configured minimum ({min_completion_pct:.0f}%) - no retry needed"
                        )
                        continue

                results["incomplete_loaders"].append(
                    {
                        "loader": table_name,
                        "completion_pct": completion_pct,  # Preserve NULL (unknown) vs 0 (failed)
                        "symbols_missing": symbols_missing,
                        "error": error_msg[:500] if error_msg else None,
                        "is_critical": is_crit,
                    }
                )

                if not dry_run:
                    # Only retry CRITICAL loaders. AUXILIARY loaders are nice-to-have;
                    # don't spend time retrying them since they don't block trading.
                    if not is_crit:
                        logger.warning(
                            f"[PHASE 1 FAILSAFE] AUXILIARY LOADER INCOMPLETE: {table_name} "
                            f"{completion_pct:.1f}% ({symbols_missing} missing). "
                            f"No retry attempted-auxiliary enrichment data is optional. "
                            f"Stock scores will reflect missing data via data_unavailable flags. "
                            f"This is correct behavior per GOVERNANCE (explicit unavailability markers)."
                        )
                        results["still_failing"].append(table_name)
                        continue

                    # Trigger retry - may raise RuntimeError or TimeoutError on failure
                    try:
                        retry_result = retry_loader(table_name, symbols_missing, is_crit)

                        if retry_result["retried"]:
                            results["retried"].append(table_name)

                            if retry_result["recovered"]:
                                results["recovered"].append(table_name)
                                final_pct = retry_result.get("final_completion_pct")
                                pct_str = f"{final_pct:.1f}%" if final_pct is not None else "unknown"
                                logger.info(f"[PHASE 1 FAILSAFE] Loader recovered: {table_name} -> {pct_str}")
                            else:
                                results["still_failing"].append(table_name)
                                final_pct = retry_result.get("final_completion_pct")
                                pct_str = f"{final_pct:.1f}%" if final_pct is not None else "unknown"

                                if "status_reason" not in retry_result or retry_result["status_reason"] is None:
                                    logger.critical(
                                        f"[PHASE 1 FAILSAFE CRITICAL] Loader retry result missing 'status_reason'. "
                                        f"Cannot determine why retry failed. Result keys: {list(retry_result.keys())}. "
                                        f"Loader retry infrastructure broken. Check invoke_loader_retry() implementation."
                                    )
                                    raise RuntimeError(
                                        "[PHASE 1] Loader retry result incomplete - missing 'status_reason' field. "
                                        "Cannot safely evaluate retry outcome."
                                    )

                                status_reason = retry_result["status_reason"]
                                if status_reason not in ("timeout", "failed"):
                                    logger.critical(
                                        f"[PHASE 1 FAILSAFE CRITICAL] Loader retry result has unexpected status_reason: {status_reason!r}. "
                                        f"Expected 'timeout' or 'failed'. Result keys: {list(retry_result.keys())}. "
                                        f"Loader retry infrastructure may have changed. Check invoke_loader_retry() implementation."
                                    )
                                    raise ValueError(
                                        f"[PHASE 1] Loader retry result has unexpected status_reason: {status_reason!r}. "
                                        "Expected 'timeout' or 'failed'."
                                    )

                                if status_reason == "timeout":
                                    reason_msg = (
                                        f"not yet confirmed recovered after {RETRY_MONITOR_TIMEOUT_SECONDS}s poll "
                                        "(ECS task still running in background - next scheduled run will re-check)"
                                    )
                                else:  # status_reason == "failed"
                                    reason_msg = f"failed (completed with {pct_str} completion)"

                                logger.error(
                                    f"[PHASE 1 FAILSAFE] Loader still failing after retry: {table_name} - {reason_msg}"
                                )

                                if is_crit:
                                    results["halt_required"] = True

                    except (RuntimeError, TimeoutError, ValueError) as e:
                        logger.critical(
                            f"[PHASE 1 FAILSAFE] CRITICAL: Failed to retry loader {table_name}: {e}. "
                            "Cannot retry critical loader."
                        )
                        results["still_failing"].append(table_name)
                        if is_crit:
                            results["halt_required"] = True
                            # Re-raise to prevent proceeding without recovery of critical loader
                            raise RuntimeError(
                                f"Phase 1 Failsafe: Critical loader {table_name} retry failed. Halting to prevent trading."
                            ) from e

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        # Database errors indicate infrastructure problems. Must halt trading.
        # Cannot safely proceed without being able to check loader status.
        logger.critical(
            f"[PHASE 1 FAILSAFE] CRITICAL: Cannot check loader status due to database error: {e}. "
            "Cannot determine if critical loaders are incomplete. Trading halted."
        )
        raise RuntimeError(
            f"Phase 1 Failsafe: Cannot check loader status due to database error: {e}. "
            "Halting to prevent trading with potentially incomplete data."
        ) from e

    # CRITICAL FIX 2026-07-01: Check if stock_scores has stale upstream dependencies
    # Upstream metric loaders (positioning_metrics, value_metrics, etc.) may update multiple
    # times per day, but stock_scores only gets recomputed if it's marked incomplete.
    # This can leave stock_scores with old data when upstream metrics update.
    try:
        with DatabaseContext("read") as cur:
            # Find the most recent update time among upstream metric tables
            cur.execute("""
                SELECT MAX(updated_at) as latest_metric_update
                FROM (
                    SELECT updated_at FROM positioning_metrics WHERE updated_at IS NOT NULL
                    UNION ALL
                    SELECT updated_at FROM value_metrics WHERE updated_at IS NOT NULL
                    UNION ALL
                    SELECT updated_at FROM stability_metrics WHERE updated_at IS NOT NULL
                    UNION ALL
                    SELECT updated_at FROM quality_metrics WHERE updated_at IS NOT NULL
                    UNION ALL
                    SELECT updated_at FROM growth_metrics WHERE updated_at IS NOT NULL
                ) metric_updates
            """)
            metric_result = cur.fetchone()
            latest_metric_update = metric_result[0] if metric_result and metric_result[0] else None

            if latest_metric_update:
                # Check stock_scores update time
                cur.execute("SELECT MAX(updated_at) FROM stock_scores")
                score_result = cur.fetchone()
                latest_score_update = score_result[0] if score_result and score_result[0] else None

                # If any upstream metric is newer than stock_scores, mark stock_scores as needing update
                if latest_score_update and latest_metric_update > latest_score_update:
                    age_minutes = (latest_metric_update - latest_score_update).total_seconds() / 60
                    logger.warning(
                        f"[PHASE 1 FAILSAFE] stock_scores has stale dependencies: "
                        f"latest metric update {age_minutes:.0f}m ago, latest score update {age_minutes:.0f}m ago. "
                        f"Upstream metrics have newer data. Retriggering stock_scores recomputation."
                    )
                    # Retrigger stock_scores to pick up new metric data
                    if not dry_run:
                        retry_result = retry_loader("stock_scores", symbols_missing=0, is_critical=True)
                        if retry_result.get("recovered"):
                            results["recovered"].append("stock_scores (dependency update)")
                        else:
                            logger.warning(
                                "[PHASE 1 FAILSAFE] stock_scores retry did not recover to 95%. "
                                "May have partial data, but proceeding as auxiliary loader."
                            )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.warning(
            f"[PHASE 1 FAILSAFE] Could not check stock_scores dependencies due to database error: {e}. "
            f"Continuing with existing data; stock_scores may be stale."
        )

    return results


def retry_loader(loader_name: str, symbols_missing: int, is_critical: bool) -> dict[str, Any]:
    """Retry a single incomplete loader.

    Args:
        loader_name: Name of the loader to retry
        symbols_missing: Number of symbols that were missing
        is_critical: True if this is a critical loader

    Returns:
        Dict with retry result:
        {
            "retried": bool,        # True if retry was triggered
            "recovered": bool,      # True if loader reached its configured min completion threshold
            "final_completion_pct": float | None,  # None if status unknown
            "status_reason": str,   # 'success', 'timeout' (still running), or 'failed'
        }

    Raises:
        RuntimeError: If retry invocation fails
        TimeoutError: If loader retry times out during monitoring
    """
    result: dict[str, bool | float | str | None] = {
        "retried": False,
        "recovered": False,
        "final_completion_pct": None,
        "status_reason": "unknown",
    }

    # Wait for API throttling to reset
    logger.info(f"[PHASE 1 FAILSAFE] Waiting {RETRY_WAIT_SECONDS}s before retry (API reset)")
    time.sleep(RETRY_WAIT_SECONDS)

    # Trigger retry via Lambda invocation or direct call
    logger.info(f"[PHASE 1 FAILSAFE] Triggering retry for {loader_name}")
    result["retried"] = invoke_loader_retry(loader_name, is_critical)

    if result["retried"]:
        # Monitor loader status
        recovered, final_pct, status_reason = monitor_loader_retry(loader_name, RETRY_MONITOR_TIMEOUT_SECONDS)
        result["recovered"] = recovered
        result["final_completion_pct"] = final_pct
        result["status_reason"] = status_reason

    return result


def invoke_loader_retry(loader_name: str, is_critical: bool) -> bool:
    """Invoke loader retry by triggering its ECS Fargate task, asynchronously.

    The orchestrator Lambda package deliberately excludes loaders/ heavy
    dependencies (pandas/numpy - see lambda/algo_orchestrator/requirements.txt)
    so loaders cannot run in-process here. Instead this reuses the same
    "algo-trigger-loaders" Lambda (lambda/trigger-loaders/lambda_function.py)
    that EventBridge uses for the regular schedule: it does ecs:RunTask for
    the named loader and returns immediately - the loader itself runs on its
    own ECS task, independent of this Lambda's lifetime/timeout.

    Args:
        loader_name: Name of loader to retry (matches data_loader_status.table_name,
            which is also the loader_name the trigger-loaders Lambda expects)
        is_critical: True if critical loader (for logging only)

    Returns:
        True if the ECS task was successfully started

    Raises:
        RuntimeError: If the trigger invocation fails or the ECS task didn't start
    """
    logger.info(
        f"[PHASE 1 FAILSAFE] Invoking retry for {loader_name} "
        f"(priority={'critical' if is_critical else 'auxiliary'}) via algo-trigger-loaders"
    )

    # In local mode, invoke loader directly via subprocess instead of Lambda/ECS
    if os.getenv("LOCAL_MODE", "").lower() in ("true", "1", "yes"):
        logger.info(f"[PHASE 1 FAILSAFE] LOCAL_MODE enabled - invoking {loader_name} directly via subprocess")
        try:
            # CRITICAL FIX SESSION 104: loader_name is a TABLE NAME (e.g., "price_daily")
            # but scripts/run_loader.py expects LOADER KEYS (e.g., "prices"). Convert first.
            from loaders.loader_registry import table_to_loader_shorthand

            try:
                loader_key_or_none = table_to_loader_shorthand(loader_name)
                if loader_key_or_none is None:
                    raise ValueError(f"Table {loader_name} not found in loader registry")
                loader_key: str = loader_key_or_none
            except ValueError as e:
                logger.error(
                    f"[PHASE 1 FAILSAFE] Cannot convert table {loader_name} to loader key: {e}. "
                    f"This table may not be registered in the loader registry."
                )
                raise RuntimeError(f"[PHASE 1 FAILSAFE] Table {loader_name} not registered") from e

            # SESSION 103 FIX: Use configured loader timeout instead of hardcoded 900s.
            # Prices needs 1440m (24h), not 15m. The configured timeout prevents premature
            # subprocess timeout that makes retry impossible for long loaders.
            # Use the loader_key (not table_name) to look up timeout.
            # SESSION 96 CRITICAL FIX: Fail-fast if loader not found - silent fallback to 3600s
            # was truncating 180min loaders (company_info_sec), causing cascading Monday failures.
            timeouts = get_loader_timeouts()
            if loader_key not in timeouts:
                # Fallback to trying the table name directly in case registry has both
                if loader_name in timeouts:
                    loader_timeout_seconds = timeouts[loader_name]
                else:
                    # Loader not registered - this is a configuration error, raise rather than silently default
                    raise RuntimeError(
                        f"[PHASE 1 FAILSAFE] Loader {loader_key} (table {loader_name}) not found in timeout config. "
                        f"Must be registered in loaders/loader_timeout_config.py. "
                        f"Registered loaders: {sorted(timeouts.keys())}"
                    )
            else:
                loader_timeout_seconds = timeouts[loader_key]

            subprocess_timeout = int(loader_timeout_seconds * 1.25)  # 25% safety margin
            logger.info(
                f"[PHASE 1 FAILSAFE] Using configured timeout for {loader_name} (loader_key={loader_key}): "
                f"{loader_timeout_seconds}s ({loader_timeout_seconds // 60}m), "
                f"subprocess timeout: {subprocess_timeout}s"
            )

            result = subprocess.run(
                [sys.executable, "scripts/run_loader.py", loader_key, "--force-refresh"],
                capture_output=True,
                text=True,
                timeout=subprocess_timeout,
            )
            if result.returncode == 0:
                logger.info(f"[PHASE 1 FAILSAFE] Local loader {loader_name} invoked successfully")
                return True
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                logger.error(f"[PHASE 1 FAILSAFE] Local loader {loader_name} invocation failed: {error_msg[:500]}")
                raise RuntimeError(
                    f"[PHASE 1 FAILSAFE] Local loader {loader_name} failed with return code {result.returncode}"
                )
        except subprocess.TimeoutExpired as e:
            logger.error(
                f"[PHASE 1 FAILSAFE] Local loader {loader_name} timed out after {subprocess_timeout}s "
                f"(configured {loader_timeout_seconds}s + 25% margin)"
            )
            raise RuntimeError(f"[PHASE 1 FAILSAFE] Local loader {loader_name} timeout") from e
        except Exception as e:
            logger.error(f"[PHASE 1 FAILSAFE] Failed to invoke local loader {loader_name}: {e}")
            raise RuntimeError(f"[PHASE 1 FAILSAFE] Failed to invoke local loader {loader_name}: {e}") from e

    trigger_function_name = os.getenv("TRIGGER_LOADERS_FUNCTION_NAME", "algo-trigger-loaders")

    try:
        lambda_client = boto3.client("lambda", region_name=os.getenv("AWS_REGION", "us-east-1"))
        response = lambda_client.invoke(
            FunctionName=trigger_function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps({"loader_name": loader_name}).encode("utf-8"),
        )

        status_code = response.get("StatusCode")
        if response.get("FunctionError"):
            payload = response["Payload"].read().decode("utf-8")
            raise RuntimeError(
                f"[PHASE 1 FAILSAFE] {trigger_function_name} returned FunctionError invoking {loader_name}: {payload}"
            )

        payload_raw = response["Payload"].read().decode("utf-8")
        if not payload_raw:
            raise ValueError("[PHASE 1 FAILSAFE] Lambda response body is empty")
        payload_body = json.loads(payload_raw)
        if "body" not in payload_body:
            raise ValueError("[PHASE 1 FAILSAFE] Lambda response missing 'body' field")
        body = payload_body["body"]
        if body is None:
            raise ValueError("[PHASE 1 FAILSAFE] Lambda body is None")
        body_obj = json.loads(body) if isinstance(body, str) else body

        if status_code != 200 or payload_body.get("statusCode", status_code) != 200:
            raise RuntimeError(
                f"[PHASE 1 FAILSAFE] {trigger_function_name} failed to start ECS task for {loader_name}: {body_obj}"
            )

        logger.info(f"[PHASE 1 FAILSAFE] ECS task(s) started for {loader_name}: {body_obj.get('tasks')}")
        return True

    except (RuntimeError, ValueError, TypeError, json.JSONDecodeError, ClientError, BotoCoreError) as e:
        raise RuntimeError(
            f"[PHASE 1 FAILSAFE] Failed to invoke retry for {loader_name}: {e}. "
            "Explicit error to prevent silent failure."
        ) from e


def monitor_loader_retry(loader_name: str, timeout_seconds: int) -> tuple[bool, float | None, str]:
    """Monitor loader status during retry.

    Args:
        loader_name: Name of loader being monitored
        timeout_seconds: How long to wait before giving up

    Returns:
        (recovered, final_completion_pct, status_reason):
        - recovered: True if loader reached its configured min completion threshold
        - final_completion_pct: Latest completion percentage, or None if status unknown
        - status_reason: 'success', 'timeout' (still running), 'stalled' (0% for 5+ min), or 'failed' (completed low)

    Raises:
        RuntimeError: If database error occurs during monitoring
    """
    # Get the loader's configured max_fail_rate to determine its min completion threshold
    max_fail_rate = get_loader_max_fail_rate(loader_name)
    min_completion_pct = 100.0 - max_fail_rate

    deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)

    # SESSION 103 FIX: Detect stalled progress (0% for >5 min indicates subprocess hung)
    stalled_start_time: datetime | None = None
    stalled_threshold_seconds = 300  # 5 minutes of no progress at 0%

    while datetime.now(timezone.utc) < deadline:
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT status, completion_pct FROM data_loader_status WHERE table_name = %s",
                    (loader_name,),
                )

                row = cur.fetchone()
                if row:
                    status, completion_pct = row

                    if completion_pct is None:
                        # Status unknown, likely still running - wait before checking again
                        stalled_start_time = None  # Reset stall tracker
                        logger.debug(
                            f"[PHASE 1 FAILSAFE] {loader_name} status unknown, still running (will check again in 10s)"
                        )
                    elif completion_pct > 0:
                        # Loader is progressing - reset stall tracker
                        stalled_start_time = None
                        if completion_pct >= min_completion_pct:
                            # Loader reached its configured minimum completion threshold
                            logger.info(
                                f"[PHASE 1 FAILSAFE] Loader recovered: {loader_name} {completion_pct:.1f}% (need >={min_completion_pct:.0f}%)"
                            )
                            return True, completion_pct, "success"
                    elif completion_pct == 0:
                        # SESSION 103 FIX: Detect subprocess hung at 0% completion
                        if stalled_start_time is None:
                            stalled_start_time = datetime.now(timezone.utc)
                            logger.warning(
                                f"[PHASE 1 FAILSAFE] {loader_name} at 0% completion, monitoring for stall..."
                            )
                        else:
                            stalled_duration = (datetime.now(timezone.utc) - stalled_start_time).total_seconds()
                            if stalled_duration >= stalled_threshold_seconds:
                                logger.critical(
                                    f"[PHASE 1 FAILSAFE] Subprocess stalled: {loader_name} at 0% for {int(stalled_duration)}s. "
                                    f"Subprocess likely hung or deadlocked. Treating as failed."
                                )
                                return False, 0.0, "stalled"

                    if status == "COMPLETED":
                        # Completed but still below minimum required completion
                        if completion_pct < min_completion_pct:
                            logger.critical(
                                f"[PHASE 1 FAILSAFE] Loader completed but dangerously incomplete: {loader_name} {completion_pct:.1f}%. "
                                f"Missing {100.0 - completion_pct:.1f}% of expected data (need >={min_completion_pct:.0f}%). "
                                f"This threshold prevents trading on incomplete market data (fail-fast)."
                            )
                            return False, completion_pct, "failed"

            # Check again in 10 seconds
            time.sleep(10)

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[PHASE 1 FAILSAFE] Database error monitoring retry for {loader_name}: {e}. "
                "Cannot determine loader status without database access."
            ) from e

    # Timeout reached - loader still running, didn't complete within deadline
    logger.error(
        f"[PHASE 1 FAILSAFE] Timeout waiting for retry of {loader_name} (waited {timeout_seconds}s, loader still running)"
    )
    return False, None, "timeout"
