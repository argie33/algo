"""Route: algo"""

# Force module reload on Lambda deployment (clear bytecode cache)
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    list_response,
    normalize_to_utc_datetime,
    safe_dict_convert,
    safe_json_serialize,
    validate_api_response,
)

from algo.infrastructure.config.sql_intervals import get_interval_sql
from algo.monitoring.pipeline_health import PipelineHealth
from shared_contracts.response_validator import ResponseValidator
from utils.validation import format_decimal_string, get_optional_field

from .signals import _TIER_CONFIG

logger = logging.getLogger(__name__)

# Tables intentionally removed from health tracking - these are optional enrichment only
# (not core to algo trading decisions). Excluding them prevents noise on the health panel.
# These are still populated by loaders but monitoring them isn't critical.
#
# Module-level (not local to _get_data_status) so other health/monitoring endpoints - e.g.
# monitoring.py's freshness/extended loader_health summary - can exclude the same tables.
# Before this was hoisted, monitoring.py's unhealthy-loader count had no such exclusion,
# so a table like algo_untracked_positions (excluded here, so it can NEVER appear in the
# DATA FRESHNESS table) could still be counted in the "Loader Health: N table(s) with
# issues (see Data Freshness Table below)" summary - pointing the user at a table list that
# structurally cannot contain the table being complained about. Confirmed live 2026-08-04.
PIPELINE_REMOVED_TABLES = {
    # Enrichment-only tables (Phase 1 halt logic doesn't depend on these)
    "price_monthly",
    "price_weekly",
    "etf_price_daily",
    "etf_price_weekly",
    "etf_price_monthly",
    # Signal variants (only daily equity signals matter; weekly/monthly/ETF are enrichment)
    "buy_sell_daily_etf",
    "buy_sell_weekly",
    "buy_sell_weekly_etf",
    "buy_sell_monthly",
    "buy_sell_monthly_etf",
    "signal_quality_scores",  # Enrichment; quality tracked via avg_strength in buy_sell_daily
    # SESSION 118 FIX: Restored visibility of metrics tables
    # These were hidden from health panel by Session 114 with rationale "enrichment-only",
    # but stakeholders need to know when optional data is 2+ days stale. Restored them to
    # the data status report (dashboard & monitor) while keeping them separate from
    # critical_tables (Phase 1/9 dependencies). Phase 1 may not halt on stale metrics,
    # but visible staleness = faster issue detection vs. silent rot behind an "everything OK" UI.
    "positioning_metrics",  # Re-added: institutional holdings data (daily). Was temporarily
    # removed with growth/quality/value metrics above but is different - it's computed from
    # 13F filings (quarterly updates), not daily SEC data like the metrics we restored.
    # Keep visible but acknowledge lower update cadence than growth/quality/value_metrics.
    # Economic data (not used in trading logic)
    "economic_data",
    # System/user tables
    "users",
    "user_alerts",
    "user_dashboard_settings",
    "user_api_keys",
    # Archive tables (historical only)
    "algo_trades_archive",
    # Utility tables
    "schema_version",
    "last_updated",
    "api_idempotency_cache",
    # Optional metrics (enrichment only)
    "economic_calendar",
    "earnings_calendar",
    "insider_transactions",
    "institutional_ownership",
    "stock_splits",
    "analyst_sentiment_analysis",
    "analyst_upgrade_downgrade",
    "aaii_sentiment",
    "naaim",
    "fear_greed_index",
    "commodity_correlations",
    "commodity_seasonality",
    "covered_call_opportunities",
    "credit_spreads",
    "vcp_patterns",
    "support_resistance_levels",
    "seasonality_day_of_week",
    "seasonality_monthly_stats",
    "ttm_cash_flow",
    "ttm_income_statement",
    "yfinance_ip_ban",
    "yfinance_snapshot",
    # Contact/community tables
    "contact_submissions",
    "community_signups",
    # ETF-specific (not algo-traded)
    "etf_symbols",
    # Alpha/ML archive (historical experiments)
    "algo_model_registry",
    "algo_champion_challenger",
    "algo_component_attribution",
    "algo_information_coefficient",
    "algo_position_sizing_audit",
    "algo_stop_loss_audit",
    "algo_tca",
    "algo_trade_adds",
    "algo_trade_r_distribution",
    "algo_exit_rules_distribution",
    "algo_weight_history",
    "algo_daily_return_histogram",  # Analytics table (empty)
    "algo_data_patrol",  # Analytics table (empty)
    "algo_holding_period_histogram",  # Analytics table (empty)
    "algo_orchestrator_state",  # Deprecated state table (empty, use orchestrator_runs instead)
    "alpaca_import_failures",
    "data_remediation_log",
    # Market/sector analysis (rarely updated or empty)
    "dividend_history",  # Historical data, not actively maintained
    "sector_correlation",  # Analytics table (empty)
    "sectors",  # Base lookup table (rarely changes)
    # Phase 9 outputs (only populated on successful complete orchestrator runs)
    "equity_curve_daily",  # Generated by Phase 9 - not always updated
    "portfolio_holdings",  # Manual/enrichment table (very stale)
    "positions_using_stale_fallback",  # Deprecated - empty
    "algo_untracked_positions",  # Empty from this morning's error run
    # Deprecated loaders (removed per DEPRECATED_LOADERS.md)
    "market_cap_computed",  # ORPHANED - load_market_cap_computed.py removed
    "price_extremes_52week",  # ORPHANED - load_price_extremes.py removed
    # Earnings table name mismatch (config calls it earnings_history_daily, actual table is earnings_history; loader writes to earnings_calendar_sec)
    "earnings_history",  # Legacy empty table - no loader writes to it (loader→earnings_calendar_sec)
    # Superseded tables (per algo/monitoring/pipeline_health.py's KNOWN_DEPRECATED_TABLES -
    # confirmed live 2026-07-27: 0 rows, no INSERT/UPDATE writer anywhere in the codebase)
    "sec_dividends",  # Superseded by dividend_data
    "sec_material_events",  # Superseded by current_reports_8k
    # Financeals (supplementary)
    "annual_balance_sheet",
    "annual_cash_flow",
    "annual_income_statement",
    "quarterly_balance_sheet",
    "quarterly_cash_flow",
    "quarterly_income_statement",
    "sec_valuations",
    # Misc
    "loader_execution_locks",
    "loader_sla_status",
    "filter_rejection_log",
    "signal_filter_tiers",
    "signal_rejection_log",
    "signal_trade_performance",
    "qualified_trades",
    "manual_positions",
} | PipelineHealth.KNOWN_DEPRECATED_TABLES
# ^ Unioned in rather than hand-duplicated: this set and algo/monitoring/pipeline_health.py's
# KNOWN_DEPRECATED_TABLES are both "tables with no writer, expected to sit frozen" allowlists,
# but were maintained as two independent literals. They drifted - sec_cash_flow_metrics
# (deprecated 2026-07-27) and algo_performance_metrics (confirmed dead 2026-08-10) were added
# to KNOWN_DEPRECATED_TABLES but never mirrored here, so this endpoint (the actual source for
# the dashboard's DATA FRESHNESS panel) kept reporting both as false STALE for weeks - confirmed
# live 2026-08-11 in the "5 stale" dashboard count. Unioning instead of copying means any future
# addition to KNOWN_DEPRECATED_TABLES can't silently drift out of sync with this list again.


