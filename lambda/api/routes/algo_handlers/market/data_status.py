"""`_get_data_status` route handler plus its private support helpers.

Split out of the former flat algo_handlers/market.py (file-size-ratchet compliance split,
2026-09-05); re-exported from algo_handlers/market/__init__.py so existing callers require
zero changes. The helpers below (`_rollback_after_error`, `_classify_loader_state_issue`,
`_is_stale_by_trading_days`, `_daily_table_staleness_cutoffs`, `_is_reaped_artifact`,
`_reaped_recently`, `_row_needs_live_refresh`) are used only by `_get_data_status` and are
kept together with it in this one module rather than split further apart.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.sql
from psycopg2.extensions import cursor
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    list_response,
    normalize_to_utc_datetime,
    safe_dict_convert,
    validate_api_response,
)

from loaders.loader_timeout_config import get_loader_timeout
from shared_contracts.response_validator import ResponseValidator

from ..market_health import _collect_phase2_circuit_breakers
from .pipeline_tables import PIPELINE_REMOVED_TABLES

logger = logging.getLogger(__name__)


def _rollback_after_error(cur: cursor) -> None:
    """Reset an aborted transaction after a caught-and-continue DB error.

    Postgres marks a transaction as failed after any statement error - every later
    query on the same connection raises InFailedSqlTransaction until a ROLLBACK runs.
    _get_data_status queries a dozen+ tables sequentially and treats a single missing/
    broken table as non-fatal (log and continue), so without this every downstream
    query in the same request would cascade-fail from one bad table.
    """
    try:
        cur.connection.rollback()
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as rollback_err:
        logger.debug(f"[DATA_STATUS] Failed to rollback after query error: {rollback_err}")


def _classify_loader_state_issue(
    loader_run_status: str | None,
    consecutive_failures: int | float | None,
    exec_started: datetime | None,
    exec_completed: datetime | None,
    completion_pct: float | int | None,
) -> str | None:
    """Classify what the actual loader state issue is (distinct from data staleness).

    Returns a short description of the loader's operational issue, or None if healthy.
    Used by dashboard to show "Loader: PENDING (waiting to run)" vs "Data: STALE (4h old)"
    """
    if not isinstance(loader_run_status, str):
        return None

    status_lower = loader_run_status.lower()

    # Pending: loader is queued but hasn't started
    if status_lower == "pending":
        return "PENDING: waiting to run"

    # Running: loader is in progress
    if status_lower == "running":
        if exec_started and not exec_completed:
            exec_start_utc = normalize_to_utc_datetime(exec_started, None)
            if isinstance(exec_start_utc, datetime):
                elapsed_seconds = (datetime.now(timezone.utc) - exec_start_utc).total_seconds()
            else:
                elapsed_seconds = 0
            # FIX 2026-08-17: same Decimal-vs-isinstance gap as the status-classification copy
            # of this check above - NUMERIC completion_pct arrives as decimal.Decimal, which
            # (int, float, str) does not match, so this silently read as 0% for every real
            # value once a loader passed 30 minutes, producing a false "TIMEOUT: ... at 0%"
            # message no matter how far along the loader actually was.
            completion_float = float(completion_pct) if isinstance(completion_pct, (int, float, str, Decimal)) else 0
            if elapsed_seconds > 1800 and completion_float < 5:  # >30 min, <5% complete
                return f"TIMEOUT: running {elapsed_seconds / 3600:.1f}h at {completion_float:.0f}%"
            return f"RUNNING: {completion_float:.0f}% complete"
        return "RUNNING"

    # Failed: loader failed
    if status_lower == "failed":
        if isinstance(consecutive_failures, (int, float)) and consecutive_failures >= 2:
            return f"FAILED: {int(consecutive_failures)}x consecutive failures"
        return "FAILED: will retry on next scheduled run"

    # Repeated failures even if not currently failed
    if isinstance(consecutive_failures, (int, float)) and consecutive_failures >= 2:
        return f"HIGH RISK: {int(consecutive_failures)}x consecutive failures before recovery"

    return None


def _is_stale_by_trading_days(data_date: date, today: date, max_age: int) -> bool:
    """True if more than max_age *trading* days have elapsed since data_date.

    BUG FIX 2026-08-16: the weekly/biweekly staleness branch used raw
    `(today - data_date).days`, which counts weekends. A table updated once per trading day
    with e.g. stale_threshold_days=2 (market_exposure_daily, market_health_daily,
    algo_risk_daily, algo_portfolio_snapshots all use 2) falsely flipped to "stale" every
    single weekend even though 0 trading days were actually missed: Friday->Monday is 3
    calendar days but 0 missed trading days. Live-confirmed: both market_exposure_daily and
    market_health_daily had correct, current Friday data (the most recent trading day) but
    showed CRIT STALE on the dashboard. Count actual trading days elapsed via MarketCalendar
    instead, consistent with this file's own expected_date calc above and this repo's "date
    math must use MarketCalendar, not raw days" rule.
    """
    from algo.infrastructure import MarketCalendar

    trading_days_elapsed = len(MarketCalendar.get_trading_days(data_date, today)) - 1
    return trading_days_elapsed > max_age


# Tables written once per trading day whose elapsed-hours staleness thresholds (below) need
# the same weekend/holiday gap allowance as _is_stale_by_trading_days above - kept in sync
# with monitor_data_staleness.py's own THRESHOLDS gap-allowance whitelist (same table set,
# same reasoning: an intraday-refreshed table should NOT get this allowance).
DAILY_TABLE_WEEKEND_GAP_ALLOWANCE = frozenset(
    {
        "price_daily",
        "technical_data_daily",
        "market_exposure_daily",
        "market_health_daily",
        "sector_rotation_signal",
        "trend_template_data",
        "algo_signals",
        "algo_reconciliation_log",
        "industry_ranking",
        "growth_metrics",
        "quality_metrics",
        "value_metrics",
        "stability_metrics",
        "positioning_metrics",
        "sector_ranking",
        "buy_sell_daily",
        "circuit_breaker_status",
        "annual_income_statement",
        "company_info_sec",
        "stock_scores",
        "algo_trades",
        "algo_positions",
        "algo_performance_daily",
        "earnings_calendar",
    }
)


def _daily_table_staleness_cutoffs(table_name: str, today: date, expected_date: date) -> tuple[float, float]:
    """(stale_cutoff_hours, critical_cutoff_hours) for the max_age<=1 elapsed-hours branch.

    BUG FIX 2026-08-23 (goal session: "42/47 NOT READY" dashboard audit): that branch's own
    comment claims to "match monitor_data_staleness.py", but only matched its flat 24h/48h
    threshold numbers, not the weekend/holiday gap-scaling logic that script applies on top of
    them (see its check_all_tables()) - this endpoint drives the dashboard's actual "DATA
    FRESHNESS" panel and `ready_to_trade` flag, so the gap was a real, visible false alarm, not
    just an inconsistency between two read-only scripts. Live-confirmed 2026-08-23 (a Sunday):
    price_daily/stock_scores/algo_trades/buy_sell_daily all correctly read FRESH in
    monitor_data_staleness.py while this endpoint flagged them stale/error purely from the
    Friday->Sunday gap. `expected_date` is already this file's own "walk back to the last real
    trading day" result (computed once, above, from the same MarketCalendar source of truth) -
    reused here rather than re-derived.
    """
    if table_name not in DAILY_TABLE_WEEKEND_GAP_ALLOWANCE:
        return 24.0, 48.0
    gap_days = (today - expected_date).days
    if gap_days <= 1:
        return 24.0, 48.0
    gap_hours = gap_days * 24
    return 24.0 + gap_hours, 48.0 + gap_hours


REAPED_SELF_HEAL_GRACE = timedelta(hours=2)


def _is_reaped_artifact(msg: object) -> bool:
    """True if error_message is a reap-cleanup artifact (abandoned RUNNING row marked FAILED),
    not a genuine loader failure. See _reaped_recently for the time-bounded "self-healing"
    classification built on top of this."""
    if not isinstance(msg, str):
        return False
    stripped = msg.strip()
    return stripped.startswith(("[REAPED]", "[MANUAL REAP"))


def _reaped_recently(row: dict[str, Any], now_utc: datetime) -> bool:
    """True if `row` is a reap artifact AND recent enough to plausibly still be
    "self-healing" (i.e. worth the dashboard's dim/reassuring treatment).

    RECENCY CHECK ADDED 2026-08-17: "self-healing" was previously asserted unconditionally
    for every reaped loader with no time bound - live-caught the same day this false
    reassurance actually misled an operator: a mass-reap at 05:32:23 hit ~30 tables across all
    4 pipelines, but the "signals" pipeline (stock_scores, stability_metrics, buy_sell_daily,
    signal_quality_scores) never got a retry queued for it (unlike morning/metrics/reference,
    which did). Those 4 tables sat FAILED for 8+ hours while the dashboard kept calling them
    "self-healing" the entire time - there is no cron/scheduled-pass guarantee locally (see
    CLAUDE.md), only whatever a human happens to re-invoke, so claiming "self-healing"
    indefinitely is not something the code can back up. A reap that's still unaddressed after
    a couple hours demonstrably isn't healing on its own and should read as actionable, not
    dim/reassuring.
    """
    if not _is_reaped_artifact(row.get("error_message")):
        return False
    started = row.get("execution_started")
    if not isinstance(started, datetime):
        # No timestamp to judge recency by - don't assume it's still healing.
        return False
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (now_utc - started) <= REAPED_SELF_HEAL_GRACE


# Tables written directly by orchestrator phases (not by any loader). data_loader_status
# rows for these names (where they exist at all) come from a one-time seed or a historical
# standalone script run and are never updated again by the phases that actually own these
# tables now - so data_loader_status is fundamentally not authoritative for freshness here,
# regardless of whether its last_updated/row_count happen to be non-NULL. See
# _get_data_status's use of this mapping for the bug this fixed (2026-08-18): a stale-but-
# present data_loader_status row silently overrode a genuinely fresh table for 30+ hours.
ORCHESTRATOR_OWNED_TABLE_TS_COLUMNS = {
    "algo_positions": "entry_date",
    "algo_trades": "entry_date",
    "algo_reconciliation_log": "reconciliation_date",
    "algo_signals": "signal_date",
    "circuit_breaker_status": "updated_at",  # DATE-only check_date caused up to 24h imprecision
    "algo_performance_daily": "report_date",
    "algo_portfolio_snapshots": "snapshot_date",
    "algo_risk_daily": "report_date",
    "algo_metrics_daily": "date",
    "equity_curve_daily": "date",
    "growth_metrics": "date",
    "algo_orchestrator_runs": "updated_at",
}


def _row_needs_live_refresh(row: dict[str, Any]) -> bool:
    """True if a data_loader_status row must be re-queried against the live table
    before being trusted for freshness - either because it's missing values outright,
    or because it's for a table data_loader_status is never authoritative for."""
    return (
        row.get("row_count") is None
        or row.get("last_updated") is None
        or row.get("table_name") in ORCHESTRATOR_OWNED_TABLE_TS_COLUMNS
    )


@db_route_handler("fetch data status")
@validate_api_response("health")
def _get_data_status(cur: cursor) -> Any:  # noqa: C901
    """Get data freshness status with summary for ServiceHealth/AlgoTradingDashboard.

    Uses same trading-day-aware freshness logic as Phase 1 orchestrator to avoid
    false stale warnings on Monday holidays or 3-day weekends.
    """
    try:
        import utils.validation as validation_module
        from algo.infrastructure import MarketCalendar

        # FRESHNESS_RULES must exist - fail fast if configuration missing
        if not hasattr(validation_module, "FRESHNESS_RULES"):
            raise RuntimeError(
                "[DATA STATUS] CRITICAL: FRESHNESS_RULES not found in utils.validation module. "
                "This configuration is required for staleness detection. "
                "Verify utils/validation/__init__.py imports FRESHNESS_RULES from freshness_config.py."
            )
        # FRESHNESS_RULES entries are heterogeneous (critical: bool, max_age_days: int,
        # description/purpose: str, applies_to: list) - dict[str, int | bool] was too
        # narrow relative to the real structure in freshness_config.py.
        _fr: dict[str, dict[str, Any]] = validation_module.FRESHNESS_RULES

        # See module-level PIPELINE_REMOVED_TABLES for the exclusion list and why it's
        # shared with monitoring.py's loader_health summary.
        pipeline_removed_tables = PIPELINE_REMOVED_TABLES

        try:
            # error_message/execution_started/execution_completed/completion_pct/symbols_loaded/
            # symbol_count are written by every loader via LoaderStatusManager (utils/loaders/status_manager.py)
            # but were previously never selected here, so a loader that failed with a real error
            # (auth failure, rate limit, timeout) showed up on the dashboard as bare "STALE" with no
            # way to tell why without reading raw logs. Select them so the freshness panel can surface
            # the actual failure reason and in-progress load state, not just an age/row-count guess.
            # `status` (NOT_STARTED/RUNNING/COMPLETED/FAILED/TIMEOUT, see utils/loaders/status_enum.py)
            # is also written by every loader via LoaderStatusManager but was never selected here either -
            # without it, a loader that has literally never run (NOT_STARTED) looked identical to one
            # that ran and legitimately produced zero rows (row_count=0), and a TIMEOUT looked identical
            # to a FAILED - both collapsed into the same generic age/row-count-derived "stale"/"empty".
            # last_success_at/consecutive_failures (migration 1163) distinguish "last time this
            # loader finished successfully" from execution_completed's "last time it finished at
            # all" (that column is stamped on FAILED/TIMEOUT too), and let a loader that's failed
            # every run for days read differently from one that failed once.
            # execution_duration_sec/symbols_per_second/retry_count/http_status_code/
            # rate_limit_quota (migration 1164) are written by LoaderStatusManager.mark_completed()/
            # mark_failed() but were never selected here, so the freshness panel's Duration/
            # Throughput columns always rendered "--" and API Diagnostics had to guess failure
            # category by string-sniffing error_message instead of reading the real HTTP status.
            cur.execute("""
                    SELECT table_name, row_count, last_updated, stale_threshold_days,
                           error_message, execution_started, execution_completed,
                           completion_pct, symbols_loaded, symbol_count, status,
                           last_success_at, consecutive_failures, symbols_failed,
                           execution_duration_sec, symbols_per_second, retry_count,
                           http_status_code, rate_limit_quota
                    FROM data_loader_status
                    WHERE table_name IS NOT NULL
                    ORDER BY table_name
                """)
            loader_rows_raw = cur.fetchall()
        except psycopg2.errors.UndefinedTable:
            _rollback_after_error(cur)
            logger.warning(
                "[DATA_STATUS] data_loader_status table does not exist - will only report algo-generated tables"
            )
            loader_rows_raw = []
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            _rollback_after_error(cur)
            logger.warning(
                f"[DATA_STATUS] Could not query data_loader_status: {e} - will only report algo-generated tables"
            )
            loader_rows_raw = []

        loader_rows = []
        for r in loader_rows_raw:
            r_dict = safe_dict_convert(r)
            if r_dict.get("table_name") not in pipeline_removed_tables:
                loader_rows.append(r_dict)
        loader_names = {r["table_name"] for r in loader_rows}

        # Algo-generated tables written by the orchestrator, not tracked in data_loader_status
        # These are the core tables produced by each orchestrator phase
        algo_rows = []
        for tbl_name, query in [
            # Phase 2: Circuit breaker status
            (
                "circuit_breaker_status",
                "SELECT COUNT(*) AS row_count, MAX(check_date) AS last_updated FROM circuit_breaker_status",
            ),
            # Phase 4: Broker reconciliation
            (
                "algo_reconciliation_log",
                "SELECT COUNT(*) AS row_count, MAX(reconciliation_date) AS last_updated FROM algo_reconciliation_log",
            ),
            # Phase 4: Untracked positions (broker-held, not managed by algo)
            (
                "algo_untracked_positions",
                "SELECT COUNT(*) AS row_count, MAX(last_seen_at) AS last_updated FROM algo_untracked_positions",
            ),
            # Phase 6/7: Signal generation and execution
            (
                "buy_sell_daily",
                "SELECT COUNT(*) AS row_count, MAX(date) AS last_updated FROM buy_sell_daily",
            ),
            # Phase 7: Final signals generated
            (
                "algo_signals",
                "SELECT COUNT(*) AS row_count, MAX(signal_date) AS last_updated FROM algo_signals",
            ),
            # Phase 9: Portfolio snapshots
            # CRITICAL FIX: Use MAX(updated_at) not MAX(snapshot_date) for freshness
            # snapshot_date is DATE-only (midnight); updated_at reflects actual last write time
            # API endpoint (_get_algo_portfolio) calculates data_age_seconds from updated_at,
            # so health panel must use same column or staleness checks diverge
            # (confirmed: portfolio panel shows 29h old while health showed "OK" at 1d old)
            (
                "algo_portfolio_snapshots",
                "SELECT COUNT(*) AS row_count, MAX(updated_at) AS last_updated FROM algo_portfolio_snapshots",
            ),
            # Phase 9: Daily equity curve
            (
                "equity_curve_daily",
                "SELECT COUNT(*) AS row_count, MAX(date) AS last_updated FROM equity_curve_daily",
            ),
            # Phase 9: Daily performance metrics
            # CRITICAL FIX: Use MAX(updated_at) not MAX(report_date) for freshness
            # report_date is DATE-only (midnight); updated_at reflects actual last write time
            # API endpoint (_get_algo_performance) calculates data_age_seconds from updated_at,
            # so health panel must use same column or staleness checks diverge
            (
                "algo_performance_daily",
                "SELECT COUNT(*) AS row_count, MAX(updated_at) AS last_updated FROM algo_performance_daily",
            ),
            # Phase 9: Daily risk metrics
            (
                "algo_risk_daily",
                "SELECT COUNT(*) AS row_count, MAX(report_date) AS last_updated FROM algo_risk_daily",
            ),
            # Phase 9: Daily metrics (trade counts, average scores)
            (
                "algo_metrics_daily",
                "SELECT COUNT(*) AS row_count, MAX(report_date) AS last_updated FROM algo_metrics_daily",
            ),
            # Phase 3-8: Current open positions (used by position monitor, exit execution, entry execution)
            (
                "algo_positions",
                "SELECT COUNT(*) AS row_count, MAX(entry_date) AS last_updated FROM algo_positions",
            ),
            # Phase 6-8: All executed trades (used by exit execution, entry execution, reconciliation)
            (
                "algo_trades",
                "SELECT COUNT(*) AS row_count, MAX(entry_date) AS last_updated FROM algo_trades",
            ),
        ]:
            if tbl_name in loader_names:
                continue
            # pipeline_removed_tables intentionally excludes noisy/non-critical tables (e.g.
            # equity_curve_daily, algo_untracked_positions - both explicitly named above as
            # "not always populated" / expected-empty), but that exclusion only applied to
            # loader_rows. A table in BOTH pipeline_removed_tables and this hardcoded query list
            # is absent from loader_names (filtered out upstream), so `tbl_name in loader_names`
            # is False and this loop queried it fresh and re-added it anyway - confirmed live
            # 2026-07-27: both tables still showed up as "empty" on the dashboard's freshness
            # panel, defeating the exclusion and inflating the visible stale/empty count.
            if tbl_name in pipeline_removed_tables:
                continue
            try:
                cur.execute(query)
                r = cur.fetchone()
                if r:
                    r_dict = safe_dict_convert(r)
                    algo_rows.append(
                        {
                            "table_name": tbl_name,
                            "row_count": r_dict.get("row_count"),
                            "last_updated": r_dict.get("last_updated"),
                        }
                    )
            except psycopg2.errors.UndefinedTable:
                _rollback_after_error(cur)
                logger.warning(f"[DATA_STATUS] Table {tbl_name} does not exist - skipping")
                continue
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                _rollback_after_error(cur)
                logger.warning(f"[DATA_STATUS] Could not query {tbl_name}: {e}")
                continue

        # CRITICAL FIX: For loader tables with NULL row_count/last_updated, fetch actual values from database
        # data_loader_status.row_count/last_updated are populated by loaders on run, but orchestrator-generated
        # tables (algo_positions, algo_trades, etc.) never have their counts updated by loaders.
        # This causes false "empty" status. Query actual counts and timestamps to fix display.
        #
        # SECOND BUG FIXED HERE (see _row_needs_live_refresh/ORCHESTRATOR_OWNED_TABLE_TS_COLUMNS
        # above): the above comment's premise ("NULL row_count/last_updated") isn't the only way
        # this goes wrong. algo_trades and circuit_breaker_status both had *non-NULL but frozen*
        # data_loader_status rows (last_updated stuck at a date-old snapshot, e.g. from a one-time
        # seed/historical standalone run) that were never touched again because Phase 6-9 write
        # these tables directly and never update data_loader_status. Live-confirmed 2026-08-18:
        # circuit_breaker_status's data_loader_status row said last_updated=2026-08-17 00:00
        # (reported "30.1h stale", tripping the critical_stale gate) while the real table had a
        # row from 7 minutes ago.
        enriched_rows = []
        for row in loader_rows:
            tbl_name = row.get("table_name")
            needs_refresh = _row_needs_live_refresh(row)

            if needs_refresh and tbl_name:
                try:
                    # Default to updated_at for tables that track update timestamps
                    # Many tables use updated_at instead of created_at
                    ts_col = ORCHESTRATOR_OWNED_TABLE_TS_COLUMNS.get(tbl_name, "updated_at")

                    cur.execute(
                        psycopg2.sql.SQL("SELECT COUNT(*) AS cnt, MAX({}) AS last_ts FROM {}").format(
                            psycopg2.sql.Identifier(ts_col), psycopg2.sql.Identifier(tbl_name)
                        )
                    )
                    refresh_row = cur.fetchone()
                    if refresh_row:
                        actual_count = refresh_row[0]
                        last_ts = refresh_row[1]
                        if actual_count is not None:
                            row["row_count"] = actual_count
                        if last_ts is not None:
                            row["last_updated"] = last_ts
                        logger.debug(f"[DATA_STATUS] Refreshed {tbl_name}: count={actual_count}, ts={last_ts}")
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    _rollback_after_error(cur)
                    logger.warning(f"[DATA_STATUS] Could not refresh {tbl_name}: {e}")
                except Exception as e:
                    logger.warning(f"[DATA_STATUS] Unexpected error refreshing {tbl_name}: {e}")

            enriched_rows.append(row)

        rows = enriched_rows + algo_rows

        # Critical tables: trading cannot proceed if these are stale/empty
        # These are the core input/output tables for all 9 phases
        critical_tables = {
            # Phase 1 inputs (loaders must run successfully)
            "price_daily",  # Entry/exit prices, risk calculation
            "market_health_daily",  # Market regime, VIX
            "market_exposure_daily",  # Exposure %, market regime - controls risk sizing (Phase 5)
            "technical_data_daily",  # Signal quality indicators
            "trend_template_data",  # Weinstein stage for position sizing
            # Phase 2 output (trading halt check)
            "circuit_breaker_status",  # Portfolio drawdown, daily loss, VIX, market stage
            # Phase 3/4 input
            "algo_positions",  # Current portfolio state
            # Phase 6/7/8 dependencies
            "buy_sell_daily",  # Phase 7 signals, Phase 6/8 execution input
            # Phase 9 outputs
            "algo_portfolio_snapshots",  # Daily portfolio metrics, P&L
            "algo_metrics_daily",  # Daily trade counts, average signal scores - critical for monitoring
        }

        # Also add any critical tables from FRESHNESS_RULES config
        critical_tables.update({t for t, r in _fr.items() if r.get("critical")})

        # Compute expected data date using trading-day-aware logic (match Phase 1)
        today = date.today()
        expected_date = today - timedelta(days=1)
        try:
            for _ in range(10):
                if MarketCalendar.is_trading_day(expected_date):
                    break
                expected_date -= timedelta(days=1)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            # Fail fast if MarketCalendar unavailable - weekday check is wrong for holidays
            raise RuntimeError(
                f"Data freshness check requires MarketCalendar: {e}. "
                f"Cannot accurately determine expected data date (weekday check ignores holidays). "
                f"Data freshness checks will have false positives/negatives if we continue."
            ) from e

        sources = []
        summary = {"ok": 0, "stale": 0, "empty": 0, "error": 0}
        critical_stale = []

        # Resolved once (not per row) - see normalize_to_utc_datetime's docstring: naive
        # timestamp columns here (e.g. data_loader_status.last_updated) are written in the
        # DB session's local wall-clock (utils/bulk_insert_manager.py's convention), not
        # UTC. Without this, age_hours was inflated by the session's UTC offset (4-6h) -
        # confirmed live: a table updated 9 minutes ago showed age_hours=5.2.
        from utils.db.timezone_utils import get_db_timezone

        naive_tz = get_db_timezone()

        for row in rows:
            # CRITICAL: Skip rows without valid table_name (prevents API returning sources without 'name' field)
            table_name = row.get("table_name")
            if not table_name:
                logger.warning(f"[DATA_STATUS] Skipping row with missing/empty table_name: {row}")
                continue

            last_updated = row["last_updated"]
            row_count = row.get("row_count")

            # CRITICAL FIX 2026-08-03: freshness status/age must be judged by the loader's
            # last GENUINE success, not its last attempt. data_loader_status.last_updated is
            # bumped to NOW() by LoaderStatusManager.mark_failed() too (see utils/loaders/
            # status_manager.py) - a loader that keeps failing today while its last real
            # success was days ago still touches last_updated every failed run, so using it
            # here made the table look freshly-updated regardless of whether the run actually
            # succeeded. last_success_at (migration 1163) only advances on mark_completed(),
            # so prefer it for the freshness/age calc; fall back to last_updated for algo_rows
            # (orchestrator-written tables with no loader run, so no last_success_at at all).
            # Live-confirmed 2026-08-03: price_daily had status=FAILED, consecutive_failures=42,
            # last_updated stamped by the latest failed attempt - freshness would read "ok" off
            # that alone with no visible signal the loader itself was stuck failing.
            freshness_reference = row.get("last_success_at")
            if freshness_reference is None:
                freshness_reference = last_updated

            # Get freshness rule once per table (consolidate lookups)
            rule = _fr.get(table_name)

            # Extract max_age with consistent default of 1 day for unknown tables
            max_age_raw = rule.get("max_age_days") if rule is not None else None
            if max_age_raw is None:
                # FRESHNESS_RULES doesn't cover every loader-tracked table (e.g. earnings_calendar_sec,
                # algo_performance_metrics), so this used to hard-fall to a 1-trading-day default -
                # far stricter than these tables' own documented cadence. data_loader_status already
                # carries a per-table stale_threshold_days (set by the loader itself, e.g. 7 days for
                # earnings_calendar_sec) - confirmed live 2026-07-27: that column already correctly
                # marked both tables HEALTHY while this endpoint's separate 1-day default flagged them
                # "stale", producing false alarms on the dashboard's freshness summary. Prefer it over
                # the hardcoded default when present.
                loader_threshold = row.get("stale_threshold_days")
                if loader_threshold is not None:
                    max_age = int(str(loader_threshold))
                else:
                    max_age = 1
                    if table_name in _fr:
                        logger.warning(f"Freshness rule for {table_name} missing max_age_days field")
            else:
                max_age = int(str(max_age_raw)) if isinstance(max_age_raw, (int, str, float)) else 1

            # BUG FIX 2026-08-22 (goal session: dashboard health endpoint 500 audit): age_hours
            # was only ever assigned inside the else branch below - any row landing in either
            # "empty" branch (row_count None/0, or freshness_reference None, e.g. a table whose
            # live-refresh query above failed - live-confirmed via growth_metrics/
            # algo_metrics_daily's stale "report_date" column mapping) left age_hours undefined,
            # and the unconditional `age_h = age_hours` read further down (used for every row's
            # display) then raised UnboundLocalError, crashing this ENTIRE endpoint (HTTP 500)
            # for the whole dashboard health/freshness panel, not just the one broken table.
            age_hours = None
            if row_count is None or row_count == 0:
                status = "empty"
            elif freshness_reference is None:
                status = "empty"
            else:
                data_date = freshness_reference.date() if hasattr(freshness_reference, "date") else freshness_reference

                # Calculate elapsed time for all tables (used below for both daily and weekly/biweekly)
                utc_result_for_age = normalize_to_utc_datetime(freshness_reference, naive_tz)
                if isinstance(utc_result_for_age, datetime):
                    age_hours = (datetime.now(timezone.utc) - utc_result_for_age).total_seconds() / 3600

                if max_age <= 1:
                    # Daily tables: use elapsed-time thresholds to match monitor_data_staleness.py
                    # This fixes false-positive "OK" for data from yesterday that's 40+ hours old.
                    # Thresholds: fresh <24h, stale 24-48h, critical >48h (see CLAUDE.md), scaled
                    # across weekend/holiday gaps for tables on the whitelist - see
                    # _daily_table_staleness_cutoffs's own docstring for the full story.
                    stale_cutoff, critical_cutoff = _daily_table_staleness_cutoffs(table_name, today, expected_date)
                    if age_hours is not None:
                        # Use elapsed time for accurate freshness
                        if age_hours > critical_cutoff:
                            status = "critical"  # Will be override to "error" below if critical table
                        elif age_hours > stale_cutoff:
                            status = "stale"
                        else:
                            status = "ok"
                    else:
                        # Fallback to date-only comparison if elapsed time unavailable
                        status = "stale" if data_date < expected_date else "ok"
                else:
                    # Weekly/biweekly tables: use trading-day age, not raw calendar days -
                    # see _is_stale_by_trading_days docstring.
                    status = "stale" if _is_stale_by_trading_days(data_date, today, max_age) else "ok"

            # CRITICAL FIX 2026-08-04: a fresh-looking last_success_at/row_count can't tell a
            # clean run apart from one whose MOST RECENT attempt only partially completed -
            # live-confirmed on price_daily the same day as this fix (status='failed',
            # error_message="Load incomplete: failed (96.2%)", yet last_success_at was recent
            # enough that the freshness math above alone reads "ok"). data_loader_status.status
            # always reflects the latest attempt's real outcome (a later successful retry
            # overwrites it back to a healthy value), so cross-check it the same way
            # monitor_data_staleness.py's get_loader_failed() already does - this endpoint is
            # the one the dashboard's primary DATA FRESHNESS panel actually renders, and it had
            # no equivalent check, so the exact same incident that script would have flagged
            # showed a plain green "ok" here instead.
            loader_run_status_raw = row.get("status")
            consecutive_failures = row.get("consecutive_failures")

            # FIX 2026-08-12: Flag loaders in problematic states, not just stale data
            # PENDING loaders haven't run yet - they should show as "blocked" if their data is about to age
            if isinstance(loader_run_status_raw, str):
                status_lower = loader_run_status_raw.lower()
                if status_lower == "deprecated":
                    # FIX 2026-08-20: data_loader_status.status='DEPRECATED' (set for tables
                    # in pipeline_health.py's KNOWN_DEPRECATED_TABLES - deliberately retired
                    # loaders/never-real tables like ttm_balance_sheet) was never checked here,
                    # so this endpoint's own row_count==0/staleness logic above always won:
                    # zero-row deprecated tables showed "empty" (ttm_balance_sheet, row_count=0,
                    # live-confirmed), and aged-but-nonzero ones (buy_sell_weekly,
                    # market_cap_computed, price_extremes_52week, sec_cash_flow_metrics)
                    # showed "stale"/"critical" - the exact same-class noise pipeline_health.py's
                    # KNOWN_DEPRECATED_TABLES and freshness_enhancements.py's quality-check skip
                    # already fixed for their own call sites, but this dashboard-facing endpoint
                    # was never updated to match. These tables are intentionally frozen, not
                    # broken - treat as healthy like every other DEPRECATED consumer does.
                    status = "ok"
                elif status_lower == "failed":
                    status = "error"
                elif status_lower == "pending":
                    # Loader is queued but not started - will show as warning if data is aging
                    # Mark as blocked (intermediate severity between ok and error)
                    if status == "ok":
                        # Only override if data still looks fresh - pending + aging data = critical
                        status = "blocked"
                    elif status == "stale":
                        status = "error"  # Stale data + pending loader = critical
                elif status_lower == "running":
                    # RUNNING for >30 min with <5% completion is stuck/timeout
                    exec_started_raw = row.get("execution_started")
                    completion_pct_raw = row.get("completion_pct")
                    if exec_started_raw and completion_pct_raw is not None:
                        try:
                            exec_start_utc = normalize_to_utc_datetime(exec_started_raw, naive_tz)
                            if isinstance(exec_start_utc, datetime):
                                elapsed_seconds = (datetime.now(timezone.utc) - exec_start_utc).total_seconds()
                            else:
                                elapsed_seconds = 0
                            # FIX 2026-08-17: completion_pct is a NUMERIC column - psycopg2
                            # returns it as decimal.Decimal, which this isinstance check did not
                            # match, silently forcing completion_float to 0 for every real
                            # value. That made every loader running >30min falsely trip the
                            # "stuck" status="error" branch below regardless of true progress
                            # (live-confirmed: current_reports_8k genuinely 32% complete, still
                            # marked "error" here). See the matching fix in
                            # _classify_loader_state_issue for the same bug's display-text half.
                            completion_float = (
                                float(completion_pct_raw)
                                if isinstance(completion_pct_raw, (int, float, str, Decimal))
                                else 0
                            )
                            # FIX 2026-08-16: the <5% branch alone missed a loader that made
                            # real partial progress (e.g. 32%) and then died (crashed/OOM/killed)
                            # with no owning process left - it never re-enters this branch's
                            # low-completion case, so it just showed plain "RUNNING" (not even
                            # "warning") indefinitely until utils/loaders/status_manager.py's
                            # reap_stale_running_loaders() next happened to run for this exact
                            # table, which for a long-timeout loader (e.g. 9h) can be many hours
                            # away. Live-reproduced tonight: sec_segment_info died mid-run at
                            # 32.51% with no process alive, dashboard still would have called it
                            # healthy. Reuse the SAME per-loader-timeout+25%-margin the reaper
                            # itself uses, so any RUNNING loader long past its own realistic
                            # budget is flagged regardless of how far it got before dying.
                            timeout_seconds = get_loader_timeout(table_name, default_seconds=3600)
                            if elapsed_seconds > 1800 and completion_float < 5:  # >30 min, <5% done
                                status = "error"  # Treat stuck runners as error
                            elif elapsed_seconds > timeout_seconds * 1.25:
                                status = "error"  # Past its own timeout+margin - likely a dead/zombie run
                        except (ValueError, TypeError, AttributeError):
                            pass  # If we can't calculate, don't override status

            # Flag loaders with repeated failures - they need fixing, not just retrying
            if isinstance(consecutive_failures, (int, float)) and consecutive_failures >= 2:
                # Loaders with 2+ consecutive failures will likely fail again
                # Mark as high-risk: "warning" if they haven't fully failed yet
                if status == "ok" and table_name not in critical_tables:
                    status = "warning"  # Non-critical loader with repeated failures
                elif status == "ok" and table_name in critical_tables:
                    status = "error"  # Critical loader with repeated failures = error

            # age_hours already calculated above in status determination
            # Reuse it for display to ensure consistency between freshness verdict and displayed age
            age_h = age_hours

            # Determine role based on criticality and freshness requirement
            if rule is not None and rule.get("critical"):
                role = "CRIT"
            elif max_age <= 7:
                role = "IMP"
            else:
                role = "NORM"

            # Bump role to CRIT if loader has repeated failures (will fail again)
            if isinstance(consecutive_failures, (int, float)) and consecutive_failures >= 2:
                role = "CRIT"

            # Map "critical" status (>48h old) to "error" for API consistency
            # Dashboard may not expect "critical" as a distinct status value
            if status == "critical":
                status = "error"

            current_count = summary.get(status)
            if current_count is None:
                current_count = 0
            elif not isinstance(current_count, int):
                raise ValueError(f"Expected int for status count '{status}', got {type(current_count).__name__}")
            summary[status] = current_count + 1
            if status in ("stale", "empty", "error", "blocked", "warning") and row["table_name"] in critical_tables:
                critical_stale.append(row["table_name"])
            # Only loader_rows entries carry these (populated by LoaderStatusManager); algo_rows
            # (orchestrator-written tables like algo_positions) don't have a loader run to report on.
            exec_started = row.get("execution_started")
            exec_completed = row.get("execution_completed")
            completion_pct = row.get("completion_pct")
            last_success_at = row.get("last_success_at")
            execution_duration = row.get("execution_duration_sec")
            throughput = row.get("symbols_per_second")
            retry_count = row.get("retry_count")
            http_status_code = row.get("http_status_code")
            rate_limit_quota_raw = row.get("rate_limit_quota")
            sources.append(
                {
                    "name": row["table_name"],
                    "role": role,
                    "status": status,
                    "last_updated": last_updated.isoformat() if last_updated else None,
                    "age_hours": round(age_h, 1) if age_h is not None else None,
                    "row_count": row_count,
                    "loader_error": row.get("error_message"),
                    "execution_started": exec_started.isoformat() if exec_started else None,
                    "execution_completed": exec_completed.isoformat() if exec_completed else None,
                    "completion_pct": float(completion_pct) if completion_pct is not None else None,
                    "symbols_loaded": row.get("symbols_loaded"),
                    "symbol_count": row.get("symbol_count"),
                    # Loader's own run-state enum (NOT_STARTED/RUNNING/COMPLETED/FAILED/TIMEOUT) -
                    # distinct from `status` above (the age/row-count-derived freshness verdict).
                    # algo_rows entries (orchestrator-written tables) have no loader run, so this
                    # is always None for them.
                    "loader_run_status": row.get("status"),
                    "stale_threshold_days": max_age,
                    "last_success_at": last_success_at.isoformat() if last_success_at else None,
                    "consecutive_failures": row.get("consecutive_failures"),
                    # Per-run partial-failure count (migration 1196) - distinct from
                    # consecutive_failures, which only tracks whole-run failure streaks. A
                    # loader that partially fails every run but stays under max_fail_rate
                    # (so never FAILED, never increments consecutive_failures) is otherwise
                    # invisible here.
                    "symbols_failed": row.get("symbols_failed"),
                    "execution_duration_sec": float(execution_duration) if execution_duration is not None else None,
                    "symbols_per_second": float(throughput) if throughput is not None else None,
                    "retry_count": retry_count,
                    "http_status_code": http_status_code,
                    "rate_limit_quota_raw": rate_limit_quota_raw,
                    # FIX 2026-08-12: Explicit loader state issues (not just data staleness)
                    "loader_state_issue": _classify_loader_state_issue(
                        loader_run_status_raw, consecutive_failures, exec_started, exec_completed, completion_pct
                    ),
                }
            )

        # ── ENRICH HEALTH ITEMS WITH NEW METRICS ──────────────────────────────
        # Add data quality, coverage, and failure pattern data to each health item
        # so dashboard can display comprehensive operational health, not just freshness
        try:
            from dashboard.freshness_enhancements import (
                enrich_health_item_with_api_diagnostics,
                enrich_health_item_with_coverage,
                enrich_health_item_with_data_quality,
                enrich_health_item_with_failure_pattern,
                enrich_health_item_with_row_count_trend,
            )

            enriched_sources = []
            for source in sources:
                # Each enrichment adds new fields to the source dict
                # These fields are only used by the dashboard (not critical for API contract)
                try:
                    source = enrich_health_item_with_data_quality(source, cur)
                except Exception as e:
                    _rollback_after_error(cur)
                    logger.debug(f"[DATA_STATUS] Data quality enrichment failed for {source.get('name')}: {e}")

                try:
                    source = enrich_health_item_with_coverage(source, cur)
                except Exception as e:
                    _rollback_after_error(cur)
                    logger.debug(f"[DATA_STATUS] Coverage enrichment failed for {source.get('name')}: {e}")

                try:
                    source = enrich_health_item_with_failure_pattern(source, cur)
                except Exception as e:
                    _rollback_after_error(cur)
                    logger.debug(f"[DATA_STATUS] Failure pattern enrichment failed for {source.get('name')}: {e}")

                try:
                    source = enrich_health_item_with_row_count_trend(source, cur)
                except Exception as e:
                    _rollback_after_error(cur)
                    logger.debug(f"[DATA_STATUS] Row count trend enrichment failed for {source.get('name')}: {e}")

                try:
                    source = enrich_health_item_with_api_diagnostics(source)
                except Exception as e:
                    logger.debug(f"[DATA_STATUS] API diagnostics enrichment failed for {source.get('name')}: {e}")

                enriched_sources.append(source)

            sources = enriched_sources
        except ImportError as e:
            logger.warning(
                f"[DATA_STATUS] Freshness enhancements module not available: {e}. Dashboard will show basic freshness only."
            )

        # CRITICAL: Validate all sources have 'name' field before returning (prevents dashboard fetch_health errors)
        validated_sources = []
        for source in sources:
            if not isinstance(source, dict):
                logger.error(f"[DATA_STATUS] Source is not a dict: {type(source).__name__}, skipping")
                continue

            source_name = source.get("name")
            if not source_name:
                logger.error(
                    f"[DATA_STATUS] Source missing 'name' field. Available keys: {list(source.keys())}. Skipping."
                )
                continue

            validated_sources.append(source)

        sources = validated_sources
        if not sources:
            logger.warning("[DATA_STATUS] No valid sources after validation - returning empty list")

        # summary only gets a key for statuses that actually occurred at least once above
        # (summary[status] = current_count + 1). If every table is stale/empty/critical,
        # "ok" is legitimately absent, not corrupt -- 0 is the correct count, not an error.
        # INTENTIONAL DESIGN: When no tables are "ok" (all stale/empty/critical), the "ok" key
        # is correctly absent. Defaulting to 0 is the correct semantic value (zero healthy tables).
        ok_count = summary.get("ok", 0)
        if not isinstance(ok_count, int):
            raise ValueError(f"Expected int for 'ok' count in health summary, got {type(ok_count).__name__}")
        data_fresh_enough = len(critical_stale) == 0 and ok_count > 0

        # CRITICAL FIX: Add loader error count to summary for visibility
        # Loaders with consecutive_failures >= 1 indicate persistent issues
        # This is different from data staleness - it shows infrastructure health
        #
        # REAPED-ARTIFACT SPLIT (2026-08-16): live-checked this count against the DB while
        # investigating an operator's "the dashboard says errors but everything's actually
        # fine" report - every single one of the 20 loaders then flagged here had its
        # consecutive_failures streak entirely from reap_stale_running_loaders() marking an
        # abandoned (no owning process alive) run FAILED with an "[REAPED]"/"[MANUAL REAP"
        # error_message, not a real bug. local_loader_scheduler.py's run_pipeline() already
        # classifies this exact pattern the same way (see its is_reaped_only check), and IF
        # something re-invokes that table's pipeline it retries and self-heals instead of being
        # permanently skipped - but this summary counted it identically to a genuinely broken
        # loader, so the dashboard read "N errors" with no way to tell noise from a real
        # problem. Splitting the two lets the panel say what's actually actionable. Only reaps
        # within the last REAPED_SELF_HEAL_GRACE count as "reaped_only" (see _reaped_recently) -
        # past that grace window nothing local guarantees a retry actually happened, so it
        # reads as genuine again rather than asserting healing that may never come.
        now_utc = datetime.now(timezone.utc)

        loaders_with_errors = [
            (r.get("consecutive_failures") or 0, r.get("table_name"))
            for r in enriched_rows
            if isinstance(r.get("consecutive_failures"), (int, float)) and r.get("consecutive_failures") >= 1
        ]
        reaped_only = [
            (r.get("consecutive_failures") or 0, r.get("table_name"))
            for r in enriched_rows
            if isinstance(r.get("consecutive_failures"), (int, float)) and r.get("consecutive_failures") >= 1
            if _reaped_recently(r, now_utc)
        ]
        genuine_errors = len(loaders_with_errors) - len(reaped_only)
        # BUG FOUND 2026-08-17: this used to be sum(r[0] for r in loaders_with_errors) - a sum
        # of each loader's consecutive_failures streak, not a count of loaders. The dashboard
        # displays it right next to loaders_with_errors_genuine/_reaped_only (both loader
        # counts) as "N loader(s) with errors (TOTAL total) (M reaped, self-healing)", which
        # reads as TOTAL == N + M. Whenever any single loader's consecutive_failures streak was
        # >1, the sum inflated past N+M with no way for the reader to tell "more distinct
        # loaders are broken" from "the same loaders failed repeatedly" - live-caught as
        # "1 loader(s) with errors (10 total) ... 8 reaped" (1+8=9, not 10). Now a loader count
        # like its siblings, so the three numbers on that line always reconcile.
        total_failure_count = len(loaders_with_errors)
        summary["loaders_with_errors"] = len(loaders_with_errors)
        summary["total_loader_failures"] = int(total_failure_count)
        summary["loaders_with_errors_genuine"] = genuine_errors
        summary["loaders_with_errors_reaped_only"] = len(reaped_only)

        # CRITICAL: Data freshness alone does not mean trading is actually authorized.
        # The circuit breaker (Phase 2) can halt entries for reasons unrelated to data
        # staleness (e.g. portfolio drawdown >= 20%) - ready_to_trade must reflect that,
        # or the dashboard shows a contradictory "READY TO TRADE" checkmark right next to
        # an orchestrator panel reporting HALTED.
        #
        # FIX (2026-08-16): This used to read the latest algo_orchestrator_runs row's
        # overall_status/halt_reason instead of algo_runtime_state. That's a log of what
        # the last run DID, not the flag the orchestrator actually gates on before running
        # any phase (HaltFlagManager.check_halt_flag() reads algo_runtime_state, see
        # algo/orchestration/halt_flag_manager.py). The two diverge whenever the latest run
        # crashed on a since-fixed bug: the dashboard showed that stale, already-fixed run
        # error as "the" halt reason while algo_runtime_state's REAL governance/manual halt
        # (which requires explicit human clearing and does not auto-expire) sat unseen for
        # days. Confirmed live 2026-08-16: algo_runtime_state held a phase9_reconciliation_
        # governance halt from 2026-08-14 while the latest orchestrator_runs row showed an
        # unrelated, already-patched Phase 1 crash from hours earlier. Read the real gate.
        trading_halted = False
        trading_halt_reason = None
        trading_halt_at = None
        trading_halt_triggered_by = None
        try:
            cur.execute(
                """
                SELECT halt_flag, halt_reason, halt_triggered_at, state_value
                FROM algo_runtime_state
                WHERE state_key = 'orchestrator_halt'
                """
            )
            halt_row = cur.fetchone()
            if halt_row:
                halt_flag, halt_reason, halt_triggered_at, state_value = halt_row
                if halt_flag:
                    trading_halted = True
                    trading_halt_reason = halt_reason
                    trading_halt_at = halt_triggered_at.isoformat() if hasattr(halt_triggered_at, "isoformat") else None
                    if isinstance(state_value, str):
                        try:
                            state_value = json.loads(state_value)
                        except (json.JSONDecodeError, TypeError):
                            state_value = None
                    if isinstance(state_value, dict):
                        trading_halt_triggered_by = state_value.get("halt_triggered_by")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            _rollback_after_error(cur)
            logger.warning(f"[DATA_STATUS] Could not determine orchestrator halt state: {e}")

        ready_to_trade = data_fresh_enough and not trading_halted

        # ── Phase 1-9 Execution Health ──────────────────────────────────
        # Query execution health from tables populated by each orchestrator phase
        execution_health: dict[str, dict[str, Any] | None] = {}

        # Phase 1: Data Freshness Check (validates 11+ critical tables for trading)
        # Phase 1 checks: price_daily, market_health_daily, market_exposure_daily, earnings_calendar,
        # growth_metrics, quality_metrics, value_metrics, positioning_metrics, stability_metrics,
        # trend_template_data, sector_ranking
        try:
            phase1_tables = [
                "price_daily",
                "market_health_daily",
                "market_exposure_daily",
                "earnings_calendar",
                "growth_metrics",
                "quality_metrics",
                "value_metrics",
                "positioning_metrics",
                "stability_metrics",
                "trend_template_data",
                "sector_ranking",
            ]

            # CRITICAL FIX: this used to re-query data_loader_status with a flat
            # "updated within the last 24 raw hours of NOW()" filter, applied identically to
            # every table regardless of its real cadence - unlike `sources` above (built a few
            # dozen lines earlier in this same function), which already uses each table's real
            # trading-day-aware/stale_threshold_days-based status. Confirmed live 2026-07-27
            # (a Monday): 8 of these 11 tables were last updated Thu/Fri/Sat (their correct,
            # expected cadence - weekly metrics loaders, or Friday's close before the weekend)
            # and were all flagged "stale"/"fail" here purely because >24 raw hours had passed
            # since NOW(), while the real Phase 1 gate (algo/orchestrator/phase1_data_freshness.py)
            # correctly treated the same data as fresh and let trading proceed - this panel section
            # was pure false-alarm noise, never reflecting the actual orchestrator decision.
            # Derive from the already-correct `sources` list instead of re-deriving staleness here.
            phase1_sources = [s for s in sources if s["name"] in phase1_tables]
            if phase1_sources:
                fresh_count = sum(1 for s in phase1_sources if s["status"] == "ok")
                stale_count = len(phase1_sources) - fresh_count
                last_checked_candidates = [s["last_updated"] for s in phase1_sources if s["last_updated"]]
                execution_health["phase_1_data_check"] = {
                    "tables_validated": len(phase1_sources),
                    "tables_fresh": fresh_count,
                    "tables_stale": stale_count,
                    "validation_status": "pass" if stale_count == 0 else ("warn" if stale_count <= 2 else "fail"),
                    "last_checked": max(last_checked_candidates) if last_checked_candidates else None,
                }
            else:
                execution_health["phase_1_data_check"] = None
        except (ValueError, TypeError):
            execution_health["phase_1_data_check"] = None

        # Phase 2: Circuit Breaker Status
        # Thresholds MUST come from algo_config (the same source
        # algo/risk/circuit_breaker.py's _get_required_config reads at halt time). This used
        # to hardcode portfolio_drawdown_pct >= 20.0 while the real configured
        # halt_drawdown_pct was -10 (halt at 10% down) - a live drawdown of 12-19% would
        # already have halted real trading while this panel kept showing "OK".
        try:
            _collect_phase2_circuit_breakers(cur, execution_health)
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, TypeError, AttributeError) as e:
            _rollback_after_error(cur)
            logger.error(f"[HEALTH] Phase 2 circuit breaker query failed - reporting as unknown, not clear: {e}")
            execution_health["phase_2_circuit_breakers"] = None

        # Phase 3: Position Monitor Health
        try:
            cur.execute("""
                SELECT COUNT(*) as open_count,
                       MAX(days_since_entry) as oldest_days,
                       MIN(unrealized_pnl_pct) as max_loss_pct
                FROM algo_positions
                WHERE status = 'open'
            """)
            pos_row = cur.fetchone()
            if pos_row:
                pos_dict = safe_dict_convert(pos_row)
                open_count_val = pos_dict.get("open_count")
                if open_count_val is None:
                    logger.error(
                        "[HEALTH] Phase 3 position monitor check incomplete: missing open_count field from COUNT(*) query. "
                        "Database query returned unexpected schema."
                    )
                    execution_health["phase_3_position_monitor"] = None
                else:
                    execution_health["phase_3_position_monitor"] = {
                        "open_positions": int(open_count_val),
                        "oldest_days": int(pos_dict["oldest_days"])
                        if pos_dict.get("oldest_days") is not None
                        else None,
                        "max_loss_pct": (
                            float(pos_dict["max_loss_pct"]) if pos_dict.get("max_loss_pct") is not None else None
                        ),
                    }
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, TypeError, AttributeError) as e:
            _rollback_after_error(cur)
            logger.debug(f"[HEALTH] Phase 3 position monitor query failed: {e}")
            execution_health["phase_3_position_monitor"] = None

        # Phase 4: Broker Reconciliation Health
        try:
            # FIXED (migration 1216, goal session: "before real money" finance-accuracy
            # audit): avg_match_pct alone can't distinguish "genuinely checked against
            # Alpaca and it matched" from "no broker was available (paper mode), so
            # mismatches was hardcoded 0 and match_pct came out to a vacuous 100% by
            # construction" - both look identical in that one number. Surface
            # broker_verified_count/unverified_count alongside it so a caller can tell
            # whether this window's "100% match" means anything.
            cur.execute("""
                SELECT COUNT(*) as sync_count,
                       MAX(reconciliation_date) as latest_sync,
                       AVG(CAST(match_percentage AS FLOAT)) as avg_match_pct,
                       COUNT(*) FILTER (WHERE broker_verified = TRUE) as broker_verified_count,
                       COUNT(*) FILTER (WHERE broker_verified = FALSE) as broker_unverified_count
                FROM algo_reconciliation_log
                WHERE reconciliation_date >= CURRENT_DATE - INTERVAL '1 day'
            """)
            recon_row = cur.fetchone()
            if recon_row:
                recon_dict = safe_dict_convert(recon_row)
                # FIX: COUNT(*) is NEVER None/absent. Direct access fails if query corrupted.
                # Removed .get() fallback to 0 - if COUNT is None, that's a data corruption error.
                sync_count = int(recon_dict["sync_count"])
                execution_health["phase_4_broker_reconciliation"] = {
                    "sync_count": sync_count,
                    "latest_sync": recon_dict.get("latest_sync").isoformat() if recon_dict.get("latest_sync") else None,
                    "avg_match_pct": (
                        float(recon_dict["avg_match_pct"]) if recon_dict.get("avg_match_pct") is not None else None
                    ),
                    "broker_verified_count": int(recon_dict.get("broker_verified_count") or 0),
                    "broker_unverified_count": int(recon_dict.get("broker_unverified_count") or 0),
                }
            else:
                execution_health["phase_4_broker_reconciliation"] = None
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, TypeError, AttributeError) as e:
            _rollback_after_error(cur)
            logger.debug(f"[HEALTH] Phase 4 broker reconciliation query failed: {e}")
            execution_health["phase_4_broker_reconciliation"] = None

        # Phase 5: Exposure Policy (market regime, entry constraints, halt flags)
        # Phase 5 evaluates market regime and sets entry constraints for risk management
        try:
            cur.execute("""
                SELECT regime, is_entry_allowed, halt_reasons, date
                FROM market_exposure_daily
                ORDER BY date DESC LIMIT 1
            """)
            phase5_row = cur.fetchone()
            if phase5_row:
                phase5_dict = safe_dict_convert(phase5_row)
                regime = phase5_dict.get("regime")
                is_entry_allowed = phase5_dict.get("is_entry_allowed")
                # halt_reasons is stored as JSON text (e.g. "[]" or '["reason"]'), same as
                # every other reader of this column in this file (see _normalize_exposure
                # and the ExposureHistory handler below) - must be parsed before checking
                # for content. bool("[]") is True (non-empty string), so the previous raw
                # truthiness check reported halt_active=True on every row with zero actual
                # halt reasons, contradicting entry_allowed=True in the same response.
                halt_reasons_raw = phase5_dict.get("halt_reasons")
                try:
                    halt_reasons = (
                        json.loads(halt_reasons_raw) if isinstance(halt_reasons_raw, str) else halt_reasons_raw
                    )
                except (json.JSONDecodeError, TypeError):
                    halt_reasons = []

                execution_health["phase_5_exposure_policy"] = {
                    "market_regime": regime,
                    "market_trend": None,
                    "entry_allowed": is_entry_allowed,
                    "max_new_entries": None,
                    "capital_deployment_pct": None,
                    "halt_active": bool(halt_reasons),
                    "checked_at": phase5_dict.get("date").isoformat() if phase5_dict.get("date") else None,
                }
            else:
                execution_health["phase_5_exposure_policy"] = None
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, TypeError, AttributeError):
            _rollback_after_error(cur)
            execution_health["phase_5_exposure_policy"] = None

        # Phase 6: Exit Execution Health (last 24h)
        try:
            cur.execute("""
                SELECT COUNT(*) as exits_executed,
                       COUNT(*) FILTER (WHERE exit_price IS NOT NULL) as successful_exits,
                       AVG(profit_loss_dollars) FILTER (WHERE profit_loss_dollars IS NOT NULL) as avg_profit,
                       COALESCE(ARRAY_AGG(DISTINCT symbol) FILTER (WHERE symbol IS NOT NULL), ARRAY[]::text[]) as symbols_exited
                FROM algo_trades
                WHERE exit_date >= CURRENT_DATE - INTERVAL '1 day'
                AND exit_date IS NOT NULL
            """)
            exit_row = cur.fetchone()
            if exit_row:
                exit_dict = safe_dict_convert(exit_row)
                exits_executed_val = exit_dict.get("exits_executed")
                successful_exits_val = exit_dict.get("successful_exits")
                symbols_exited_val = exit_dict.get("symbols_exited")
                if exits_executed_val is None or successful_exits_val is None or symbols_exited_val is None:
                    logger.error(
                        "[HEALTH] Phase 6 exit execution check incomplete: missing required fields. "
                        f"exits_executed={exits_executed_val}, successful_exits={successful_exits_val}, "
                        f"symbols_exited={symbols_exited_val}"
                    )
                    execution_health["phase_6_exit_execution"] = None
                else:
                    total_exits = int(exits_executed_val)
                    successful = int(successful_exits_val)
                    execution_health["phase_6_exit_execution"] = {
                        "exits_executed": total_exits,
                        "successful_exits": successful,
                        "success_rate": (successful / total_exits * 100) if total_exits > 0 else 0,
                        "avg_profit": float(exit_dict["avg_profit"])
                        if exit_dict.get("avg_profit") is not None
                        else None,
                        "symbols_exited": symbols_exited_val,
                    }
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, TypeError):
            _rollback_after_error(cur)
            execution_health["phase_6_exit_execution"] = None

        # Phase 7: Signal Generation (outputs algo_signals generated by Phase 7)
        # Phase 7 generates trading signals from technical analysis and fundamental screening
        try:
            cur.execute("""
                SELECT COUNT(*) as signal_count,
                       COUNT(*) FILTER (WHERE raw_signal = 'BUY') as buy_count,
                       COUNT(*) FILTER (WHERE raw_signal = 'SELL') as sell_count,
                       AVG(CAST(signal_quality_score AS FLOAT)) as avg_strength,
                       MAX(created_at) as latest_signal,
                       COALESCE(ARRAY_AGG(DISTINCT symbol) FILTER (WHERE symbol IS NOT NULL), ARRAY[]::text[]) as symbols_with_signals
                FROM algo_signals
                WHERE created_at >= CURRENT_DATE - INTERVAL '1 day'
            """)
            sig_row = cur.fetchone()
            if sig_row:
                sig_dict = safe_dict_convert(sig_row)
                total_signals = sig_dict.get("signal_count")
                buy_signals = sig_dict.get("buy_count")
                sell_signals = sig_dict.get("sell_count")
                if total_signals is None or buy_signals is None or sell_signals is None:
                    logger.error(
                        "[HEALTH] Phase 7 signal generation check incomplete: missing signal counts. "
                        f"total_signals={total_signals}, buy_signals={buy_signals}, sell_signals={sell_signals}"
                    )
                    execution_health["phase_7_signal_generation"] = None
                else:
                    total_signals = int(total_signals)
                    buy_signals = int(buy_signals)
                    sell_signals = int(sell_signals)
                    symbols_with_signals_val = sig_dict.get("symbols_with_signals")
                    if symbols_with_signals_val is None:
                        logger.error(
                            "[HEALTH] Phase 7 signal generation check incomplete: missing symbols_with_signals field. "
                            "Cannot report which symbols generated signals."
                        )
                        execution_health["phase_7_signal_generation"] = None
                    else:
                        execution_health["phase_7_signal_generation"] = {
                            "signals_generated": total_signals,
                            "buy_signals": buy_signals,
                            "sell_signals": sell_signals,
                            "avg_strength": (
                                float(sig_dict["avg_strength"]) if sig_dict.get("avg_strength") is not None else None
                            ),
                            "latest_signal": (
                                sig_dict.get("latest_signal").isoformat() if sig_dict.get("latest_signal") else None
                            ),
                            "symbols_with_signals": symbols_with_signals_val,
                        }
            else:
                execution_health["phase_7_signal_generation"] = None
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, TypeError):
            _rollback_after_error(cur)
            execution_health["phase_7_signal_generation"] = None

        # Phase 8: Entry Execution Health (last 24h)
        try:
            cur.execute("""
                SELECT COUNT(*) as entries_executed,
                       COUNT(*) FILTER (WHERE entry_price IS NOT NULL) as successful_entries,
                       AVG(entry_price) FILTER (WHERE entry_price IS NOT NULL) as avg_entry_price,
                       COALESCE(ARRAY_AGG(DISTINCT symbol) FILTER (WHERE symbol IS NOT NULL), ARRAY[]::text[]) as symbols_entered
                FROM algo_trades
                WHERE entry_date >= CURRENT_DATE - INTERVAL '1 day'
                AND entry_date IS NOT NULL
            """)
            entry_row = cur.fetchone()
            if entry_row:
                entry_dict = safe_dict_convert(entry_row)
                entries_executed_val = entry_dict.get("entries_executed")
                successful_entries_val = entry_dict.get("successful_entries")
                symbols_entered_val = entry_dict.get("symbols_entered")
                if entries_executed_val is None or successful_entries_val is None or symbols_entered_val is None:
                    logger.error(
                        "[HEALTH] Phase 8 entry execution check incomplete: missing required fields. "
                        f"entries_executed={entries_executed_val}, successful_entries={successful_entries_val}, "
                        f"symbols_entered={symbols_entered_val}"
                    )
                    execution_health["phase_8_entry_execution"] = None
                else:
                    total_entries = int(entries_executed_val)
                    successful = int(successful_entries_val)
                    execution_health["phase_8_entry_execution"] = {
                        "entries_executed": total_entries,
                        "successful_entries": successful,
                        "success_rate": (successful / total_entries * 100) if total_entries > 0 else 0,
                        "avg_entry_price": (
                            float(entry_dict["avg_entry_price"])
                            if entry_dict.get("avg_entry_price") is not None
                            else None
                        ),
                        "symbols_entered": symbols_entered_val,
                    }
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, TypeError):
            _rollback_after_error(cur)
            execution_health["phase_8_entry_execution"] = None

        # Phase 9: Portfolio Snapshot Health
        try:
            # BUG FIX 2026-08-31: MAX(snapshot_date) and MAX(total_portfolio_value) were
            # independent aggregates with no pairing to the same row - after any drawdown
            # from a prior peak (routine), this returned the all-time HIGHEST portfolio value
            # mislabeled as the CURRENT one alongside the real latest date, understating real
            # risk exposure to anyone reading this health check. Fixed to pair date and value
            # from the same latest row, matching the correct pattern already used elsewhere
            # (e.g. position_sizer.py's get_portfolio_value snapshot fallback). Also bounded by
            # snapshot_date <= CURRENT_DATE - same "stray future-dated snapshot" bug class fixed
            # 2026-08-09 across circuit_breaker.py/position_sizer.py/var.py/etc (see
            # tests/unit/test_no_unbounded_portfolio_snapshot_queries.py's docstring).
            cur.execute("""
                SELECT counts.snapshot_count,
                       latest.snapshot_date as latest_date,
                       latest.total_portfolio_value as latest_value
                FROM (SELECT COUNT(*) as snapshot_count FROM algo_portfolio_snapshots) counts
                LEFT JOIN (
                    SELECT snapshot_date, total_portfolio_value
                    FROM algo_portfolio_snapshots
                    WHERE snapshot_date <= CURRENT_DATE
                    ORDER BY snapshot_date DESC
                    LIMIT 1
                ) latest ON TRUE
            """)
            snap_row = cur.fetchone()
            if snap_row:
                snap_dict = safe_dict_convert(snap_row)
                snapshot_count_val = snap_dict.get("snapshot_count")
                if snapshot_count_val is None:
                    logger.error(
                        "[HEALTH] Phase 9 portfolio snapshot check incomplete: missing snapshot_count field from COUNT(*) query. "
                        "Database query returned unexpected schema."
                    )
                    execution_health["phase_9_portfolio_snapshot"] = None
                else:
                    execution_health["phase_9_portfolio_snapshot"] = {
                        "snapshot_count": int(snapshot_count_val),
                        "latest_snapshot": (
                            snap_dict.get("latest_date").isoformat() if snap_dict.get("latest_date") else None
                        ),
                        "portfolio_value": float(snap_dict["latest_value"]) if snap_dict.get("latest_value") else None,
                    }
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, TypeError):
            _rollback_after_error(cur)
            execution_health["phase_9_portfolio_snapshot"] = None

        response = list_response(sources, total=len(sources), limit=None, offset=None)
        response["data"]["sources"] = sources
        response["data"]["ready_to_trade"] = ready_to_trade
        response["data"]["trading_halted"] = trading_halted
        response["data"]["trading_halt_reason"] = trading_halt_reason
        response["data"]["trading_halt_at"] = trading_halt_at
        response["data"]["trading_halt_triggered_by"] = trading_halt_triggered_by
        response["data"]["summary"] = summary
        response["data"]["critical_stale"] = critical_stale
        response["data"]["expected_date"] = str(expected_date)
        response["data"]["as_of"] = datetime.now(timezone.utc).isoformat()
        response["data"]["execution_health"] = execution_health

        # Validate health response against contract schema
        is_valid, error_msg = ResponseValidator.validate_endpoint_response("health", response["data"])
        if not is_valid:
            logger.error(f"Health response validation failed: {error_msg}")
            return error_response(500, "response_validation_error", error_msg)

        return response
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch data status")
        return error_response(code, error_type, message)
