#!/usr/bin/env python3
"""
PHASE 1 HELPERS: PIPELINE-TABLE FRESHNESS MATRIX

Pure extract-method split of phase1_data_freshness.py's run() (see that module's docstring
for the overall Phase 1 contract). This file holds the per-table date-column mapping and the
per-table staleness comparison against each table's own reference date. The halt_tables/
warn_tables classification dicts themselves stay defined in phase1_data_freshness.py's run()
(several regression tests scan that file's source text for them directly), and are passed
into the functions below as parameters.

- DATE_COLUMN_OVERRIDES: per-table date-column mapping (most tables use "date"; metrics
  tables and a few SEC/financial tables use "updated_at" instead).
- build_table_reference_dates(): each table's upstream reference date (e.g. market_health_daily
  is limited by VIX availability in price_daily, not the global price_daily max_date).
- check_all_tables_freshness(): the single UNION ALL query fetching every table's MAX(date)
  and the per-table halt-vs-warn decision loop.

NO BEHAVIOR CHANGE: every function/constant here is a verbatim relocation of code that used
to live inline in run() - control flow, thresholds, log messages, and return values are
unchanged.
"""

import logging
from collections.abc import Callable
from datetime import date as _date
from datetime import datetime as dt
from typing import Any

import psycopg2

from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)

# Tables checked by MAX(date) vs price_daily latest date
# Note: metrics tables (growth, quality, value, positioning, stability) use updated_at instead of date
DATE_COLUMN_OVERRIDES = {
    # FIXED 2026-08-04: was "earnings_date" - a forward-looking calendar column
    # populated years ahead for scheduled earnings, not a load timestamp. That made
    # this halt-critical check structurally blind to loader staleness: confirmed
    # live, earnings_calendar's writer was deleted 2026-07-19 and its data frozen
    # since 2026-07-23, yet MAX(earnings_date) still read out to 2026-12-08 and
    # passed every freshness check. load_earnings_calendar.py (restored the same day
    # as this fix) now explicitly sets updated_at=now on every row it touches, so
    # this reflects real elapsed time since the loader last ran - same convention as
    # growth_metrics/quality_metrics/etc. below.
    "earnings_calendar": "updated_at",
    "growth_metrics": "updated_at",
    "quality_metrics": "updated_at",
    "value_metrics": "updated_at",
    "positioning_metrics": "updated_at",
    "stability_metrics": "updated_at",
    # SESSION 116 FIX: Add annual_income_statement (real table for the
    # "financial_statements" loader/pipeline - see note in warn_tables above)
    # & company_info_sec for visibility. These are SEC/financial data without
    # daily "date" columns; use "updated_at" to track when loaders last ran.
    # Allows early detection of stale financial data.
    "annual_income_statement": "updated_at",
    "company_info_sec": "updated_at",
    # CRITICAL FIX (2026-08-05): Add explicit date column for technical_data_daily
    # (was being skipped entirely from freshness checks). Uses standard "date" column
    # like price_daily, matching when technical indicators were computed/loaded.
    "technical_data_daily": "date",
}


def check_upstream_health_staleness(health_max_date: _date, acceptable_min_date: _date) -> list[str]:
    """Validate UPSTREAM reference tables (market_health_daily) are fresh before using them
    to validate downstream tables.

    CRITICAL FIX (Session 288): Validate UPSTREAM reference tables are fresh
    before using them to validate downstream tables.
    Previous bug: if market_health_daily was 9 days stale, and market_exposure_daily
    was also 9 days stale, comparing them to each other would pass (both same age).
    Solution: Compare upstream tables (market_health_daily, etc.) to expected trading day.

    Returns a list of halt_stale messages to append (empty if fresh).
    """
    if health_max_date >= acceptable_min_date:
        # Fresh - not an error, no halt messages to report, nothing to process here.
        return []

    days_behind = (acceptable_min_date - health_max_date).days
    logger.critical(
        f"[PHASE 1] UPSTREAM TABLE STALE: market_health_daily is {days_behind} day(s) old "
        f"(expected {acceptable_min_date}, got {health_max_date}). "
        f"Cannot use stale upstream table to validate downstream tables."
    )
    return [f"market_health_daily is {days_behind} day(s) stale (upstream reference invalid)"]