@db_route_handler("get data quality")
@validate_api_response("health")
def _get_data_quality(cur: cursor) -> Any:
    try:
        # Get patrol log entries from last 24 hours
        interval_24h = get_interval_sql("24h")
        cur.execute(f"""
                SELECT
                    target_table AS table_name,
                    severity,
                    message,
                    NULL AS data_detail,
                    created_at,
                    ROW_NUMBER() OVER (PARTITION BY target_table ORDER BY created_at DESC) as rn
                FROM data_patrol_log
                WHERE created_at >= CURRENT_TIMESTAMP - {interval_24h}
            """)
        patrol_rows = cur.fetchall()

        if not patrol_rows:
            response = list_response([], total=0, limit=None, offset=None)
            response["data"]["accuracy_check"] = "no_data"
            response["data"]["last_check"] = None
            response["data"]["summary"] = {
                "critical": 0,
                "errors": 0,
                "warnings": 0,
                "healthy": 0,
            }
            return response

        # Organize by table, keeping latest status per table
        tables_dict = {}
        for row in patrol_rows:
            row_dict = safe_json_serialize(safe_dict_convert(row))
            if row_dict.get("rn") == 1:  # Latest entry per table
                table_name = row_dict.get("table_name")
                if not table_name:
                    raise ValueError(
                        "[DATA QUALITY] Patrol log row missing table_name. "
                        "Cannot identify which table is being monitored. "
                        "Check data_patrol_log table for NULL target_table values."
                    )
                tables_dict[table_name] = row_dict

        # Get latest timestamp
        latest_ts = max([safe_dict_convert(r)["created_at"] for r in patrol_rows]) if patrol_rows else None

        # Compute summary
        severity_counts = {"critical": 0, "error": 0, "warn": 0, "healthy": 0}
        table_statuses = []
        for table_name, entry in tables_dict.items():
            severity = entry.get("severity")
            if not severity:
                raise ValueError(
                    f"[DATA QUALITY] Patrol log entry for {table_name} missing severity. "
                    f"Cannot determine health status of this table. "
                    f"Check data_patrol_log.severity column for NULL values."
                )
            severity_counts[severity if severity in severity_counts else "warn"] += 1
            if severity == "critical":
                status_label = "failed"
            elif severity in ("error", "warn"):
                status_label = "warning"
            else:
                status_label = "passed"

            table_statuses.append(
                {
                    "table": table_name,
                    "status": status_label,
                    "severity": severity,
                    "message": entry.get("message"),
                    "detail": entry.get("data_detail"),
                    "last_check": (entry.get("created_at") if entry.get("created_at") else None),
                }
            )

        # Determine overall accuracy
        if severity_counts["critical"] > 0:
            accuracy = "failed"
        elif severity_counts["error"] > 0:
            accuracy = "error"
        elif severity_counts["warn"] > 0:
            accuracy = "warning"
        else:
            accuracy = "passed"

        # Sort tables by status severity
        status_order = {"failed": 0, "error": 1, "warning": 2, "passed": 3}
        table_statuses.sort(key=lambda x: status_order.get(x["status"], 4))

        response = list_response(table_statuses, total=len(table_statuses), limit=None, offset=None)
        response["data"]["accuracy_check"] = accuracy
        response["data"]["last_check"] = latest_ts.isoformat() if latest_ts else None
        response["data"]["summary"] = {
            "critical": severity_counts["critical"],
            "errors": severity_counts["error"],
            "warnings": severity_counts["warn"],
            "healthy": severity_counts["healthy"],
            "total_tables_checked": len(tables_dict),
        }
        return response
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "check data quality")
        logger.error(f"Failed to check data quality: {error_type} - {message}")
        return error_response(code, error_type, message)


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
            completion_float = float(completion_pct) if isinstance(completion_pct, (int, float, str)) else 0
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
        enriched_rows = []
        for row in loader_rows:
            tbl_name = row.get("table_name")
            needs_refresh = row.get("row_count") is None or row.get("last_updated") is None

            if needs_refresh and tbl_name:
                try:
                    # Query timestamp column name - varies by table
                    ts_columns = {
                        "algo_positions": "entry_date",
                        "algo_trades": "entry_date",
                        "algo_reconciliation_log": "reconciliation_date",
                        "algo_signals": "signal_date",
                        "circuit_breaker_status": "check_date",
                        "algo_performance_daily": "report_date",
                        "algo_portfolio_snapshots": "snapshot_date",
                        "algo_risk_daily": "report_date",
                        "algo_metrics_daily": "report_date",
                        "equity_curve_daily": "date",
                        "growth_metrics": "report_date",
                        "algo_orchestrator_runs": "updated_at",
                    }
                    # Default to updated_at for tables that track update timestamps
                    # Many tables use updated_at instead of created_at
                    ts_col = ts_columns.get(tbl_name, "updated_at")

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

            if row_count is None or row_count == 0:
                status = "empty"
            elif freshness_reference is None:
                status = "empty"
            else:
                data_date = freshness_reference.date() if hasattr(freshness_reference, "date") else freshness_reference

                # Calculate elapsed time for all tables (used below for both daily and weekly/biweekly)
                utc_result_for_age = normalize_to_utc_datetime(freshness_reference, naive_tz)
                age_hours = None
                if isinstance(utc_result_for_age, datetime):
                    age_hours = (datetime.now(timezone.utc) - utc_result_for_age).total_seconds() / 3600

                if max_age <= 1:
                    # Daily tables: use elapsed-time thresholds to match monitor_data_staleness.py
                    # This fixes false-positive "OK" for data from yesterday that's 40+ hours old.
                    # Thresholds: fresh <24h, stale 24-48h, critical >48h (see CLAUDE.md)
                    if age_hours is not None:
                        # Use elapsed time for accurate freshness
                        if age_hours > 48:
                            status = "critical"  # Will be override to "error" below if critical table
                        elif age_hours > 24:
                            status = "stale"
                        else:
                            status = "ok"
                    else:
                        # Fallback to date-only comparison if elapsed time unavailable
                        status = "stale" if data_date < expected_date else "ok"
                else:
                    # Weekly/biweekly tables: use simple calendar-day age threshold
                    status = "stale" if (today - data_date).days > max_age else "ok"

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
                if status_lower == "failed":
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
                            completion_float = (
                                float(completion_pct_raw) if isinstance(completion_pct_raw, (int, float, str)) else 0
                            )
                            if elapsed_seconds > 1800 and completion_float < 5:  # >30 min, <5% done
                                status = "error"  # Treat stuck runners as error
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
        loaders_with_errors = [
            (r.get("consecutive_failures") or 0, r.get("table_name"))
            for r in enriched_rows
            if isinstance(r.get("consecutive_failures"), (int, float)) and r.get("consecutive_failures") >= 1
        ]
        total_failure_count = sum(r[0] for r in loaders_with_errors)
        summary["loaders_with_errors"] = len(loaders_with_errors)
        summary["total_loader_failures"] = int(total_failure_count)

        # CRITICAL: Data freshness alone does not mean trading is actually authorized.
        # The circuit breaker (Phase 2) can halt entries for reasons unrelated to data
        # staleness (e.g. portfolio drawdown >= 20%) - ready_to_trade must reflect that,
        # or the dashboard shows a contradictory "READY TO TRADE" checkmark right next to
        # an orchestrator panel reporting HALTED. Use the most recent orchestrator run's
        # halt state as the authoritative "is trading currently permitted" signal.
        trading_halted = False
        trading_halt_reason = None
        trading_halt_at = None
        try:
            cur.execute("""
                SELECT overall_status, halt_reason, started_at
                FROM algo_orchestrator_runs
                ORDER BY started_at DESC
                LIMIT 1
            """)
            latest_run_row = cur.fetchone()
            if latest_run_row:
                latest_run_dict = safe_dict_convert(latest_run_row)
                run_status = latest_run_dict.get("overall_status")
                if run_status is None:
                    logger.error(
                        "[DATA_STATUS] CRITICAL: Orchestrator run record missing overall_status field. "
                        "Database schema mismatch or corrupt record. Cannot determine trading halt state."
                    )
                    raise ValueError("Orchestrator run status query returned row without overall_status field")
                run_status = str(run_status).lower()
                if run_status in ("halted", "error"):
                    trading_halted = True
                    trading_halt_reason = latest_run_dict.get("halt_reason")
                    # Surfaced so the dashboard can show how old this halt record is - a halt
                    # reason from a bug that's since been fixed in code still shows as the
                    # "current" halt until a newer run record supersedes it, and without a
                    # timestamp there's no way for an operator to tell a live blocker from a
                    # stale one (confirmed live 2026-08-16: a halt reason for an already-fixed
                    # bug sat as the latest row for hours with no fresher run to replace it).
                    started_at_val = latest_run_dict.get("started_at")
                    trading_halt_at = started_at_val.isoformat() if hasattr(started_at_val, "isoformat") else None
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
            cur.execute("""
                SELECT COUNT(*) as sync_count,
                       MAX(reconciliation_date) as latest_sync,
                       AVG(CAST(match_percentage AS FLOAT)) as avg_match_pct
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
            cur.execute("""
                SELECT COUNT(*) as snapshot_count,
                       MAX(snapshot_date) as latest_date,
                       MAX(total_portfolio_value) as latest_value
                FROM algo_portfolio_snapshots
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


def _normalize_market_health(mh: dict[str, Any]) -> Any:
    """Validate and normalize market_health dict. Fails fast if critical fields missing or invalid.

    Critical fields (halt circuit breaker): vix_level, market_stage, market_trend
    CRITICAL: vix_level must be numeric > 0 (VIX is never negative or zero)
    """
    critical_fields = {"vix_level", "market_stage", "market_trend"}
    missing = critical_fields - {k for k in mh.keys() if mh[k] is not None}
    if missing:
        raise ValueError(f"Market health missing critical fields: {missing}")

    # Validate VIX level is > 0 (invalid data would be <= 0)
    vix_raw = mh.get("vix_level")
    try:
        vix_level = float(vix_raw) if vix_raw is not None else None
        if vix_level is not None and vix_level <= 0:
            raise ValueError(f"VIX level must be > 0, got {vix_level}")
    except (TypeError, ValueError) as e:
        raise ValueError(f"VIX level validation failed: {e} (got {type(vix_raw).__name__}: {vix_raw})") from e

    # Validate data_unavailable markers are present (fail-fast if missing)
    data_unavailable_markers = {
        "put_call_ratio_data_unavailable",
        "yield_curve_data_unavailable",
        "fed_rate_data_unavailable",
    }
    missing_markers = data_unavailable_markers - {k for k in mh.keys() if k in data_unavailable_markers}
    if missing_markers:
        logger.error(
            f"[MARKET HEALTH VALIDATION] CRITICAL: Missing data_unavailable markers: {missing_markers}. "
            f"Market health dict missing required fields for data availability tracking. "
            f"Check: market_health_daily table schema and loader that populates put_call_ratio_data_unavailable, "
            f"yield_curve_data_unavailable, fed_rate_data_unavailable. "
            f"Without these markers, API cannot accurately report data availability to clients."
        )
        raise ValueError(
            f"Market health missing required data_unavailable markers: {missing_markers}. "
            f"Cannot determine which optional fields are truly unavailable."
        )

    # Extract optional enrichment fields explicitly (fail if type is wrong, allow None if missing)
    market_trend = mh.get("market_trend")
    market_stage = mh.get("market_stage")
    up_volume_pct = get_optional_field(mh, "up_volume_percent")
    ad_ratio = get_optional_field(mh, "advance_decline_ratio")
    new_highs = get_optional_field(mh, "new_highs_count")
    new_lows = get_optional_field(mh, "new_lows_count")
    breadth_10d = get_optional_field(mh, "breadth_momentum_10d")
    put_call = get_optional_field(mh, "put_call_ratio")
    put_call_unavailable_reason = get_optional_field(mh, "put_call_ratio_unavailable_reason")
    yield_curve = get_optional_field(mh, "yield_curve_slope")
    yield_curve_unavailable_reason = get_optional_field(mh, "yield_curve_unavailable_reason")
    fed_rate_env = get_optional_field(mh, "fed_rate_environment")
    fed_rate_unavailable_reason = get_optional_field(mh, "fed_rate_unavailable_reason")
    spy_change = get_optional_field(mh, "spy_change_pct")

    return {
        "market_trend": market_trend,
        "market_stage": market_stage,
        "vix_level": vix_level,
        "up_volume_percent": up_volume_pct,
        "advance_decline_ratio": ad_ratio,
        "new_highs_count": new_highs,
        "new_lows_count": new_lows,
        "breadth_momentum_10d": breadth_10d,
        "put_call_ratio": put_call,
        "put_call_ratio_data_unavailable": mh["put_call_ratio_data_unavailable"],
        "put_call_ratio_unavailable_reason": put_call_unavailable_reason,
        "yield_curve_slope": yield_curve,
        "yield_curve_data_unavailable": mh["yield_curve_data_unavailable"],
        "yield_curve_unavailable_reason": yield_curve_unavailable_reason,
        "fed_rate_environment": fed_rate_env,
        "fed_rate_data_unavailable": mh["fed_rate_data_unavailable"],
        "fed_rate_unavailable_reason": fed_rate_unavailable_reason,
        "spy_change_pct": spy_change,
    }


def _normalize_exposure(exp: dict[str, Any]) -> Any:
    """Validate and normalize exposure dict. Fails fast if critical fields missing or invalid type.

    Critical fields (position sizing, trading halts): exposure_pct, regime
    CRITICAL: exposure_pct must be numeric 0-100, regime must be string (not "unknown" or "")
    """
    critical_fields = {"exposure_pct", "regime"}
    missing = critical_fields - {k for k in exp.keys() if exp[k] is not None}
    if missing:
        raise ValueError(f"Market exposure missing critical fields: {missing}")

    # Type and range validation for exposure_pct (AWS position sizing depends on this)
    exposure_pct_raw = exp.get("exposure_pct")
    if exposure_pct_raw is None:
        raise ValueError("exposure_pct is required but missing")
    try:
        exposure_pct = float(exposure_pct_raw)
        # BUG FOUND 2026-08-10 (NaN-comparison-guard class): `<0`/`>100` never catch NaN
        # (NaN comparisons are always False in Python) - this function's own docstring says
        # "AWS position sizing depends on this", so a NaN would have passed as "valid".
        if math.isnan(exposure_pct) or math.isinf(exposure_pct) or exposure_pct < 0 or exposure_pct > 100:
            raise ValueError(f"exposure_pct {exposure_pct} outside valid range [0,100]")
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"exposure_pct type/range validation failed: {e} "
            f"(got {type(exposure_pct_raw).__name__}: {exposure_pct_raw})"
        ) from e

    # Validate regime is not "unknown" or empty string
    regime = exp.get("regime")
    if not regime or regime == "unknown" or regime == "":
        raise ValueError(
            f"Market exposure regime is invalid: '{regime}'. "
            f"Must be one of: confirmed_uptrend, uptrend_under_pressure, caution, correction"
        )
    if regime not in ("confirmed_uptrend", "uptrend_under_pressure", "caution", "correction"):
        raise ValueError(f"Market exposure regime '{regime}' not recognized")

    halt_reasons = get_optional_field(exp, "halt_reasons", default=[])
    return {
        "exposure_pct": exposure_pct,
        "regime": regime,
        "halt_reasons": halt_reasons if halt_reasons is not None else [],
        "distribution_days": exp.get("distribution_days"),
    }


