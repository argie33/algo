"""`_get_data_quality` route handler.

Split out of the former flat algo_handlers/market.py (file-size-ratchet compliance split,
2026-09-05); re-exported from algo_handlers/market/__init__.py so existing callers require
zero changes.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    list_response,
    safe_dict_convert,
    safe_json_serialize,
    validate_api_response,
)

from algo.infrastructure.config.sql_intervals import get_interval_sql

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"critical": 0, "error": 1, "warn": 2, "healthy": 3}


def _severity_rank(severity: Any) -> int:
    return _SEVERITY_RANK.get(severity, _SEVERITY_RANK["warn"]) if isinstance(severity, str) else _SEVERITY_RANK["warn"]


@db_route_handler("get data quality")
@validate_api_response("health")
def _get_data_quality(cur: cursor) -> Any:
    try:
        # Get patrol log entries from last 24 hours
        #
        # FIXED 2026-09-13 (goal session: comprehensive patrol/quarantine audit): this used
        # to partition ONLY by target_table, keeping the single most-recently-inserted row
        # per table regardless of which check produced it. Many distinct checks target the
        # same table (e.g. 9 different check modules write findings against
        # annual_income_statement - tie-out identity/bounds, statistical_anomaly,
        # financial_statement_flag_drift, reverse_merger_shell, etc.), so whichever check
        # happened to run last for a table silently hid every other check's finding for that
        # same table from this endpoint's summary and per-table status list - including a
        # CRITICAL from one check being masked by a later INFO/WARN from an unrelated check
        # on the same table. Partitioning by (target_table, check_name) instead keeps each
        # check's own latest state, then the table-level rollup below takes the worst
        # severity across all checks for that table (not just whichever inserted last).
        interval_24h = get_interval_sql("24h")
        cur.execute(f"""
                SELECT
                    target_table AS table_name,
                    check_name,
                    severity,
                    message,
                    NULL AS data_detail,
                    created_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY target_table, check_name ORDER BY created_at DESC
                    ) as rn
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

        # Keep each check's own latest state (one row per (table, check_name)), then find the
        # worst-severity check per table for display - not just whichever check inserted last.
        checks_dict: dict[tuple[str, str], dict[str, Any]] = {}
        for row in patrol_rows:
            row_dict = safe_json_serialize(safe_dict_convert(row))
            if row_dict.get("rn") == 1:  # Latest entry per (table, check_name)
                table_name = row_dict.get("table_name")
                check_name = row_dict.get("check_name")
                if not table_name:
                    raise ValueError(
                        "[DATA QUALITY] Patrol log row missing table_name. "
                        "Cannot identify which table is being monitored. "
                        "Check data_patrol_log table for NULL target_table values."
                    )
                if not check_name:
                    raise ValueError(
                        f"[DATA QUALITY] Patrol log row for {table_name} missing check_name. "
                        "Cannot distinguish which check produced this finding. "
                        "Check data_patrol_log table for NULL check_name values."
                    )
                checks_dict[(table_name, check_name)] = row_dict

        # Get latest timestamp
        latest_ts = max([safe_dict_convert(r)["created_at"] for r in patrol_rows]) if patrol_rows else None

        # Compute summary - every distinct (table, check) finding counts, not just one per
        # table, so this doesn't undercount how many checks are actually flagging something.
        severity_counts = {"critical": 0, "error": 0, "warn": 0, "healthy": 0}
        worst_per_table: dict[str, dict[str, Any]] = {}
        for (table_name, _check_name), entry in checks_dict.items():
            severity = entry.get("severity")
            if not severity:
                raise ValueError(
                    f"[DATA QUALITY] Patrol log entry for {table_name} missing severity. "
                    f"Cannot determine health status of this table. "
                    f"Check data_patrol_log.severity column for NULL values."
                )
            severity_counts[severity if severity in severity_counts else "warn"] += 1

            current_worst = worst_per_table.get(table_name)
            if current_worst is None or _severity_rank(severity) < _severity_rank(current_worst.get("severity")):
                worst_per_table[table_name] = entry

        table_statuses = []
        for table_name, entry in worst_per_table.items():
            severity = entry.get("severity")
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
        table_statuses.sort(key=lambda x: status_order.get(x["status"], 4) if isinstance(x["status"], str) else 4)

        response = list_response(table_statuses, total=len(table_statuses), limit=None, offset=None)
        response["data"]["accuracy_check"] = accuracy
        response["data"]["last_check"] = latest_ts.isoformat() if latest_ts else None
        response["data"]["summary"] = {
            "critical": severity_counts["critical"],
            "errors": severity_counts["error"],
            "warnings": severity_counts["warn"],
            "healthy": severity_counts["healthy"],
            "total_tables_checked": len(worst_per_table),
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
