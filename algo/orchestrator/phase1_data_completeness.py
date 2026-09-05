"""Table-date-column mapping and data-completeness checking for Phase 1's failsafe retry
loop, extracted from algo/orchestrator/phase1_failsafe_retry.py (2026-09-05, file-size
ratchet: that file is a Tier-2 bloater flagged for decomposition). Bodies are verbatim, no
logic changed - only moved file.

`LoaderStatusManager` is accessed via the phase1_failsafe_retry module object at call time
(not imported by name here) because some existing tests patch
`algo.orchestrator.phase1_failsafe_retry.LoaderStatusManager` expecting that to affect
_mark_loader_failed_after_crash - a plain import here would silently stop seeing that patch.
`algo.orchestrator.phase1_failsafe_retry` itself imports this module at load time, so the
reference is resolved lazily (inside the function body, not at import time) to avoid a
circular-import failure.
"""

import logging
from datetime import date as _date
from datetime import datetime
from typing import Any

import psycopg2

import algo.orchestrator.phase1_failsafe_retry as _p1
from loaders.loader_registry import all_tables, normalize_loader_name
from utils.infrastructure.timezone import EASTERN_TZ

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
        "industry_ranking": "date_recorded",
        "naaim": "date",
        "aaii": "date",
        "aaii_sentiment": "date",
        # BUG FIX (2026-08-16): both were "created_at", which is stamped once at INSERT and
        # never updated on upsert - a table loaded once weeks ago and never touched since
        # would show as permanently "fresh". earnings_date/filing_date are forward-looking
        # announcement dates, not load timestamps, so updated_at is the only real freshness
        # signal - same reasoning the completeness-check code below (~line 465) already uses
        # for earnings_calendar, and confirmed by a test predating this fix
        # (test_phase1_failsafe_earnings_calendar_column.py) that this map alone missed.
        "earnings_calendar": "updated_at",
        "earnings_calendar_sec": "updated_at",
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
        "value_metrics": "updated_at",  # No date column - use updated_at for freshness
        "quality_metrics": "updated_at",  # No date column - use updated_at for freshness
        "growth_metrics": "date",  # Has date column for data load date
        "momentum_metrics": "date",
        "positioning_metrics": "updated_at",  # 13F/short interest data
        "institutional_holdings_13f": "updated_at",
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
            status_mgr = _p1.LoaderStatusManager(table)  # type: ignore[attr-defined]
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
# This affected: sec_valuations (20m), institutional_holdings_13f (30m), sec_segment_info (30m).
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


def _check_data_completeness(cur: Any, table_name: str, check_date: _date) -> tuple[bool, str]:
    """Check if table has sufficient data completeness (95%+ non-NULL in critical column).

    Args:
        cur: Open DB cursor - caller owns the DatabaseContext/transaction this runs inside.
        table_name: Table being checked.
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