def build_table_reference_dates(
    vix_max_date: _date, health_max_date: _date, run_date: _date, acceptable_min_date: _date
) -> dict[str, _date]:
    """Map each table to its upstream reference date for staleness comparison.

    CRITICAL FIX: Must include all tables that will be checked below
    """
    return {
        "market_health_daily": vix_max_date,
        "market_exposure_daily": health_max_date,
        "earnings_calendar": run_date,  # Earnings calendar reference is the run date itself
        "earnings_calendar_sec": run_date,
        "price_daily": run_date,
        "technical_data_daily": run_date,
        "stock_scores": run_date,
        "buy_sell_daily": acceptable_min_date,  # Must have the latest trading day's signals for Phase 7
        "trend_template_data": run_date,
        "sector_ranking": run_date,
        "growth_metrics": run_date,
        "quality_metrics": run_date,
        "value_metrics": run_date,
        "positioning_metrics": run_date,
        "stability_metrics": run_date,
        # SESSION 116 FIX added annual_income_statement/company_info_sec to
        # date_checked_tables (warn_tables) but never added matching entries here,
        # so Phase 1 crashed with "missing reference date" the moment the earlier
        # "relation financial_statements does not exist" bug was fixed (confirmed
        # live 2026-08-16). Both are warn-only enrichment tables like growth_metrics
        # above, so run_date is the correct reference.
        "annual_income_statement": run_date,
        "company_info_sec": run_date,
    }


def check_all_tables_freshness(
    cur: Any,
    date_checked_tables: dict[str, str],
    halt_tables: dict[str, str],
    table_reference_dates: dict[str, _date],
    phase1_halt_table_max_tolerance_days: int,
    halt_stale: list[str],
    log_phase_result_fn: Callable[..., Any],
) -> tuple[list[str], list[dict[str, Any]], PhaseResult | None]:
    """Run the UNION ALL freshness query across every checked table and classify staleness.

    `halt_stale` is mutated in place (it may already contain the upstream health-staleness
    message from check_upstream_health_staleness) and is also returned for convenience.

    Returns (warn_stale, stale_table_details, halt_result). halt_result is a PhaseResult if
    the freshness query itself failed (fail-closed), else None.
    """
    warn_stale: list[str] = []  # auxiliary tables - stale = WARNING only
    # Structured (table_name, age) pairs mirroring halt_stale/warn_stale, kept separate
    # so the human-readable message strings above stay unchanged for existing callers
    # (notify_signal_staleness, log messages). This feeds the dashboard's PHASE EXECUTION
    # DETAILS panel (dashboard/panels/health.py, phase_num==1 branch), which reads
    # tables_validated/tables_fresh/tables_stale/stale_tables from PhaseResult.data - keys
    # this function never populated, so that panel section always rendered nothing.
    stale_table_details: list[dict[str, Any]] = []

    try:
        union_parts = []
        for table_name in date_checked_tables.keys():
            date_col = DATE_COLUMN_OVERRIDES.get(table_name, "date")
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
                    "[PHASE 1] Table freshness query returned NULL table name. Union query construction may be broken."
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
                        # BUG FOUND 2026-08-10 (live-reproduced): this hardcoded "1-day
                        # tolerance" regardless of the actual max_tolerance_days used in
                        # the comparison above (algo_config's
                        # phase1_halt_table_max_tolerance_days, live-confirmed set to 3,
                        # not 1). A live run logged "3 day(s) behind (within 1-day
                        # tolerance)" - self-contradictory, and actively misleading for
                        # anyone trying to diagnose staleness on a CRITICAL halt table.
                        msg = (
                            f"{description} is {days_behind} day(s) behind (within {max_tolerance_days}-day tolerance)"
                        )
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
            f"Could not verify table freshness: {str(e)[:500]}",
        )
        return (
            warn_stale,
            stale_table_details,
            PhaseResult(
                1,
                "table_freshness_check_error",
                "halted",
                {},
                True,
                f"Table freshness check failed (cannot distinguish stale from error): {str(e)[:500]}",
            ),
        )

    if warn_stale:
        logger.warning(
            f"[PHASE 1] Non-critical staleness (auxiliary tables, trading continues): {'; '.join(warn_stale)}"
        )

    return warn_stale, stale_table_details, None


def handle_halt_stale_tables(
    halt_stale: list[str],
    date_checked_tables: dict[str, str],
    stale_table_details: list[dict[str, Any]],
    log_phase_result_fn: Callable[..., Any],
) -> PhaseResult | None:
    """Halt Phase 1 if any halt-critical pipeline table is stale/missing."""
    if not halt_stale:
        return None

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
