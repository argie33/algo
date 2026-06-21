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

import logging
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
from routes.utils import (
    error_response,
    execute_with_timeout,
    handle_db_error,
    json_response,
    success_response,
)

from utils.db.sql_safety import assert_safe_table
from utils.validation import DatabaseResultValidator


logger = logging.getLogger(__name__)


def get_price_coverage(cur) -> dict[str, Any]:
    """Get price_daily coverage metrics."""
    try:
        rows = execute_with_timeout(
            cur,
            """
            SELECT
                COUNT(DISTINCT symbol) as total_symbols,
                (SELECT COUNT(DISTINCT symbol) FROM stock_symbols WHERE is_sp500 = TRUE) as sp500_total,
                MAX(date) as latest_date,
                COUNT(*) as total_rows,
                COUNT(CASE WHEN volume = 0 OR volume IS NULL THEN 1 END) as zero_volume_rows,
                COUNT(CASE WHEN close <= 0 THEN 1 END) as invalid_price_rows
            FROM price_daily
            WHERE date > NOW() - INTERVAL '7 days'
        """,
            timeout_sec=10,
        )

        row = DatabaseResultValidator.safe_get_first_row(rows, "price coverage")
        if not row:
            return error_response(503, "no_data", "Price data not yet available")

        total_symbols = row["total_symbols"]
        sp500_total = row["sp500_total"]
        latest_date = row["latest_date"]
        total_rows = row["total_rows"]
        zero_vol = row["zero_volume_rows"]
        invalid_prices = row["invalid_price_rows"]

        days_stale = (_date.today() - latest_date).days if latest_date else 999
        zero_vol_pct = (zero_vol / total_rows * 100) if total_rows else 0
        invalid_pct = (invalid_prices / total_rows * 100) if total_rows else 0

        return success_response(
            {
                "total_symbols": total_symbols,
                "sp500_target": sp500_total,
                "coverage_pct": (
                    round(total_symbols / sp500_total * 100, 1) if sp500_total else 0
                ),
                "latest_date": str(latest_date),
                "days_stale": days_stale,
                "status": "fresh" if days_stale <= 1 else "stale",
                "data_quality": {
                    "zero_volume_pct": round(zero_vol_pct, 2),
                    "invalid_price_pct": round(invalid_pct, 2),
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
        code, error_type, message = handle_db_error(e, "get price coverage")
        return error_response(code, error_type, message)


def get_technical_coverage(cur) -> dict[str, Any]:
    """Get technical_data_daily coverage and completeness."""
    try:
        cur.execute("SET LOCAL statement_timeout = '20s'")
        cur.execute("""
            SELECT
                COUNT(DISTINCT symbol) as symbols,
                MAX(date) as latest_date,
                COUNT(*) as total_rows,
                COUNT(CASE WHEN rsi IS NOT NULL THEN 1 END)::FLOAT / COUNT(*) as rsi_coverage,
                COUNT(CASE WHEN ema_12 IS NOT NULL THEN 1 END)::FLOAT / COUNT(*) as ema50_coverage,
                COUNT(CASE WHEN atr IS NOT NULL THEN 1 END)::FLOAT / COUNT(*) as atr_coverage,
                COUNT(CASE WHEN rsi IS NULL OR ema_12 IS NULL OR atr IS NULL THEN 1 END) as incomplete_rows
            FROM technical_data_daily
            WHERE date > NOW() - INTERVAL '7 days'
        """)

        row = cur.fetchone()
        if not row:
            return error_response(503, "no_data", "Technical data not yet available")

        symbols, latest_date, total_rows, rsi_cov, ema_cov, atr_cov, incomplete = row

        min_coverage = (
            min(rsi_cov, ema_cov, atr_cov)
            if None not in (rsi_cov, ema_cov, atr_cov)
            else 0
        )

        return success_response(
            {
                "symbols_with_technicals": symbols,
                "latest_date": str(latest_date),
                "indicator_coverage": {
                    "rsi_pct": round(rsi_cov * 100, 1) if rsi_cov else 0,
                    "ema50_pct": round(ema_cov * 100, 1) if ema_cov else 0,
                    "atr_pct": round(atr_cov * 100, 1) if atr_cov else 0,
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


def get_market_data_coverage(cur) -> dict[str, Any]:
    """Get market_health_daily and other market data coverage."""
    try:
        # Market health
        cur.execute("""
            SELECT
                MAX(date) as latest_date,
                COUNT(*) as rows
            FROM market_health_daily
            WHERE date > NOW() - INTERVAL '7 days'
        """)

        mh_row = cur.fetchone()
        mh_date = mh_row["latest_date"] if mh_row else None
        mh_rows = mh_row["rows"] if mh_row else 0

        # Economic data (FRED) — uses series_id not symbol
        cur.execute("""
            SELECT MAX(date) as latest_date, COUNT(DISTINCT series_id) as indicators
            FROM economic_data
            WHERE date > NOW() - INTERVAL '30 days'
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


def get_loader_health(cur) -> dict[str, Any]:
    """Get recent loader execution health from patrol log or direct table freshness checks."""
    try:
        # Try to get patrol data first
        cur.execute("""
            SELECT
                table_name,
                status,
                last_updated,
                row_count
            FROM data_loader_status
            WHERE last_updated > NOW() - INTERVAL '7 days'
            ORDER BY table_name
        """)

        rows = cur.fetchall()

        # If patrol data is recent, use it
        if rows:
            stale_loaders = [
                row[0] for row in rows if row[1] in ("stale", "error") or row[1] is None
            ]
            return success_response(
                {
                    "total_tracked": len(rows),
                    "stale_loaders": list(set(stale_loaders)),
                    "stale_count": len(set(stale_loaders)),
                    "status": "healthy" if not stale_loaders else "degraded",
                }
            )

        # Fallback: if patrol data is missing/stale, check key tables directly
        tables_to_check = [
            "price_daily",
            "technical_data_daily",
            "market_health_daily",
            "sector_performance",
            "economic_data",
            "stock_symbols",
        ]

        table_health = []
        try:
            for table in tables_to_check:
                assert_safe_table(table)

            union_parts = []
            for table in tables_to_check:
                table_safe = assert_safe_table(table)
                union_parts.append(f"SELECT '{table}' as tbl_name, MAX(date) as last_update, COUNT(*) as row_count FROM {table_safe}")

            union_query = " UNION ALL ".join(union_parts)
            cur.execute(union_query)

            health_by_table = {}
            for row in cur.fetchall():
                row_dict = dict(row)
                health_by_table[row_dict["tbl_name"]] = (row_dict["last_update"], row_dict["row_count"])

            for table in tables_to_check:
                try:
                    if table in health_by_table:
                        last_update, count = health_by_table[table]
                        days_old = (
                            (datetime.now(timezone.utc) - last_update).days if last_update else 999
                        )
                        status = "stale" if days_old > 7 else "fresh"
                        table_health.append((table, status, last_update, count))
                except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
                    logger.warning(f"[LOADER_HEALTH] Table {table} not found - skipping")
                except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
                    logger.warning(
                        f"[LOADER_HEALTH] Database error checking {table}: {type(e).__name__}: {e}"
                    )
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.warning(
                        f"[LOADER_HEALTH] Unexpected error checking {table}: {type(e).__name__}: {e}"
                    )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"[LOADER_HEALTH] Failed to check table health: {e}")

        stale_loaders = [t[0] for t in table_health if t[1] == "stale"]
        return success_response(
            {
                "total_tracked": len(table_health),
                "stale_loaders": stale_loaders,
                "stale_count": len(stale_loaders),
                "status": "healthy" if not stale_loaders else "degraded",
                "source": "patrol" if rows else "table_check",
            }
        )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise Exception(f"Failed to retrieve loader health: {e}")


def _safe_call(cur, fn) -> dict[str, Any]:
    """Call fn(cur) with SAVEPOINT isolation so a failed query doesn't abort the outer tx.

    Each sub-function raises exceptions on errors, which are caught here.
    Returns error dict if fn fails, or normal dict if successful.
    """
    try:
        cur.execute("SAVEPOINT coverage_check")
    except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
        logger.debug(f"[SAVEPOINT_CREATE] Database error: {type(e).__name__}: {e}")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.debug(
            f"[SAVEPOINT_CREATE] Error creating savepoint: {type(e).__name__}: {e}"
        )

    try:
        result = fn(cur)
        # fn succeeded - release the savepoint
        try:
            cur.execute("RELEASE SAVEPOINT coverage_check")
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            logger.debug(f"[SAVEPOINT_RELEASE] Database error: {type(e).__name__}: {e}")
            try:
                cur.execute("ROLLBACK TO SAVEPOINT coverage_check")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as sp_err:
                logger.debug(
                    f"[SAVEPOINT_ROLLBACK] Error rolling back: {type(sp_err).__name__}: {sp_err}"
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(
                f"[SAVEPOINT_RELEASE] Error releasing savepoint: {type(e).__name__}: {e}"
            )
            try:
                cur.execute("ROLLBACK TO SAVEPOINT coverage_check")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as sp_err:
                logger.debug(
                    f"[SAVEPOINT_ROLLBACK] Error rolling back: {type(sp_err).__name__}: {sp_err}"
                )
        return result
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        # fn failed - rollback the savepoint and return error dict
        try:
            cur.execute("ROLLBACK TO SAVEPOINT coverage_check")
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as rollback_err:
            logger.warning(
                f"[SAVEPOINT_ROLLBACK] Database error rolling back: {type(rollback_err).__name__}: {rollback_err}"
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as rollback_err:
            logger.warning(
                f"[SAVEPOINT_ROLLBACK] Error rolling back: {type(rollback_err).__name__}: {rollback_err}"
            )
        logger.warning(
            f"[COVERAGE_CHECK] Coverage check function failed: {type(e).__name__}: {e}"
        )
        code, error_type, message = handle_db_error(e, "data coverage check")
        return error_response(code, error_type, message)


def get_overall_coverage_summary(cur) -> dict[str, Any]:
    """Get overall data coverage summary."""
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "price_data": _safe_call(cur, get_price_coverage),
        "technical_data": _safe_call(cur, get_technical_coverage),
        "market_data": _safe_call(cur, get_market_data_coverage),
        "loaders": _safe_call(cur, get_loader_health),
    }

    # Determine overall status
    statuses = []
    for section_name, section_data in summary.items():
        if section_name == "timestamp":
            continue
        if isinstance(section_data, dict):
            # error_response() returns {'statusCode': ..., 'errorType': ..., 'message': ...}
            # Detect these and treat as critical so they don't silently pass the rollup.
            if (
                "statusCode" in section_data
                and section_data.get("statusCode", 200) >= 400
            ):
                statuses.append("critical")
                continue
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
    cur,
    path: str,
    method: str,
    params: dict,
    body: dict = None,
    jwt_claims: dict = None,
) -> dict:
    """Handle GET /api/data-coverage request."""
    if method != "GET":
        return error_response(
            405, "method_not_allowed", "Method not allowed. Only GET is supported."
        )

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