@db_route_handler("get market")
@validate_api_response("mkt")
def _get_market(cur: cursor) -> Any:
    try:
        cur.execute("SET LOCAL statement_timeout = '8000ms'")

        # CRITICAL: Fetch market health; fail fast if unavailable
        # Include data_unavailable markers for optional enrichment fields so API can signal
        # which fields are truly unavailable vs. present in the response
        # Skip non-trading days (weekends/holidays) to get last valid trading day's data
        # Filter out NULL vix_level to skip incomplete records from non-trading days
        cur.execute("""
            SELECT market_trend, market_stage, vix_level,
                   up_volume_percent, advance_decline_ratio, new_highs_count,
                   new_lows_count, breadth_momentum_10d, put_call_ratio,
                   put_call_ratio_data_unavailable, put_call_ratio_unavailable_reason,
                   yield_curve_slope, yield_curve_data_unavailable, yield_curve_unavailable_reason,
                   fed_rate_environment, fed_rate_data_unavailable, fed_rate_unavailable_reason,
                   spy_change_pct
            FROM market_health_daily
            WHERE vix_level IS NOT NULL
            ORDER BY date DESC LIMIT 1
        """)
        mh = cur.fetchone()
        if not mh:
            return error_response(503, "data_unavailable", "Market health data unavailable")
        mh_raw = safe_json_serialize(safe_dict_convert(mh))
        market_health = _normalize_market_health(mh_raw)

        # CRITICAL: Fetch exposure data; fail fast if unavailable
        # Skip non-trading days (weekends/holidays) to get last valid trading day's data
        cur.execute("""
            SELECT exposure_pct, regime, halt_reasons, distribution_days
            FROM market_exposure_daily
            WHERE date <= CURRENT_DATE
            ORDER BY date DESC LIMIT 1
        """)
        exp = cur.fetchone()
        if not exp:
            return error_response(503, "data_unavailable", "Market exposure data unavailable")
        exp_raw = safe_json_serialize(safe_dict_convert(exp))
        exposure = _normalize_exposure(exp_raw)

        # Parse JSON strings from database (halt_reasons is stored as JSON text)
        if exposure["halt_reasons"]:
            try:
                exposure["halt_reasons"] = (
                    json.loads(exposure["halt_reasons"])
                    if isinstance(exposure["halt_reasons"], str)
                    else exposure["halt_reasons"]
                )
            except (json.JSONDecodeError, TypeError):
                exposure["halt_reasons"] = []

        # CRITICAL: Fetch SPY close price; fail fast if unavailable
        cur.execute("""
            SELECT close FROM price_daily
            WHERE symbol = 'SPY'
            ORDER BY date DESC LIMIT 1
        """)
        spy_row = cur.fetchone()
        if not spy_row:
            return error_response(503, "data_unavailable", "SPY price data unavailable")
        spy_row = safe_dict_convert(spy_row)
        if spy_row.get("close") is None:
            return error_response(503, "data_unavailable", "SPY price data unavailable")
        spy_close = float(spy_row["close"])

        # Handle optional/enrichment fields that may be None (breadth data, sentiment, macro indicators)
        uv_val = market_health.get("up_volume_percent")
        adr_val = market_health.get("advance_decline_ratio")
        nh_val = market_health.get("new_highs_count")
        nl_val = market_health.get("new_lows_count")
        pcr_val = market_health.get("put_call_ratio")
        bm_val = market_health.get("breadth_momentum_10d")
        ycs_val = market_health.get("yield_curve_slope")
        spy_chg_val = market_health.get("spy_change_pct")

        # When today's put/call ratio genuinely has no fresh value (common pre-market: SPY
        # options open interest is a lagging figure and often reads 0 before the session
        # gets going), surface the last day it WAS available instead of leaving the dashboard
        # with nothing to show at all. Same lookback pattern already used for the same column
        # in algo/risk/market_factor_calculator.py - only ever reads a row explicitly NOT
        # flagged unavailable, so a failed-fetch value that was never cleared from the column
        # can't leak through as if it were real (that's the specific bug this pattern guards
        # against, per the comment on put_call_ratio_data_unavailable below). Does not change
        # put_call_ratio/put_call_ratio_data_unavailable themselves - those keep truthfully
        # reporting "no fresh value today" so any consumer trusting that flag is unaffected.
        pcr_stale_val = None
        pcr_stale_date = None
        if pcr_val is None:
            cur.execute("""
                SELECT date, put_call_ratio FROM market_health_daily
                WHERE put_call_ratio IS NOT NULL AND put_call_ratio_data_unavailable IS NOT TRUE
                ORDER BY date DESC LIMIT 1
            """)
            stale_row = cur.fetchone()
            if stale_row:
                stale_row = safe_dict_convert(stale_row)
                pcr_stale_val = stale_row.get("put_call_ratio")
                pcr_stale_date = stale_row.get("date")

        # Convert to appropriate types, allowing None for optional/enrichment fields
        # Include data_unavailable markers so frontend knows which fields are truly unavailable
        data = {
            "exposure_pct": float(exposure["exposure_pct"]),
            "regime": exposure["regime"],
            "halt_reasons": exposure["halt_reasons"],
            "vix_level": float(market_health["vix_level"]),
            "market_stage": int(market_health["market_stage"]),
            "market_trend": market_health["market_trend"],
            "distribution_days_4w": int(exposure["distribution_days"]),
            "spy_close": spy_close,
            "spy_change_pct": float(spy_chg_val) if spy_chg_val is not None else None,
            "up_volume_percent": float(uv_val) if uv_val is not None else None,
            "advance_decline_ratio": float(adr_val) if adr_val is not None else None,
            "new_highs_count": int(nh_val) if nh_val is not None else None,
            "new_lows_count": int(nl_val) if nl_val is not None else None,
            "put_call_ratio": float(pcr_val) if pcr_val is not None else None,
            # Trust the loader's own put_call_ratio_data_unavailable column (already normalized
            # above by _normalize_market_health) instead of re-deriving from NULL-ness - the two
            # can diverge, and the same re-derive-from-NULL anti-pattern already caused a real
            # stale-value bug elsewhere in this codebase (see algo/risk/market_factor_calculator.py).
            "put_call_ratio_data_unavailable": market_health["put_call_ratio_data_unavailable"],
            "put_call_ratio_stale_value": float(pcr_stale_val) if pcr_stale_val is not None else None,
            "put_call_ratio_stale_date": str(pcr_stale_date) if pcr_stale_date is not None else None,
            "put_call_ratio_unavailable_reason": (
                market_health.get("put_call_ratio_unavailable_reason")
                if market_health["put_call_ratio_data_unavailable"]
                else None
            ),
            "breadth_momentum_10d": float(bm_val) if bm_val is not None else None,
            "yield_curve_slope": float(ycs_val) if ycs_val is not None else None,
            "yield_curve_data_unavailable": market_health["yield_curve_data_unavailable"],
            "yield_curve_unavailable_reason": (
                market_health.get("yield_curve_unavailable_reason")
                if market_health["yield_curve_data_unavailable"]
                else None
            ),
            "fed_rate_environment": market_health.get("fed_rate_environment"),
            # CRITICAL FIX: Explicitly check if fed_rate_data_unavailable is True (not False default).
            # Do NOT silently default to False if field is missing - that masks data quality issues.
            # Consistency: Put_call_ratio and yield_curve use explicit None checks, apply same pattern here.
            "fed_rate_data_unavailable": market_health.get("fed_rate_data_unavailable"),
            "fed_rate_unavailable_reason": (
                market_health.get("fed_rate_unavailable_reason")
                if market_health.get("fed_rate_data_unavailable")
                else None
            ),
        }

        return json_response(200, data)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Failed to fetch market: {type(e).__name__}: {e}\n  Operation: Query market_health_daily with date filter\n  Endpoint: GET /api/algo/market"
        )
        return error_response(503, "service_unavailable", "Failed to fetch market data")


