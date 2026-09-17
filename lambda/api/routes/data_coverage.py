#!/usr/bin/env python3
"""
API: GET /api/data-coverage

Returns comprehensive data coverage diagnostics:
- Price data freshness
- Technical indicators completeness
- Symbol coverage
- Loader health
- Metric availability

For use in dashboard and automated monitoring.
"""

from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
from psycopg2.extensions import cursor
from routes.utils import (
    error_response,
    execute_with_timeout,
    handle_db_error,
    json_response,
    success_response,
)

from algo.infrastructure.config.sql_intervals import get_interval_sql
from utils.validation import DatabaseResultValidator

logger = logging.getLogger(__name__)


def get_price_coverage(cur: cursor) -> Any:
    try:
        interval_7d = get_interval_sql("7d")
        # coverage_pct is meant to answer "what % of the SP500 has recent price data" -
        # previously divided the FULL active universe's symbol count (total_symbols, ~5400+)
        # by the SP500-only denominator (sp500_total, ~500), producing nonsense values like
        # 1090% (confirmed live 2026-08-03). sp500_symbols_covered scopes the numerator to
        # the same SP500 set as the denominator so the ratio is actually meaningful.
        rows = execute_with_timeout(
            cur,
            f"""
            SELECT
                COUNT(DISTINCT symbol) as total_symbols,
                COUNT(DISTINCT symbol) FILTER (
                    WHERE symbol IN (SELECT symbol FROM stock_symbols WHERE is_sp500 = TRUE)
                ) as sp500_symbols_covered,
                (SELECT COUNT(DISTINCT symbol) FROM stock_symbols WHERE is_sp500 = TRUE) as sp500_total,
                MAX(date) as latest_date,
                COUNT(*) as total_rows,
                COUNT(CASE WHEN volume = 0 OR volume IS NULL THEN 1 END) as zero_volume_rows,
                COUNT(CASE WHEN close <= 0 THEN 1 END) as invalid_price_rows
            FROM price_daily
            WHERE date > NOW() - {interval_7d}
        """,
            timeout_sec=10,
        )

        row = DatabaseResultValidator.safe_get_first_row(rows)
        if row is None:
            return error_response(503, "no_data", "Price data not yet available")

        total_symbols = row["total_symbols"]
        sp500_symbols_covered = row["sp500_symbols_covered"]
        sp500_total = row["sp500_total"]
        latest_date = row["latest_date"]
        total_rows = row["total_rows"]
        zero_vol = row["zero_volume_rows"]
        invalid_prices = row["invalid_price_rows"]

        if sp500_total is None or sp500_total <= 0:
            return error_response(
                503, "configuration_error", "SP500 symbol target count missing or zero - configuration required"
            )

        if not total_rows:
            return error_response(503, "no_data", "No price rows available in last 7 days - data loading required")

        days_stale = (_date.today() - latest_date).days if latest_date else None
        zero_vol_pct = (zero_vol / total_rows * 100) if total_rows else None
        invalid_pct = (invalid_prices / total_rows * 100) if total_rows else None
        coverage_pct = round((sp500_symbols_covered or 0) / sp500_total * 100, 1)

        result = {
            "total_symbols": total_symbols,
            "sp500_target": sp500_total,
            "coverage_pct": coverage_pct,
            "latest_date": str(latest_date) if latest_date else None,
            "days_stale": days_stale,
            "status": (
                "fresh"
                if (days_stale is not None and days_stale <= 1)
                else ("stale" if days_stale is not None else None)
            ),
            "data_quality": {
                "zero_volume_pct": round(zero_vol_pct, 2) if zero_vol_pct is not None else None,
                "invalid_price_pct": round(invalid_pct, 2) if invalid_pct is not None else None,
            },
        }

        return success_response(result)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "get price coverage")
        return error_response(code, error_type, message)


