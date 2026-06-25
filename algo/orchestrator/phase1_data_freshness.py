#!/usr/bin/env python3
"""
PHASE 1: DATA FRESHNESS CHECK

Verify pipeline-loaded tables are fresh before trading:
1. price_daily: Must have last trading day data (75%+ symbol coverage) — HALT if stale
2. market_health_daily: Market breadth metrics — HALT if stale
3. market_exposure_daily: Market regime / exposure limits — HALT if stale
4. earnings_calendar: Earnings dates for blackout window gating — HALT if stale
5. trend_template_data: Minervini/Weinstein criteria — WARNING if stale
6. swing_trader_scores: Legacy scoring — WARNING if stale
7. sector_ranking: Sector data for last trading day — WARNING if stale

Phase 5 generates stock_scores and signals on-the-fly from price_daily input.
Excluded: stock_scores (orchestrator output), technical_data_daily, buy_sell_daily (no longer in pipeline).

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

from algo.orchestrator.phase1_failsafe_retry import check_and_retry_incomplete_loaders
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


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

    Halts if price_daily, market_health_daily, or market_exposure_daily are stale —
    these are required for Phase 5 signal generation and regime gating.
    Issues warnings for trend_template_data, swing_trader_scores, and sector_ranking —
    stale but trading can continue.
    Excludes stock_scores (orchestrator-generated output, not pipeline input).
    """
    from datetime import timedelta as td

    phase_start = time.time()

    if not config:
        raise RuntimeError(
            "[PHASE 1] Config not provided: cannot proceed without phase1_min_coverage_pct "
            "and phase1_min_symbol_count thresholds. Config must be passed from algo_config table."
        )

    min_coverage_pct = config.get("phase1_min_coverage_pct")
    if min_coverage_pct is None:
        raise RuntimeError(
            "[PHASE 1] Config missing required key 'phase1_min_coverage_pct'. "
            "Cannot proceed without explicit data freshness threshold (no hardcoded fallback)."
        )

    min_symbol_count = config.get("phase1_min_symbol_count")
    if min_symbol_count is None:
        raise RuntimeError(
            "[PHASE 1] Config missing required key 'phase1_min_symbol_count'. "
            "Cannot proceed without explicit symbol count threshold (no hardcoded fallback)."
        )

    from datetime import datetime as dt
    from zoneinfo import ZoneInfo

    now_et = dt.now(ZoneInfo("America/New_York"))
    pipeline_context = "EOD" if now_et.hour >= 16 else "MORNING" if now_et.hour < 10 else "INTRADAY"

    logger.info(
        f"[PHASE 1] Starting comprehensive freshness check (Pipeline: {pipeline_context}, Time: {now_et.strftime('%H:%M:%S ET')})"
    )

    # PHASE 1 FAILSAFE: Check for and retry incomplete loaders before freshness check
    # This prevents cascading failures when upstream loaders are incomplete
    failsafe_result = check_and_retry_incomplete_loaders(dry_run=dry_run)

    if failsafe_result.get("halt_required"):
        logger.critical(
            "[PHASE 1] CRITICAL: Incomplete critical loaders even after failsafe retry. "
            "Cannot proceed with data processing."
        )
        still_failing = failsafe_result.get("still_failing")
        if still_failing is None:
            still_failing = []
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

    if failsafe_result.get("incomplete_loaders"):
        recovered = failsafe_result.get("recovered")
        if recovered is None:
            recovered = []
        still_failing = failsafe_result.get("still_failing")
        if still_failing is None:
            still_failing = []
        logger.info(
            f"[PHASE 1] Failsafe retry check: {len(recovered)} recovered, "
            f"{len(still_failing)} still failing (auxiliary)"
        )

    # ISSUE #6 FIX: Check DataPatrol results before proceeding with freshness validation
    # DataPatrol runs independently and validates data quality; Phase 1 must respect those findings
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SET LOCAL statement_timeout = '5000ms'")  # 5s timeout for patrol log check

            # Get latest DataPatrol results for today (critical/error severity only)
            # These are dealbreakers that must block trading
            cur.execute(
                """
                SELECT severity, check_name, target_table, message
                FROM data_patrol_log
                WHERE patrol_date = %s
                AND severity IN ('critical', 'error')
                ORDER BY severity DESC, check_name
                LIMIT 20
                """,
                (run_date,),
            )
            critical_patrol_issues = cur.fetchall()

            if critical_patrol_issues:
                logger.critical(
                    f"[PHASE 1] DataPatrol found {len(critical_patrol_issues)} critical/error issues. "
                    "Cannot proceed with trading until resolved."
                )
                issues_summary = "; ".join(
                    [f"{row[1]} ({row[2]}): {row[3][:80]}" for row in critical_patrol_issues[:5]]
                )
                log_phase_result_fn(
                    1,
                    "data_patrol_critical_issues",
                    "halt",
                    f"DataPatrol CRITICAL/ERROR: {issues_summary}",
                )
                from algo.orchestrator.phase_error_handling import (
                    ErrorCategory,
                    PhaseError,
                    log_phase_error,
                )

                error = PhaseError(
                    category=ErrorCategory.DATA_INVALID,
                    message=f"DataPatrol detected {len(critical_patrol_issues)} critical data quality issues",
                    root_cause=f"Check data_patrol_log table for details. Issues: {issues_summary}",
                    recoverable=False,
                    log_level="critical",
                )
                log_phase_error(1, error, log_phase_result_fn)

                return PhaseResult(
                    1,
                    "data_patrol_critical_issues",
                    "halted",
                    {},
                    True,
                    f"DataPatrol critical issues found: {issues_summary[:100]}",
                )

            # Log any warnings from DataPatrol (informational only - trading continues)
            cur.execute(
                """
                SELECT COUNT(*), COUNT(DISTINCT check_name)
                FROM data_patrol_log
                WHERE patrol_date = %s
                AND severity = 'warning'
                """,
                (run_date,),
            )
            patrol_warn_row = cur.fetchone()
            if patrol_warn_row is None:
                patrol_warn_count = 0
                patrol_warn_checks = 0
            else:
                if len(patrol_warn_row) < 2:
                    raise RuntimeError(
                        f"[PHASE1] DataPatrol query returned incomplete row: {patrol_warn_row} — "
                        "expected (warning_count, check_count) tuple"
                    )
                patrol_warn_count = patrol_warn_row[0]
                patrol_warn_checks = patrol_warn_row[1]
            if patrol_warn_count > 0:
                logger.warning(
                    f"[PHASE 1] DataPatrol: {patrol_warn_count} warning(s) from {patrol_warn_checks} check(s) "
                    "(trading continues but data quality degraded)"
                )

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        # Check if this is a "table doesn't exist" error (first-run scenario).
        # Even on first run, we should fail-closed for financial accuracy unless explicitly in dry-run.
        is_missing_table = "data_patrol_log" in str(e).lower() or "undefined table" in str(e).lower()
        if is_missing_table and not dry_run:
            logger.critical(
                "[PHASE 1] DataPatrol log table missing (not yet initialized). "
                "DataPatrol must be set up before trading. "
                "Please initialize data_patrol infrastructure or run in dry-run mode."
            )
            log_phase_result_fn(
                1,
                "data_patrol_not_initialized",
                "halt",
                "DataPatrol table missing — infrastructure not initialized",
            )
            return PhaseResult(
                1,
                "data_patrol_not_initialized",
                "halted",
                {},
                True,
                "DataPatrol infrastructure not initialized. Cannot proceed without quality checks.",
            )
        elif is_missing_table and dry_run:
            logger.warning(
                "[PHASE 1] DataPatrol log table not yet available (dry-run). "
                "Continuing with traditional freshness checks (production requires DataPatrol)."
            )
        else:
            # Unexpected database error — FAIL-CLOSED instead of silently continuing
            logger.critical(f"[PHASE 1] DataPatrol check failed (unexpected error): {str(e)[:100]}")
            log_phase_result_fn(
                1,
                "data_patrol_check_error",
                "halt",
                f"DataPatrol check failed: {str(e)[:100]}",
            )
            return PhaseResult(
                1,
                "data_patrol_check_error",
                "halted",
                {},
                True,
                f"DataPatrol check failed unexpectedly: {str(e)[:100]}",
            )

    try:
        with DatabaseContext("read") as cur:
            cur.execute("SET statement_timeout = 15000")  # 15s timeout for multi-table checks

            # CRITICAL: Validate that stock_scores table has data (Phase 5 dependency)
            # stock_scores must be populated by its loader before Phase 5 can generate signals
            cur.execute("SELECT COUNT(*) FROM stock_scores")
            stock_scores_count_row = cur.fetchone()
            if stock_scores_count_row is None or len(stock_scores_count_row) == 0:
                raise RuntimeError(
                    "[PHASE 1] Unexpected NULL/empty result from stock_scores COUNT query. "
                    "Database integrity check failed."
                )
            stock_scores_count = stock_scores_count_row[0]

            if stock_scores_count == 0:
                logger.critical(
                    "[PHASE 1] stock_scores table is empty — signal generation cannot proceed. "
                    "Check that stock_scores loader completed successfully."
                )
                log_phase_result_fn(
                    1,
                    "stock_scores_empty",
                    "halt",
                    "stock_scores table empty (loader incomplete?)",
                )
                return PhaseResult(
                    1,
                    "stock_scores_empty",
                    "halted",
                    {},
                    True,
                    "stock_scores table is empty — loader may not have completed",
                )

            # Find reference date from price_daily (most reliable source)
            cur.execute("SELECT MAX(date) FROM price_daily")
            row = cur.fetchone()
            max_date = row[0] if row and row[0] is not None else None

            if max_date is None:
                logger.critical("[PHASE 1] price_daily table is empty")
                log_phase_result_fn(1, "price_data", "halt", "price_daily table is empty")
                return PhaseResult(1, "price_data", "halted", {}, True, "price_daily table is empty")

            from algo.infrastructure import MarketCalendar

            # If run_date itself is a trading day, require same-day prices (algo runs post-close).
            # If run_date is a weekend/holiday, require prices from the most recent trading day.
            if MarketCalendar.is_trading_day(run_date):
                last_trading_day = run_date
            else:
                last_trading_day = run_date - td(days=1)
                while last_trading_day > run_date - td(days=10):
                    if MarketCalendar.is_trading_day(last_trading_day):
                        break
                    last_trading_day -= td(days=1)

            if max_date < last_trading_day:
                from algo.orchestrator.phase_error_handling import (
                    ErrorCategory,
                    PhaseError,
                    log_phase_error,
                )

                days_stale = (last_trading_day - max_date).days
                logger.critical(f"[PHASE 1] Price data stale: {max_date} vs expected {last_trading_day}")

                # CONSISTENCY: Categorize staleness as DATA_STALE so operators know it's a timing issue, not a loader failure
                error = PhaseError(
                    category=ErrorCategory.DATA_STALE,
                    message=f"Price data is {days_stale} day(s) stale (latest: {max_date}, expected: {last_trading_day})",
                    root_cause="Check that price_daily loader has completed for today. Check data_loader_status and CloudWatch logs.",
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
                    f"Price data too old: {max_date} vs {last_trading_day}",
                )

            # Verify price coverage - accept symbols with recent data (past 2 trading days)
            # This handles asynchronous data loading where different symbols update on different dates
            recent_cutoff = max_date - td(days=2)
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date >= %s AND date <= %s",
                (recent_cutoff, max_date),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise RuntimeError("Symbol count query failed for recent period")
            symbols_loaded = row[0]
            prior_cutoff = recent_cutoff - td(days=2)
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date >= %s AND date < %s",
                (prior_cutoff, recent_cutoff),
            )
            row = cur.fetchone()
            prior_count = row[0] if row and row[0] is not None else symbols_loaded
            coverage_pct = (symbols_loaded / max(prior_count, 1)) * 100

            if symbols_loaded < min_symbol_count or coverage_pct < min_coverage_pct:
                from algo.orchestrator.phase_error_handling import (
                    ErrorCategory,
                    PhaseError,
                    log_phase_error,
                )

                fail_reason = (
                    f"symbols {symbols_loaded} < min {min_symbol_count}"
                    if symbols_loaded < min_symbol_count
                    else f"coverage {coverage_pct:.1f}% < min {min_coverage_pct}%"
                )
                logger.critical(
                    f"[PHASE 1] Insufficient price coverage: {symbols_loaded} symbols ({coverage_pct:.1f}%) — {fail_reason}"
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

            # Halt-critical tables: Phase 5 cannot generate signals without these
            halt_tables = {
                "market_health_daily": "Market health (breadth/regime)",
                "market_exposure_daily": "Market exposure limits",
                "earnings_calendar": "Earnings dates (blackout window gating)",
            }
            # Warning-only tables: stale → logged, trading continues
            warn_tables = {
                "trend_template_data": "Trend template (Minervini/Weinstein)",
                "swing_trader_scores": "Swing trader scores (legacy, warning only)",
                "sector_ranking": "Sector rankings",
            }
            critical_tables = {**halt_tables, **warn_tables}

            halt_stale = []  # pipeline-loaded tables — stale = HALT
            warn_stale = []  # auxiliary tables — stale = WARNING only

            # Tables checked by MAX(date) vs price_daily latest date
            # Note: earnings_calendar uses earnings_date instead of date
            date_column_overrides = {
                "earnings_calendar": "earnings_date",
            }
            date_checked_tables = critical_tables

            try:
                union_parts = []
                for table_name in date_checked_tables.keys():
                    date_col = date_column_overrides.get(table_name, "date")
                    union_parts.append(f"SELECT '{table_name}' as tbl, MAX({date_col}) as max_dt FROM {table_name}")

                union_query = " UNION ALL ".join(union_parts)
                cur.execute(union_query)

                max_dates = {}
                for row in cur.fetchall():
                    row_dict = dict(row)
                    max_dates[row_dict["tbl"]] = row_dict["max_dt"]

                for table_name, description in date_checked_tables.items():
                    is_halt_table = table_name in halt_tables
                    try:
                        table_max_date = max_dates.get(table_name)

                        if table_max_date is None:
                            msg = f"{description} is empty"
                            if is_halt_table:
                                logger.critical(f"[PHASE 1] {msg}")
                                halt_stale.append(msg)
                            else:
                                logger.warning(f"[PHASE 1] {msg}")
                                warn_stale.append(msg)
                            continue

                        if table_max_date < max_date:
                            days_behind = (max_date - table_max_date).days
                            max_tolerance_days = 1 if is_halt_table else 0
                            if days_behind > max_tolerance_days:
                                msg = f"{description} is {days_behind} day(s) stale"
                                if is_halt_table:
                                    logger.critical(f"[PHASE 1] {msg}")
                                    halt_stale.append(msg)
                                else:
                                    logger.warning(f"[PHASE 1] {msg}")
                                    warn_stale.append(msg)
                            else:
                                msg = f"{description} is {days_behind} day(s) behind (within 1-day tolerance)"
                                logger.info(f"[PHASE 1] {msg}")

                    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                        msg = f"{description} check failed: {str(e)[:50]}"
                        if is_halt_table:
                            logger.critical(f"[PHASE 1] {msg} — FAIL-CLOSED")
                            halt_stale.append(msg)
                        else:
                            logger.warning(f"[PHASE 1] {msg}")
                            warn_stale.append(msg)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.critical(
                    f"[PHASE 1] CRITICAL: Failed to check table freshness — cannot verify data integrity: {e}",
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
                # Allow stale data in dry-run mode for development/testing
                if dry_run:
                    logger.warning(
                        f"[PHASE 1] CRITICAL DATA GAPS (pipeline tables) — BYPASSED FOR DRY-RUN: {'; '.join(halt_stale)}"
                    )
                    logger.warning(
                        "[PHASE 1] Continuing with stale data for dry-run testing. "
                        "In production, this would halt trading."
                    )
                else:
                    logger.critical(f"[PHASE 1] CRITICAL DATA GAPS (pipeline tables): {'; '.join(halt_stale)}")
                    log_phase_result_fn(
                        1,
                        "signal_tables_stale",
                        "halt",
                        f"Stale/missing pipeline data: {'; '.join(halt_stale[:3])}",
                    )
                    from algo.reporting.notifications import notify_signal_staleness

                    notify_signal_staleness(halt_stale)
                    return PhaseResult(
                        1,
                        "signal_tables_stale",
                        "halted",
                        {},
                        True,
                        f"Critical pipeline tables stale/missing: {halt_stale[0]}",
                    )

            elapsed = time.time() - phase_start
            phase1_end_et = dt.now(ZoneInfo("America/New_York"))

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

            log_phase_result_fn(
                1,
                "all_tables_fresh",
                "success",
                f"All critical tables fresh: prices={max_date}, coverage={coverage_pct:.1f}%",
            )

            return PhaseResult(
                1,
                "all_tables_fresh",
                "ok",
                {
                    "status": "ok",
                    "price_date": str(max_date),
                    "symbols_loaded": symbols_loaded,
                    "coverage_pct": coverage_pct,
                },
                False,
                "All critical data fresh and complete",
            )

    except Exception as e:
        logger.error(f"[PHASE 1] ERROR: {e}", exc_info=True)
        log_phase_result_fn(1, "error", "error", str(e)[:100])
        return PhaseResult(1, "error", "error", {}, True, f"Phase 1 error: {str(e)[:100]}")