@db_route_handler("get market factors")
def _get_market_factors(cur: cursor) -> Any:
    logger.debug("[MARKET_FACTORS] Function called - no validation decorator")
    try:
        cur.execute("SET LOCAL statement_timeout = '8000ms'")

        # Fetch exposure factors from market_exposure_daily
        cur.execute("""
            SELECT exposure_pct, raw_score, regime, factors
            FROM market_exposure_daily
            ORDER BY date DESC LIMIT 1
        """)
        row = cur.fetchone()

        if not row:
            return error_response(503, "data_unavailable", "Market exposure factors data not yet available")

        data_dict = safe_json_serialize(safe_dict_convert(row))

        # Parse factors if it's a JSON string
        factors = {}
        if data_dict.get("factors"):
            try:
                factors_val = data_dict.get("factors")
                if isinstance(factors_val, str):
                    factors = json.loads(factors_val)
                else:
                    factors = factors_val if isinstance(factors_val, dict) else {}
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"[MARKET_FACTORS] Failed to parse factors: {e}")
                factors = {}

        data = {
            "exposure_pct": format_decimal_string(data_dict.get("exposure_pct"), precision=2, allow_none=True),
            "raw_score": format_decimal_string(data_dict.get("raw_score"), precision=2, allow_none=True),
            "regime": data_dict.get("regime"),
            "factors": factors,
        }

        return json_response(200, data)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Failed to fetch market factors: {type(e).__name__}: {e}\n  Operation: Calculate market exposure factors\n  Endpoint: GET /api/algo/market-factors"
        )
        return error_response(503, "service_unavailable", "Failed to fetch market factors")