def get_technical_coverage(cur: cursor) -> Any:
    try:
        cur.execute("SET LOCAL statement_timeout = '20s'")
        interval_7d = get_interval_sql("7d")
        cur.execute(f"""
            SELECT
                COUNT(DISTINCT symbol) as symbols,
                MAX(date) as latest_date,
                COUNT(*) as total_rows,
                COUNT(CASE WHEN rsi IS NOT NULL THEN 1 END)::FLOAT / COUNT(*) as rsi_coverage,
                COUNT(CASE WHEN ema_12 IS NOT NULL THEN 1 END)::FLOAT / COUNT(*) as ema50_coverage,
                COUNT(CASE WHEN atr IS NOT NULL THEN 1 END)::FLOAT / COUNT(*) as atr_coverage,
                COUNT(CASE WHEN rsi IS NULL OR ema_12 IS NULL OR atr IS NULL THEN 1 END) as incomplete_rows
            FROM technical_data_daily
            WHERE date > NOW() - {interval_7d}
        """)

        row = cur.fetchone()
        if not row:
            return error_response(503, "no_data", "Technical data not yet available")

        symbols, latest_date, _total_rows, rsi_cov, ema_cov, atr_cov, incomplete = row

        if None in (rsi_cov, ema_cov, atr_cov):
            missing_indicators = []
            if rsi_cov is None:
                missing_indicators.append("rsi")
            if ema_cov is None:
                missing_indicators.append("ema_12")
            if atr_cov is None:
                missing_indicators.append("atr")
            error_msg = f"Technical data incomplete: missing coverage for {', '.join(missing_indicators)}"
            logger.error(error_msg)
            return error_response(503, "incomplete_data", error_msg)

        min_coverage = min(rsi_cov, ema_cov, atr_cov)

        return success_response(
            {
                "symbols_with_technicals": symbols,
                "latest_date": str(latest_date),
                "indicator_coverage": {
                    "rsi_pct": round(rsi_cov * 100, 1),
                    "ema50_pct": round(ema_cov * 100, 1),
                    "atr_pct": round(atr_cov * 100, 1),
                    "min_coverage_pct": round(min_coverage * 100, 1),
                },
                "incomplete_rows": incomplete,
                "status": "complete" if min_coverage >= 0.95 else "incomplete",
            }
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "get technical coverage")
        return error_response(code, error_type, message)


def get_market_data_coverage(cur: cursor) -> Any:
    try:
        # Market health
        interval_7d = get_interval_sql("7d")
        cur.execute(f"""
            SELECT
                MAX(date) as latest_date,
                COUNT(*) as rows
            FROM market_health_daily
            WHERE date > NOW() - {interval_7d}
        """)

        mh_row = cur.fetchone()
        mh_date = mh_row["latest_date"] if mh_row else None
        mh_rows = mh_row["rows"] if mh_row else 0

        # Economic data (FRED) - uses series_id not symbol
        interval_30d = get_interval_sql("30d")
        cur.execute(f"""
            SELECT MAX(date) as latest_date, COUNT(DISTINCT series_id) as indicators
            FROM economic_data
            WHERE date > NOW() - {interval_30d}
        """)

        econ_row = cur.fetchone()
        econ_date = econ_row["latest_date"] if econ_row else None
        econ_count = econ_row["indicators"] if econ_row else 0

        return success_response(
            {
                "market_health": {
                    "latest_date": str(mh_date),
                    "days_stale": (_date.today() - mh_date).days if mh_date else 999,
                    "recent_rows": mh_rows,
                    "status": "available" if mh_rows > 0 else "missing",
                },
                "economic_data": {
                    "latest_date": str(econ_date) if econ_date else None,
                    "indicators_tracked": econ_count,
                    "status": "available" if econ_count > 0 else "missing",
                },
            }
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "get market data coverage")
        return error_response(code, error_type, message)


def get_loader_health(cur: cursor) -> Any:
    try:
        # Try to get patrol data first
        interval_7d = get_interval_sql("7d")
        cur.execute(f"""
            SELECT
                table_name,
                status,
                last_updated,
                row_count
            FROM data_loader_status
            WHERE last_updated > NOW() - {interval_7d}
            ORDER BY table_name
        """)

        rows = cur.fetchall()

        # Patrol data is REQUIRED - fail fast if missing
        if not rows:
            error_msg = "Loader health data unavailable: data_loader_status table is empty or no recent updates"
            logger.error(error_msg)
            return error_response(503, "no_loader_status", error_msg)

        # data_loader_status.status is written by two competing vocabularies: the loader's
        # own canonical execution result (utils/loaders/status_enum.py - RUNNING/COMPLETED/
        # FAILED/TIMEOUT) and algo/monitoring/pipeline_health.py's periodic freshness sweep
        # (HEALTHY/STALE/VERY_STALE/MISSING/ERROR), which overwrites the same column on every
        # sweep. Comparing against lowercase "stale"/"error" only ever matched a legacy
        # lowercase mapping that utils/loader_infrastructure.py no longer writes - it missed
        # every uppercase value from both real vocabularies, so this endpoint reported
        # "healthy" even when loaders were genuinely stale or failed. Match case-insensitively
        # against all known bad-status values from both vocabularies instead of one hardcoded
        # lowercase pair.
        bad_statuses = {"stale", "very_stale", "missing", "error", "failed", "timeout"}
        stale_loaders = [row[0] for row in rows if row[1] is None or str(row[1]).lower() in bad_statuses]
        return success_response(
            {
                "total_tracked": len(rows),
                "stale_loaders": list(set(stale_loaders)),
                "stale_count": len(set(stale_loaders)),
                "status": "healthy" if not stale_loaders else "degraded",
            }
        )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise Exception(f"Failed to retrieve loader health: {e}") from e


