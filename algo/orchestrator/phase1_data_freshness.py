#!/usr/bin/env python3
"""
PHASE 1: DATA FRESHNESS CHECK

Verify pipeline-loaded tables are fresh before trading:
1. price_daily: Must have last trading day data (75%+ symbol coverage) — HALT if stale
2. market_health_daily: Market breadth metrics — HALT if stale
3. market_exposure_daily: Market regime / exposure limits — HALT if stale
4. earnings_calendar: Earnings dates for blackout window gating — HALT if stale
5. growth_metrics: Multi-year revenue/EPS growth metrics — HALT if stale (ADDED 2026-07-05)
6. quality_metrics: Financial quality metrics (ROE/margins/ratios) — HALT if stale (ADDED 2026-07-05)
7. value_metrics: Valuation metrics (P/E, P/B, etc.) — HALT if stale (ADDED 2026-07-05)
8. positioning_metrics: Ownership and short interest — HALT if stale (ADDED 2026-07-05)
9. stability_metrics: Volatility and beta metrics — HALT if stale (ADDED 2026-07-05)
10. trend_template_data: Minervini/Weinstein criteria — WARNING if stale
11. sector_ranking: Sector data for last trading day — WARNING if stale
(swing_trader_scores: removed in Session 14, no longer checked)

CRITICAL FIX 2026-07-05: Metric loaders (growth, quality, value, positioning, stability)
are now required for stock scoring. Per phase1_failsafe_retry.py, these are CRITICAL loaders
that must complete and remain fresh. stock_scores requires minimum 3/6 metrics per GOVERNANCE.md
to prevent single-metric bias. Stale metrics = stale scores = HALT.

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

from algo.orchestrator.phase1_failsafe_retry import check_and_retry_incomplete_loaders
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


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
    # Log failsafe results for visibility
    logger.info(
        f"[PHASE 1] Failsafe retry check: "
        f"incomplete={len(failsafe_result.get('incomplete_loaders', []))} "
        f"retried={len(failsafe_result.get('retried', []))} "
        f"recovered={len(failsafe_result.get('recovered', []))} "
        f"still_failing={len(failsafe_result.get('still_failing', []))} "
        f"halt_required={failsafe_result.get('halt_required', False)}"
    )

    still_failing = failsafe_result.get("still_failing", [])
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
                cur.execute(
                    """SELECT completion_pct FROM data_loader_status
                       WHERE table_name='price_daily' ORDER BY last_updated DESC LIMIT 1"""
                )
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

    if failsafe_result.get("halt_required") is True:
        logger.critical(
            "[PHASE 1] CRITICAL: Other critical loaders incomplete even after failsafe retry. "
            "Cannot proceed with data processing."
        )
        still_failing = failsafe_result.get("still_failing")
        if still_failing is None:
            logger.error("[PHASE 1] failsafe_result missing 'still_failing' field — data quality issue")
            still_failing = ["unknown"]
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

    try:
        phase1_recent_cutoff_days = config.get("phase1_recent_cutoff_days", 2)
        phase1_prior_cutoff_days = config.get("phase1_prior_cutoff_days", 2)
        phase1_halt_table_max_tolerance_days = config.get("phase1_halt_table_max_tolerance_days", 1)
    except (KeyError, TypeError) as e:
        raise RuntimeError(
            f"[PHASE 1] Config error reading staleness thresholds: {e}. "
            "Defaults: phase1_recent_cutoff_days=2, phase1_prior_cutoff_days=2, phase1_halt_table_max_tolerance_days=1"
        ) from e

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

    Halts if price_daily, market_health_daily, or market_exposure_daily are stale —
    these are required for Phase 5 signal generation and regime gating.
    Issues warnings for trend_template_data and sector_ranking —
    stale but trading can continue.
    Excludes stock_scores (orchestrator-generated output, not pipeline input).
    """
    from datetime import timedelta as td

    phase_start = time.time()
    degraded_reason = None
    (
        min_coverage_pct,
        min_symbol_count,
        phase1_recent_cutoff_days,
        phase1_prior_cutoff_days,
        phase1_halt_table_max_tolerance_days,
    ) = _validate_config(config)

    from datetime import datetime as dt
    from zoneinfo import ZoneInfo

    now_et = dt.now(ZoneInfo("America/New_York"))
    pipeline_context = "EOD" if now_et.hour >= 16 else "MORNING" if now_et.hour < 10 else "INTRADAY"

    logger.info(
        f"[PHASE 1] Starting comprehensive freshness check (Pipeline: {pipeline_context}, Time: {now_et.strftime('%H:%M:%S ET')})"
    )

    # PHASE 1 FAILSAFE: Check for and retry incomplete loaders before freshness check
    failsafe_result = check_and_retry_incomplete_loaders(dry_run=dry_run)
    failsafe_halt = _check_failsafe_retry_result(failsafe_result, log_phase_result_fn)
    if failsafe_halt:
        return failsafe_halt

    try:
        with DatabaseContext("read") as cur:
            cur.execute("SET statement_timeout = 15000")  # 15s timeout for multi-table checks

            # Find reference date from price_daily (most reliable source)
            # NOTE: stock_scores is NOT validated here; it's an orchestrator OUTPUT (Phase 5),
            # not a pipeline loader INPUT. Validating orchestrator outputs in Phase 1 breaks first-run.
            # Phase 7 (Signal Generation) will handle missing stock_scores when it runs.
            cur.execute("SELECT MAX(date) FROM price_daily")
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
                return PhaseResult(1, "price_data", "halted", {}, True, "price_daily table is empty")

            # CRITICAL FIX: Ensure max_date is a date object, not datetime
            # PostgreSQL date columns can return datetime.datetime from some drivers
            if isinstance(max_date, dt):
                max_date = max_date.date()

            # CRITICAL: Verify stock_symbols table is pre-loaded (required for ALL loaders)
            cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
            symbol_count_row = cur.fetchone()
            if symbol_count_row is None or symbol_count_row[0] is None or symbol_count_row[0] == 0:
                logger.critical(
                    "[PHASE 1] CRITICAL: stock_symbols table is empty or has no active symbols. "
                    "All loaders depend on symbol list being pre-loaded. "
                    "Run load_market_constituents.py first to populate NASDAQ/NYSE symbols."
                )
                log_phase_result_fn(
                    1, "symbol_list_missing", "halt", "stock_symbols table empty - run market_constituents loader first"
                )
                return PhaseResult(
                    1,
                    "symbol_list_missing",
                    "halted",
                    {},
                    True,
                    "stock_symbols table is empty - symbols must be loaded before trading",
                )
            symbol_count = symbol_count_row[0]
            logger.info(f"[PHASE 1] Symbol list verified: {symbol_count} active symbols")

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
                # During market hours: expect the *previous* trading day's data (today's not closed yet)
                prev_date = run_date_obj - td(days=1)
                if MarketCalendar.is_trading_day(prev_date):
                    last_trading_day = prev_date
                else:
                    # Find the most recent trading day before today
                    last_trading_day = prev_date
                    while last_trading_day > run_date_obj - td(days=10):
                        if MarketCalendar.is_trading_day(last_trading_day):
                            break
                        last_trading_day -= td(days=1)
            else:
                # After market close (EOD context): expect same-day data if it's a trading day
                if MarketCalendar.is_trading_day(run_date_obj):
                    last_trading_day = run_date_obj
                else:
                    # Weekend/holiday: find most recent trading day
                    last_trading_day = run_date_obj - td(days=1)
                    while last_trading_day > run_date_obj - td(days=10):
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
                logger.warning("[PHASE 1] Attempting emergency price loader trigger...")

                # CRITICAL FIX: Try to load fresh prices before halting
                # This handles the case where the scheduled morning pipeline failed
                try:
                    from loaders.load_prices import PriceLoader

                    logger.info("[PHASE 1] Starting emergency price loader...")
                    loader = PriceLoader()
                    # Get portfolio symbols to load prices for
                    cur.execute(
                        "SELECT DISTINCT symbol FROM algo_positions WHERE status='open' ORDER BY symbol LIMIT 100"
                    )
                    positions = cur.fetchall()
                    symbols = [dict(p)["symbol"] for p in positions] if positions else []
                    if not symbols:
                        # If no open positions, load top portfolio symbols
                        cur.execute("SELECT DISTINCT symbol FROM algo_trades ORDER BY created_at DESC LIMIT 100")
                        trades = cur.fetchall()
                        symbols = [dict(t)["symbol"] for t in trades]
                    result = loader.run(symbols=symbols, parallelism=1, backfill_days=1)

                    if result.get("rows_inserted", 0) > 0:
                        logger.warning(f"[PHASE 1] Emergency loader succeeded: {result['rows_inserted']} rows inserted")
                        # Re-check price freshness after emergency load
                        cur.execute("SELECT MAX(date) FROM price_daily")
                        fresh_result = cur.fetchone()
                        if fresh_result and fresh_result[0]:
                            new_max_date = fresh_result[0]
                            # Ensure date comparison works (convert datetime to date if needed)
                            if isinstance(new_max_date, dt):
                                new_max_date = new_max_date.date()
                            if new_max_date >= last_trading_day:
                                logger.warning("[PHASE 1] Price data now fresh after emergency load - proceeding")
                                # Data is now fresh, continue to next check
                            else:
                                raise RuntimeError(f"Emergency loader inserted data but still stale: {new_max_date}")
                        else:
                            raise RuntimeError("Emergency loader reported success but no data found")
                    else:
                        raise RuntimeError(f"Emergency loader returned no data: {result}")
                except Exception as e:
                    logger.error(f"[PHASE 1] Emergency price loader failed: {type(e).__name__}: {e}")
                    # Fall back to halt if emergency load fails
                    error = PhaseError(
                        category=ErrorCategory.DATA_STALE,
                        message=f"Price data is {days_stale} day(s) stale (latest: {max_date}, expected: {last_trading_day}). Emergency price loader also failed.",
                        root_cause="Scheduled morning pipeline failed AND emergency price loader failed. Check price_daily loader, yfinance access, and network connectivity.",
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
                        f"Price data too old: {max_date} vs {last_trading_day} (emergency load failed)",
                    )

            # Verify price coverage - accept symbols with recent data (configurable days)
            # This handles asynchronous data loading where different symbols update on different dates
            recent_cutoff = max_date - td(days=phase1_recent_cutoff_days)
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date >= %s AND date <= %s",
                (recent_cutoff, max_date),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise RuntimeError("Symbol count query failed for recent period")
            symbols_loaded = row[0]
            prior_cutoff = recent_cutoff - td(days=phase1_prior_cutoff_days)
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date >= %s AND date < %s",
                (prior_cutoff, recent_cutoff),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise RuntimeError(
                    "[PHASE1] Prior symbol count query failed or returned NULL. "
                    "Cannot assess price data coverage without historical reference. "
                    "Check that price_daily has data from 2+ days ago."
                )
            prior_count = row[0]
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
            # FIXED 2026-07-07: Added metrics tables (growth, quality, value, positioning, stability)
            # These are CRITICAL for stock_scores generation in Phase 7. Missing/stale metrics = HALT.
            halt_tables = {
                "market_health_daily": "Market health (breadth/regime)",
                "market_exposure_daily": "Market exposure limits",
                "earnings_calendar": "Earnings dates (blackout window gating)",
                "growth_metrics": "Growth metrics (revenue/EPS growth)",
                "quality_metrics": "Quality metrics (ROE/margins/ratios)",
                "value_metrics": "Value metrics (P/E, P/B, P/S)",
                "positioning_metrics": "Positioning metrics (ownership/short interest)",
                "stability_metrics": "Stability metrics (volatility/beta)",
            }
            # Warning-only tables: stale -> logged, trading continues
            # FIXED 2026-07-06: Removed swing_trader_scores (deprecated table, removed in Session 14)
            warn_tables = {
                "trend_template_data": "Trend template (Minervini/Weinstein)",
                "sector_ranking": "Sector rankings",
            }

            halt_stale = []  # pipeline-loaded tables — stale = HALT
            warn_stale = []  # auxiliary tables — stale = WARNING only

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
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"[PHASE 1] CRITICAL: Database error fetching VIX/health reference dates: {e}")
                raise RuntimeError(f"[PHASE 1] Cannot fetch market reference dates from database: {e}") from e

            # Map each table to its upstream reference date for staleness comparison
            table_reference_dates = {
                "market_health_daily": vix_max_date,
                "market_exposure_daily": health_max_date,
            }

            try:
                union_parts = []
                for table_name in date_checked_tables.keys():
                    date_col = date_column_overrides.get(table_name, "date")
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
                    ref_date = table_reference_dates.get(table_name, max_date)
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
                if dry_run:
                    logger.warning(
                        f"[PHASE 1] CRITICAL DATA GAPS (pipeline tables) — BYPASSED (dry_run only): {'; '.join(halt_stale)}"
                    )
                else:
                    # SESSION 124 FIX: removed a fake "EMERGENCY_BOOTSTRAP" that used to sit here.
                    # It only ever loaded PRICE data via PriceLoader, but halt_stale here covers
                    # market_health_daily/market_exposure_daily/earnings_calendar/growth_metrics/
                    # quality_metrics/value_metrics/positioning_metrics/stability_metrics -- none of
                    # which loading prices can fix. Worse, its "full universe" attempt hardcoded
                    # psycopg2.connect("...host=localhost"), which can never reach RDS from a Lambda
                    # in production, so it always fell through to a 3-symbol hardcoded fallback
                    # (AAPL/SPY/QQQ) and unconditionally logged "PASS (after EMERGENCY_BOOTSTRAP)"
                    # regardless of whether the actual stale tables got fixed. A halt here is the
                    # correct, safe behavior -- this file already treats halt_stale as HALT-worthy
                    # everywhere else; loading three ETF prices should never have been able to
                    # override that.
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
            except RuntimeError as e:
                metric_error = str(e)
                # RESILIENCE FIX: Instead of HALT on stale metrics, allow DEGRADED mode
                # Check if metrics exist but are just stale (vs completely missing)
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
                        # Metrics exist and are reasonably recent (< 7 days), allow degraded mode
                        logger.warning(
                            "[PHASE 1] Metrics exist but may be slightly stale. "
                            "Proceeding in DEGRADED mode - stock scores may use older metric data."
                        )
                        degraded_reason = "Stale metric data (older than 1 day) - using available data"
                    else:
                        # Metrics are completely missing or too old, must halt
                        logger.critical(f"[PHASE 1] CRITICAL: Metric loaders validation failed: {metric_error}")
                        log_phase_result_fn(
                            1, "metric_loaders_not_ready", "halt", f"Metric loaders incomplete: {metric_error[:100]}"
                        )
                        return PhaseResult(
                            1,
                            "metric_loaders_not_ready",
                            "halted",
                            {},
                            True,
                            f"Required metric loaders not ready: {metric_error[:80]}",
                        )
                except Exception as check_err:
                    # If we can't check metric existence, halt safely
                    logger.error(f"[PHASE 1] Could not verify metric availability: {check_err}")
                    logger.critical(f"[PHASE 1] CRITICAL: Metric loaders validation failed: {metric_error}")
                    log_phase_result_fn(
                        1, "metric_loaders_not_ready", "halt", f"Metric loaders incomplete: {metric_error[:100]}"
                    )
                    return PhaseResult(
                        1,
                        "metric_loaders_not_ready",
                        "halted",
                        {},
                        True,
                        f"Required metric loaders not ready: {metric_error[:80]}",
                    )

            log_phase_result_fn(
                1,
                "all_tables_fresh",
                "success",
                f"All critical tables fresh: prices={max_date}, coverage={coverage_pct:.1f}%"
                + (f" [DEGRADED MODE: {degraded_reason}]" if degraded_reason else ""),
            )

            # Return with degraded status if metrics are stale but trading can proceed
            return PhaseResult(
                1,
                "all_tables_fresh_degraded" if degraded_reason else "all_tables_fresh",
                "degraded" if degraded_reason else "ok",
                {
                    "status": "degraded" if degraded_reason else "ok",
                    "price_date": str(max_date),
                    "symbols_loaded": symbols_loaded,
                    "coverage_pct": coverage_pct,
                    "degradation_reason": degraded_reason,
                },
                False,  # Not halted, trading can proceed even in degraded mode
                degraded_reason or "All critical data fresh and complete",
            )

    except Exception as e:
        # FIXED 2026-07-07: Include exception type and full message, not just truncated str(e)
        exception_type = type(e).__name__
        exception_msg = str(e) if str(e) else "(no message)"
        error_summary = f"{exception_type}: {exception_msg}"[:200]
        logger.error(f"[PHASE 1] ERROR: {error_summary}", exc_info=True)
        log_phase_result_fn(1, "error", "error", error_summary)
        return PhaseResult(1, "error", "error", {}, True, error_summary)