@db_route_handler("get market sentiment")
@validate_api_response("mkt")
def _get_market_sentiment(cur: cursor) -> Any:
    # market_sentiment view provides: date, fear_greed_index, label, put_call_ratio, vix, sentiment_score.
    # bullish/bearish/neutral breakdown is not available in this view (AAII survey data lives in
    # aaii_sentiment instead) - only sentiment_score is used below.
    cur.execute("""
        SELECT sentiment_score, date
        FROM market_sentiment
        ORDER BY date DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    if not row:
        return error_response(503, "no_data", "Market sentiment data not yet available")

    row = safe_dict_convert(row)

    if row.get("sentiment_score") is None:
        return error_response(503, "incomplete_data", "Market sentiment data incomplete")

    sentiment_score = float(row["sentiment_score"])
    bullish = None  # Not available in market_sentiment view
    bearish = None  # Not available in market_sentiment view
    neutral = None  # Not available in market_sentiment view

    trend = None
    if sentiment_score is not None:
        if sentiment_score > 60:
            trend = "BULLISH"
        elif sentiment_score > 40:
            trend = "NEUTRAL"
        else:
            trend = "BEARISH"

    return json_response(
        200,
        {
            # sentiment_score is validated non-None above; an extreme-bearish reading of
            # exactly 0 must not be hidden as "unavailable" by a falsy check.
            "sentiment": round(sentiment_score, 2),
            "trend": trend,
            "bullish_pct": round(bullish, 1) if bullish else None,
            "bearish_pct": round(bearish, 1) if bearish else None,
            "neutral_pct": round(neutral, 1) if neutral else None,
        },
    )


@db_route_handler("get markets")
@validate_api_response("mkt")
def _get_markets(cur: cursor) -> Any:  # noqa: C901
    try:
        # Latest exposure row (skip non-trading days to get last valid trading day)
        cur.execute("""
                SELECT date, exposure_pct, raw_score, regime, factors, halt_reasons, distribution_days
                FROM market_exposure_daily
                WHERE date <= CURRENT_DATE
                ORDER BY date DESC
                LIMIT 1
            """)
        row = cur.fetchone()

        if not row:
            return error_response(503, "data_unavailable", "Market exposure data not yet available")

        row = safe_json_serialize(safe_dict_convert(row))

        halt_reasons = []
        if row.get("halt_reasons"):
            try:
                halt_reasons = (
                    json.loads(row["halt_reasons"]) if isinstance(row["halt_reasons"], str) else row["halt_reasons"]
                )
            except (json.JSONDecodeError, TypeError):
                halt_reasons = []

        factors = {}
        if row.get("factors"):
            try:
                factors_val = json.loads(row["factors"]) if isinstance(row["factors"], str) else row["factors"]
                factors = factors_val if isinstance(factors_val, dict) else {}
            except (json.JSONDecodeError, TypeError):
                factors = {}

        regime_val = row.get("regime")
        if regime_val is None or regime_val == "":
            logger.error(
                f"[MARKETS API] CRITICAL: market regime is missing or empty for {row.get('date')}. "
                f"Cannot determine risk tier for position sizing (affects exposure caps 25-100%). "
                f"Check: market_exposure_daily table, load_market_exposure_daily logs."
            )
            return error_response(
                503,
                "data_unavailable",
                "Market regime data unavailable - cannot determine risk tier for position sizing",
            )
        tier_key = str(regime_val).lower()
        tier_conf = _TIER_CONFIG.get(tier_key)
        if tier_conf is None:
            logger.error(
                f"[MARKETS API] CRITICAL: No tier configuration for regime '{tier_key}'. "
                f"Regime value from market_exposure_daily does not map to TIER_CONFIG. "
                f"Database or configuration mismatch."
            )
            return error_response(
                503,
                "data_unavailable",
                f"Unknown market regime '{tier_key}' - cannot apply risk tier constraints",
            )
        active_tier = {"name": tier_key, **tier_conf}
        if "halt" not in tier_conf:
            logger.error(
                f"[MARKETS API] Tier config for '{tier_key}' missing 'halt' field. "
                f"Configuration incomplete-cannot determine entry eligibility rules."
            )
            return error_response(
                500,
                "configuration_error",
                f"Tier configuration incomplete for '{tier_key}'",
            )
        active_tier["halt"] = bool(halt_reasons) or tier_conf["halt"]

        # History: last 90 sessions for ExposureHistory chart (skip non-trading days)
        history = []
        history_data_unavailable = False
        try:
            cur.execute("""
                    SELECT date, exposure_pct, regime, distribution_days
                    FROM market_exposure_daily
                    WHERE date <= CURRENT_DATE
                    ORDER BY date DESC
                    LIMIT 90
                """)
            for h in cur.fetchall():
                try:
                    h = safe_json_serialize(safe_dict_convert(h))
                    d = h.get("date")
                    history.append(
                        {
                            "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                            "exposure_pct": (float(h["exposure_pct"]) if h.get("exposure_pct") is not None else None),
                            "regime": h.get("regime"),
                            "distribution_days": h.get("distribution_days"),
                        }
                    )
                except Exception as hist_err:
                    logger.error(
                        f"[MARKETS_API] Failed to parse history item: {hist_err}. Marking history unavailable."
                    )
                    history_data_unavailable = True
                    break
        except Exception as h_err:
            logger.error(f"[MARKETS_API] Failed to fetch market history: {h_err}. History data unavailable.")
            history_data_unavailable = True

        # Sector rankings for SectorRotationMap
        sectors = []
        sectors_data_unavailable = False
        try:
            cur.execute("""
                    SELECT sector_name AS name, current_rank AS rank, rank_4w_ago, momentum_score AS momentum
                    FROM sector_ranking
                    WHERE date = (SELECT MAX(date) FROM sector_ranking)
                    ORDER BY current_rank ASC NULLS LAST
                """)
            for sr in cur.fetchall():
                try:
                    sr = safe_json_serialize(safe_dict_convert(sr))
                    sectors.append(
                        {
                            "name": sr.get("name"),
                            "rank": sr.get("rank"),
                            "rank_4w_ago": sr.get("rank_4w_ago"),
                            "momentum": (float(sr["momentum"]) if sr.get("momentum") is not None else None),
                        }
                    )
                except Exception as item_err:
                    logger.error(f"[MARKETS_API] Failed to parse sector item: {item_err}. Marking sectors unavailable.")
                    sectors_data_unavailable = True
                    break
        except Exception as se:
            logger.error(f"[MARKETS_API] Failed to fetch sector rankings: {se}. Sectors data unavailable.")
            sectors_data_unavailable = True

        # Fetch market health from market_health_daily for dashboard KPIs
        # Skip today if it's not a trading day (Saturday/Sunday or holiday)
        # Markets only have valid data on trading days
        market_health = {}
        try:
            cur.execute("""
                    SELECT date, market_trend, market_stage, vix_level, spy_change_pct,
                           up_volume_percent, advance_decline_ratio, new_highs_count,
                           new_lows_count, breadth_momentum_10d, put_call_ratio,
                           put_call_ratio_data_unavailable, put_call_ratio_unavailable_reason,
                           yield_curve_slope, yield_curve_data_unavailable, yield_curve_unavailable_reason,
                           fed_rate_environment
                    FROM market_health_daily
                    WHERE date <= CURRENT_DATE AND vix_level IS NOT NULL
                    ORDER BY date DESC LIMIT 1
                """)
            mh_row = cur.fetchone()
            if not mh_row:
                return error_response(
                    503,
                    "data_unavailable",
                    "Market health data not available (market_health_daily has no rows with valid VIX)",
                )
            market_health = safe_json_serialize(safe_dict_convert(mh_row))

            # VIX is guaranteed non-NULL from query filter (WHERE vix_level IS NOT NULL)
            vix_val = market_health.get("vix_level")
            if vix_val is None:
                logger.error(
                    "[MARKETS API] CRITICAL BUG: Query filtered for vix_level IS NOT NULL but got NULL. "
                    "This should never happen - indicates database or query logic error."
                )
                raise ValueError(
                    "Market health VIX validation failed (query logic error). Check API query and database state."
                )

            # Validate VIX is numeric and > 0 (VIX is never zero or negative)
            try:
                vix_float = float(vix_val)
                # BUG FOUND 2026-08-10 (NaN-comparison-guard class): `vix_float <= 0` never
                # caught NaN/Inf (always False in Python) - the raise below silently never
                # fired for a NaN VIX, so this try block "succeeded" and a NaN VIX (this
                # dashboard's own docstring: "critical for position sizing") reached the
                # caller unvalidated.
                if math.isnan(vix_float) or math.isinf(vix_float) or vix_float <= 0:
                    raise ValueError(
                        f"VIX {vix_float} is invalid (must be > 0 and finite). Data quality issue in market_health_daily."
                    )
            except (ValueError, TypeError) as e:
                logger.error(
                    f"[MARKETS API] CRITICAL: VIX validation failed: {e}. "
                    f"Cannot parse VIX value: {vix_val} ({type(vix_val).__name__}). "
                    f"Market health validation requires numeric VIX > 0."
                )
                raise ValueError(f"VIX data invalid: {e}") from e

            pcr_val = market_health.get("put_call_ratio")
            pcr_stale_val = None
            pcr_stale_date = None
            if pcr_val is None and market_health.get("put_call_ratio_data_unavailable"):
                cur.execute("""
                    SELECT date, put_call_ratio FROM market_health_daily
                    WHERE put_call_ratio IS NOT NULL AND put_call_ratio_data_unavailable IS NOT TRUE
                    ORDER BY date DESC LIMIT 1
                """)
                stale_row = cur.fetchone()
                if stale_row:
                    stale_row = safe_dict_convert(stale_row)
                    pcr_stale_val = stale_row.get("put_call_ratio")
                    pcr_stale_date = stale_row.get("date")
                    if pcr_stale_val is not None:
                        try:
                            pcr_stale_val = float(pcr_stale_val)
                        except (ValueError, TypeError):
                            pcr_stale_val = None
                            pcr_stale_date = None
            market_health["put_call_ratio_stale_value"] = pcr_stale_val
            market_health["put_call_ratio_stale_date"] = str(pcr_stale_date) if pcr_stale_date else None

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as mhe:
            logger.error(f"CRITICAL: Failed to fetch market_health_daily: {mhe}")
            return error_response(
                503,
                "data_unavailable",
                f"Market health unavailable: {type(mhe).__name__}",
            )
        except ValueError as ve:
            logger.error(f"[MARKETS API] Market health validation failed: {ve}")
            return error_response(
                503,
                "data_unavailable",
                str(ve),
            )

        # Fetch latest SPY close for dashboard header (critical for position sizing)
        spy_close = None
        try:
            cur.execute("""
                SELECT close FROM price_daily
                WHERE symbol = 'SPY'
                ORDER BY date DESC LIMIT 1
            """)
            spy_row = cur.fetchone()
            if not spy_row:
                return error_response(503, "data_unavailable", "SPY price data not available")
            spy_row = safe_dict_convert(spy_row)
            if spy_row.get("close") is None:
                return error_response(503, "data_unavailable", "SPY price data not available")
            spy_close = float(spy_row["close"])
            # CRITICAL: Validate SPY price is reasonable (> 0)
            # BUG FOUND 2026-08-10 (NaN-comparison-guard class): `spy_close <= 0` never
            # caught NaN/Inf (always False in Python).
            if math.isnan(spy_close) or math.isinf(spy_close) or spy_close <= 0:
                logger.error(
                    f"[MARKETS API] Invalid SPY close: {spy_close} <= 0. Data quality issue in price_daily table."
                )
                return error_response(503, "data_unavailable", f"Invalid SPY price data: {spy_close}")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as spy_e:
            logger.error(f"CRITICAL: Failed to fetch SPY price: {spy_e}")
            return error_response(
                503,
                "data_unavailable",
                f"SPY price unavailable: {type(spy_e).__name__}",
            )

        current_date = row.get("date")

        # Validate vix_regime is present in factors; fail-fast if missing (critical market signal)
        if "vix_regime" not in factors or factors.get("vix_regime") is None:
            error_msg = (
                f"vix_regime missing/null in factors for {current_date}: "
                f"market exposure computation has not completed successfully. "
                f"Check market_exposure_daily table and load_market_exposure_daily logs."
            )
            logger.error(f"[MARKETS API] {error_msg}")
            return error_response(503, "data_unavailable", error_msg)

        # distribution_days is a key market factor; fail-fast if missing
        try:
            dist_days_raw = row.get("distribution_days")
            if dist_days_raw is None:
                raise ValueError(
                    f"distribution_days missing from market_exposure_daily for {current_date}. "
                    f"Market exposure computation has not completed successfully. "
                    f"Check market_exposure_daily table and load_market_exposure_daily logs."
                )
        except ValueError as e:
            logger.error(f"[MARKETS API] Market data validation failed: {e}")
            return error_response(503, "data_unavailable", str(e))

        response_data = {
            "exposure_pct": (float(row["exposure_pct"]) if row.get("exposure_pct") is not None else None),
            "raw_score": (float(row["raw_score"]) if row.get("raw_score") is not None else None),
            "regime": row.get("regime"),
            "halt_reasons": halt_reasons,
            "distribution_days": int(dist_days_raw) if isinstance(dist_days_raw, (int, float)) else dist_days_raw,
            "factors": factors,
            "spy_close": spy_close,
            "date": (current_date.isoformat() if hasattr(current_date, "isoformat") else str(current_date)),
        }

        # Include spy_close in market_health as well (required by dashboard fetcher)
        market_health["spy_close"] = spy_close

        # Set put_call_ratio/yield_curve availability flags for dashboard fetcher.
        # Trust the loader's own *_data_unavailable columns (now selected above) rather than
        # re-deriving from NULL-ness - the two can diverge, and the same re-derive-from-NULL
        # anti-pattern already caused a real stale-value bug elsewhere in this codebase (see
        # algo/risk/market_factor_calculator.py). Only fall back to NULL-inference if the column
        # itself is missing (nullable, defaults to false, but be defensive for older rows).
        if market_health.get("put_call_ratio_data_unavailable") is None:
            market_health["put_call_ratio_data_unavailable"] = market_health.get("put_call_ratio") is None
        if market_health.get("yield_curve_data_unavailable") is None:
            market_health["yield_curve_data_unavailable"] = market_health.get("yield_curve_slope") is None

        # Build response with market data (not a list response)
        # Contract requires: spy_close, vix_level (required), plus optional market data fields
        vix_level = market_health.get("vix_level")
        response: dict[str, object] = {
            "statusCode": 200,
            "data": {
                "spy_close": spy_close,
                "vix_level": float(vix_level) if vix_level is not None else None,
                "current": response_data,
                "active_tier": active_tier,
                "history": history,
                "history_data_unavailable": history_data_unavailable,
                "sectors": sectors,
                "sectors_data_unavailable": sectors_data_unavailable,
                "market_health": market_health,
                # Add breadth indicators at top level
                "adr": (
                    float(market_health.get("advance_decline_ratio"))
                    if market_health.get("advance_decline_ratio") is not None
                    else None
                ),
                "nh": (
                    int(market_health.get("new_highs_count"))
                    if market_health.get("new_highs_count") is not None
                    else None
                ),
                "nl": (
                    int(market_health.get("new_lows_count"))
                    if market_health.get("new_lows_count") is not None
                    else None
                ),
                "pcr": (
                    float(market_health.get("put_call_ratio"))
                    if market_health.get("put_call_ratio") is not None
                    else None
                ),
            },
        }

        # Add additional market indicators at top level
        data = cast(dict[str, Any], response["data"])
        data["bmom"] = (
            float(market_health.get("breadth_momentum_10d"))
            if market_health.get("breadth_momentum_10d") is not None
            else None
        )
        data["ycs"] = (
            float(market_health.get("yield_curve_slope"))
            if market_health.get("yield_curve_slope") is not None
            else None
        )
        data["fed"] = market_health.get("fed_rate_environment")

        return json_response(200, data)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        import traceback

        error_trace = traceback.format_exc()
        logger.error(
            f"[MARKETS_HANDLER_ERROR] Failed to fetch markets: {type(e).__name__}: {e}\n"
            f"  Operation: Query market_exposure_daily\n"
            f"  Endpoint: GET /api/algo/markets\n"
            f"  Full Traceback:\n{error_trace}"
        )
        return error_response(
            503, "service_unavailable", f"Failed to fetch markets data: {type(e).__name__}: {str(e)[:100]}"
        )


@db_route_handler("get trend criteria")
@validate_api_response("mkt")
def _get_trend_criteria(cur: cursor) -> Any:
    cur.execute("""
        SELECT
            COUNT(*) as total_symbols,
            COUNT(*) FILTER (WHERE price_above_sma50 = true) as above_sma50,
            COUNT(*) FILTER (WHERE sma50_above_sma200 = true) as sma50_above_sma200,
            COUNT(*) FILTER (WHERE price_above_sma200 = true) as above_sma200,
            COUNT(*) FILTER (WHERE weinstein_stage = 2) as stage2
        FROM trend_template_data
        WHERE date = (SELECT MAX(date) FROM trend_template_data)
    """)
    row = cur.fetchone()
    if not row:
        return error_response(503, "no_data", "Trend template data not yet available")
    row = safe_dict_convert(row)
    if "total_symbols" not in row or row["total_symbols"] is None:
        return error_response(503, "no_data", "Trend template data not yet available")
    total_symbols_val = row["total_symbols"]
    if int(total_symbols_val) == 0:
        return error_response(503, "no_data", "Trend template data not yet available")

    total_symbols = int(row["total_symbols"])
    criteria = [
        {
            "name": "Price Above 50-Day MA",
            "passing": int(row["above_sma50"]),
            "total": total_symbols,
        },
        {
            "name": "50-Day Above 200-Day MA",
            "passing": int(row["sma50_above_sma200"]),
            "total": total_symbols,
        },
        {
            "name": "Price Above 200-Day MA",
            "passing": int(row["above_sma200"]),
            "total": total_symbols,
        },
        {
            "name": "Stage 2 Uptrend (Weinstein)",
            "passing": int(row["stage2"]),
            "total": total_symbols,
        },
    ]

    return list_response(criteria, total=total_symbols, limit=None, offset=None)


def _is_any_circuit_breaker_triggered(
    metrics: dict[str, Any],
    drawdown_threshold: float,
    daily_loss_threshold: float,
    weekly_loss_threshold: float,
    open_risk_threshold: float,
    vix_threshold: float,
) -> bool:
    """Check if any circuit breaker metric exceeds its configured threshold.

    Args:
        metrics: Dict with keys portfolio_drawdown_pct, daily_loss_pct, weekly_loss_pct,
                open_risk_pct, vix_level
        *_threshold: Configured thresholds from algo_config (absolute values for comparisons)

    Returns:
        True if any metric >= threshold, False if all below thresholds or None.
    """
    if metrics.get("portfolio_drawdown_pct") is not None:
        if float(metrics["portfolio_drawdown_pct"]) >= drawdown_threshold:
            return True
    if metrics.get("daily_loss_pct") is not None:
        if float(metrics["daily_loss_pct"]) >= daily_loss_threshold:
            return True
    if metrics.get("weekly_loss_pct") is not None:
        if float(metrics["weekly_loss_pct"]) >= weekly_loss_threshold:
            return True
    if metrics.get("open_risk_pct") is not None:
        if float(metrics["open_risk_pct"]) >= open_risk_threshold:
            return True
    if metrics.get("vix_level") is not None:
        if float(metrics["vix_level"]) >= vix_threshold:
            return True
    return False


def _collect_phase2_circuit_breakers(cur: cursor, execution_health: dict[str, Any]) -> None:
    """Collect Phase 2 circuit breaker status with thresholds from algo_config.

    CRITICAL: Thresholds MUST come from algo_config (same source the real circuit breaker
    reads), not hardcoded. Dashboard indicator and real halt logic must stay in sync.
    If any threshold key is missing from algo_config, sets execution_health to None
    (unknown status), not a silent "all clear" with a guessed default.
    """
    cur.execute(
        """
        SELECT key, value FROM algo_config
        WHERE key IN ('halt_drawdown_pct', 'max_daily_loss_pct', 'max_weekly_loss_pct',
                      'max_total_risk_pct', 'vix_max_threshold')
        """
    )
    cb_config = {row[0]: row[1] for row in cur.fetchall()}
    required_keys = (
        "halt_drawdown_pct",
        "max_daily_loss_pct",
        "max_weekly_loss_pct",
        "max_total_risk_pct",
        "vix_max_threshold",
    )
    missing_keys = [k for k in required_keys if k not in cb_config]
    if missing_keys:
        logger.warning(f"[HEALTH] Phase 2 algo_config missing keys: {missing_keys}")
        execution_health["phase_2_circuit_breakers"] = None
        return

    drawdown_threshold = abs(float(cb_config["halt_drawdown_pct"]))
    daily_loss_threshold = float(cb_config["max_daily_loss_pct"])
    weekly_loss_threshold = float(cb_config["max_weekly_loss_pct"])
    open_risk_threshold = float(cb_config["max_total_risk_pct"])
    vix_threshold = float(cb_config["vix_max_threshold"])

    cur.execute(
        """
        SELECT portfolio_drawdown_pct, daily_loss_pct, weekly_loss_pct, open_risk_pct,
               vix_level, market_stage, check_date
        FROM circuit_breaker_status
        ORDER BY check_date DESC LIMIT 1
        """
    )
    cb_row = cur.fetchone()
    if cb_row:
        cb_dict = safe_dict_convert(cb_row)
        any_triggered = _is_any_circuit_breaker_triggered(
            cb_dict,
            drawdown_threshold=drawdown_threshold,
            daily_loss_threshold=daily_loss_threshold,
            weekly_loss_threshold=weekly_loss_threshold,
            open_risk_threshold=open_risk_threshold,
            vix_threshold=vix_threshold,
        )

        check_date = cb_dict.get("check_date")
        check_date_str = check_date.isoformat() if check_date and hasattr(check_date, "isoformat") else str(check_date)

        execution_health["phase_2_circuit_breakers"] = {
            "any_triggered": any_triggered,
            "drawdown_pct": (
                float(cb_dict["portfolio_drawdown_pct"]) if cb_dict.get("portfolio_drawdown_pct") is not None else None
            ),
            "daily_loss_pct": (float(cb_dict["daily_loss_pct"]) if cb_dict.get("daily_loss_pct") is not None else None),
            "weekly_loss_pct": (
                float(cb_dict["weekly_loss_pct"]) if cb_dict.get("weekly_loss_pct") is not None else None
            ),
            "open_risk_pct": (float(cb_dict["open_risk_pct"]) if cb_dict.get("open_risk_pct") is not None else None),
            "vix_level": float(cb_dict["vix_level"]) if cb_dict.get("vix_level") is not None else None,
            "last_check": check_date_str,
        }
    else:
        execution_health["phase_2_circuit_breakers"] = None