# ADDED 2026-09-16 (goal session: "verified accurate / known issue / unknown, covering all
# [second-opinion] sources"). Only scripts/xbrl_yfinance_crosscheck.py persists a granular,
# per-symbol/per-field/per-fiscal-year comparison (xbrl_yfinance_line_item_report, migration
# 1300) - the other XBRL second-opinion layers (calculation-linkbase self-consistency, DQC/
# Arelle, segment-sum reconciliation, price source crosscheck; see CLAUDE.md's XBRL table)
# only ever persist an aggregate WARN/info rollup per check into data_patrol_log, same as every
# other DataPatrol check - there's no per-field breakdown to surface for those. This section is
# honest about that granularity gap rather than pretending equal detail exists everywhere:
# `line_item_matrix` is the real verified/known-issue/unknown matrix (from the one source that
# actually has one), `other_second_opinion_layers` is coarser (whole-check pass/fail + whether
# a human has triaged it in data_patrol_review), not a symbol-level breakdown.
_OTHER_SECOND_OPINION_CHECK_NAMES = [
    "xbrl_calculation_linkbase_self_consistency",
    "xbrl_dqc_arelle_check",
    "xbrl_segment_sum_reconciliation",
    "price_source_independent_crosscheck",
]


def get_fundamentals_verification_coverage(cur: cursor) -> Any:
    try:
        cur.execute("SET LOCAL statement_timeout = '20s'")

        # Same eligible-universe filter scripts/xbrl_yfinance_crosscheck.py itself uses -
        # kept in sync deliberately so "coverage_pct" here means the same thing it means in
        # scripts/xbrl_line_item_report.py's CLI output.
        cur.execute(
            """
            SELECT COUNT(DISTINCT ais.symbol)
            FROM annual_income_statement ais
            JOIN stock_symbols s ON s.symbol = ais.symbol AND s.active = true
            WHERE ais.data_source = 'sec_audited' AND ais.data_unavailable = FALSE
            """
        )
        row = cur.fetchone()
        universe = row[0] if row and row[0] is not None else 0

        cur.execute("SELECT COUNT(DISTINCT symbol) FROM xbrl_yfinance_line_item_report")
        row = cur.fetchone()
        symbols_checked = row[0] if row and row[0] is not None else 0

        # review_status (migration 1302): `divergent` alone is just "SEC and yfinance disagree by
        # more than X this run" - it does NOT mean anyone confirmed which source is wrong. Calling
        # a divergent row "known_issue" is exactly the mislabeling that caused the 2026-09-16
        # corruption incident (scripts/DIVERGENCE_REPAIR_POSTMORTEM.md): downstream scripts
        # treated "flagged" as "confirmed wrong, safe to overwrite." So this is a genuine 5-way
        # split now: confident (not divergent), unreviewed (flagged, nobody's looked), and the
        # three review outcomes for whatever HAS been looked at via scripts/
        # xbrl_line_item_review.py. "known_issue"/"verified_accurate" keys are kept alongside the
        # new ones for existing API consumers, but callers should prefer the new fields - they
        # were never an accurate name for what this data actually shows.
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE NOT divergent) AS confident,
                COUNT(*) FILTER (WHERE divergent AND review_status = 'unreviewed') AS unreviewed,
                COUNT(*) FILTER (WHERE divergent AND review_status = 'reviewed_not_error') AS reviewed_not_error,
                COUNT(*) FILTER (WHERE divergent AND review_status = 'reviewed_needs_fix') AS reviewed_needs_fix,
                COUNT(*) FILTER (WHERE divergent AND review_status = 'reviewed_fixed') AS reviewed_fixed,
                COUNT(*) FILTER (WHERE divergent) AS flagged,
                COUNT(*) AS total
            FROM xbrl_yfinance_line_item_report
            """
        )
        row = cur.fetchone()
        (
            confident,
            unreviewed,
            reviewed_not_error,
            reviewed_needs_fix,
            reviewed_fixed,
            flagged,
            total_compared,
        ) = tuple(v or 0 for v in row) if row else (0, 0, 0, 0, 0, 0, 0)

        cur.execute(
            """
            SELECT our_table, our_field,
                   COUNT(*) FILTER (WHERE NOT divergent) AS confident,
                   COUNT(*) FILTER (WHERE divergent AND review_status = 'unreviewed') AS unreviewed,
                   COUNT(*) FILTER (WHERE divergent AND review_status = 'reviewed_not_error') AS reviewed_not_error,
                   COUNT(*) FILTER (WHERE divergent AND review_status = 'reviewed_needs_fix') AS reviewed_needs_fix,
                   COUNT(*) FILTER (WHERE divergent AND review_status = 'reviewed_fixed') AS reviewed_fixed,
                   COUNT(*) FILTER (WHERE divergent) AS flagged,
                   COUNT(*) AS checked
            FROM xbrl_yfinance_line_item_report
            GROUP BY our_table, our_field
            ORDER BY unreviewed DESC, our_table, our_field
            """
        )
        per_field = [
            {
                "table": r[0],
                "field": r[1],
                "confident": r[2],
                "unreviewed": r[3],
                "reviewed_not_error": r[4],
                "reviewed_needs_fix": r[5],
                "reviewed_fixed": r[6],
                "flagged": r[7],
                "checked": r[8],
                "verified_accurate": r[2],
                "known_issue": r[7],
                "known_issue_rate_pct": round(r[7] / r[8] * 100, 1) if r[8] else None,
            }
            for r in cur.fetchall()
        ]

        cur.execute("SELECT last_symbol, updated_at FROM xbrl_yfinance_crosscheck_progress WHERE id = 1")
        row = cur.fetchone()
        sweep_cursor = {"last_symbol": row[0], "updated_at": str(row[1])} if row else None

        other_layers: list[dict[str, Any]] = []
        for check_name in _OTHER_SECOND_OPINION_CHECK_NAMES:
            cur.execute(
                """
                SELECT severity, message, created_at
                FROM data_patrol_log
                WHERE check_name = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (check_name,),
            )
            latest = cur.fetchone()

            cur.execute(
                "SELECT status, COUNT(*) FROM data_patrol_review WHERE check_name = %s GROUP BY status",
                (check_name,),
            )
            review_triage = {r[0]: r[1] for r in cur.fetchall()}

            if latest is None:
                other_layers.append({"check_name": check_name, "status": "never_run", "review_triage": review_triage})
                continue

            severity, message, created_at = latest
            # data_patrol_log.created_at is live-typed "timestamp without time zone" (schema.sql
            # says WITH TIME ZONE, but that's stale vs. the live column - confirmed 2026-09-16),
            # so psycopg2 hands back a naive datetime; compare against another naive one instead
            # of datetime.now(timezone.utc), which raises on naive-vs-aware subtraction.
            days_since_run = (datetime.utcnow() - created_at).days if created_at else None
            other_layers.append(
                {
                    "check_name": check_name,
                    "last_severity": severity,
                    "last_message": message,
                    "last_run_at": str(created_at) if created_at else None,
                    "days_since_run": days_since_run,
                    # findings a human has already looked at (acceptable/needs_fix) vs. sitting
                    # untriaged in the review queue - not itself the finding count, just triage state
                    "review_triage": review_triage,
                }
            )

        return success_response(
            {
                "line_item_matrix": {
                    "source": "scripts/xbrl_yfinance_crosscheck.py (per-symbol/per-field/per-fiscal-year)",
                    "universe_size": universe,
                    "symbols_checked": symbols_checked,
                    "symbols_unknown": max(universe - symbols_checked, 0),
                    "coverage_pct": round(symbols_checked / universe * 100, 1) if universe else None,
                    # honest breakdown - see the comment above the query this comes from
                    "comparisons_confident": confident,
                    "comparisons_unreviewed": unreviewed,
                    "comparisons_reviewed_not_error": reviewed_not_error,
                    "comparisons_reviewed_needs_fix": reviewed_needs_fix,
                    "comparisons_reviewed_fixed": reviewed_fixed,
                    "comparisons_flagged": flagged,
                    "comparisons_total": total_compared,
                    # deprecated aliases, kept for existing consumers - "known_issue" never
                    # meant "confirmed wrong", it meant "flagged"; prefer the fields above
                    "comparisons_verified_accurate": confident,
                    "comparisons_known_issue": flagged,
                    "sweep_cursor": sweep_cursor,
                    "per_field": per_field,
                },
                "other_second_opinion_layers": other_layers,
                "status": "ok" if symbols_checked else "not_started",
            }
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "get fundamentals verification coverage")
        return error_response(code, error_type, message)


def _safe_call(cur: cursor, fn: Any) -> Any:
    """Call fn(cur) with SAVEPOINT isolation so a failed query doesn't abort the outer tx.

    Each sub-function raises exceptions on errors, which are caught here.
    Returns error dict if fn fails, or normal dict if successful.
    """
    try:
        cur.execute("SAVEPOINT coverage_check")
    except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
        logger.debug(f"[SAVEPOINT_CREATE] Error creating savepoint: {type(e).__name__}: {e}")

    try:
        result: dict[str, Any] = fn(cur)
        # fn succeeded - release the savepoint
        try:
            cur.execute("RELEASE SAVEPOINT coverage_check")
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            logger.debug(f"[SAVEPOINT_RELEASE] Error releasing savepoint: {type(e).__name__}: {e}")
            try:
                cur.execute("ROLLBACK TO SAVEPOINT coverage_check")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as sp_err:
                logger.debug(f"[SAVEPOINT_ROLLBACK] Error rolling back: {type(sp_err).__name__}: {sp_err}")
        return result
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        # fn failed - rollback the savepoint and return error dict
        try:
            cur.execute("ROLLBACK TO SAVEPOINT coverage_check")
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as rollback_err:
            logger.warning(f"[SAVEPOINT_ROLLBACK] Error rolling back: {type(rollback_err).__name__}: {rollback_err}")
        logger.warning(f"[COVERAGE_CHECK] Coverage check function failed: {type(e).__name__}: {e}")
        code, error_type, message = handle_db_error(e, "data coverage check")
        return error_response(code, error_type, message)


def get_overall_coverage_summary(cur: cursor) -> Any:
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "price_data": _safe_call(cur, get_price_coverage),
        "technical_data": _safe_call(cur, get_technical_coverage),
        "market_data": _safe_call(cur, get_market_data_coverage),
        "loaders": _safe_call(cur, get_loader_health),
        "fundamentals_verification": _safe_call(cur, get_fundamentals_verification_coverage),
    }

    # Determine overall status
    statuses = []
    for section_name, section_data in summary.items():
        if section_name == "timestamp":
            continue
        if isinstance(section_data, dict):
            # error_response() returns {'statusCode': ..., 'errorType': ..., 'message': ...}
            # Detect these and treat as critical so they don't silently pass the rollup.
            if "statusCode" in section_data:
                try:
                    if int(section_data.get("statusCode", 200)) >= 400:
                        statuses.append("critical")
                        continue
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"[COVERAGE_SUMMARY] Failed to parse statusCode from section '{section_name}': "
                        f"statusCode={section_data.get('statusCode')!r}, error={e}. "
                        f"Treating as critical status to avoid silent mask of errors."
                    )
                    statuses.append("critical")
            status = section_data.get("status")
            if status == "error" or status == "missing":
                statuses.append("critical")
            elif status in ["stale", "incomplete", "degraded"]:
                statuses.append("warning")
            elif status in ["fresh", "complete", "available", "healthy", "ok"]:
                statuses.append("ok")

    if "critical" in statuses:
        summary["overall_health"] = "critical"
    elif "warning" in statuses:
        summary["overall_health"] = "warning"
    else:
        summary["overall_health"] = "healthy"

    return summary


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle GET /api/data-coverage request."""
    if method != "GET":
        return error_response(405, "method_not_allowed", "Method not allowed. Only GET is supported.")

    try:
        summary = get_overall_coverage_summary(cur)
        # Return data wrapped in standard response format
        return json_response(200, summary)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle data coverage")
        return error_response(code, error_type, message)
