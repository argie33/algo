"""Route: algo"""

from __future__ import annotations

import json
import logging
from typing import Any

import psycopg2
from psycopg2.extensions import cursor

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    db_route_handler,
    error_response,
    list_response,
    safe_dict_convert,
    safe_json_serialize,
    success_response,
    validate_api_response,
)

logger = logging.getLogger(__name__)


@db_route_handler("fetch orchestrator execution details")  # type: ignore[untyped-decorator]
@validate_api_response("run")  # type: ignore[untyped-decorator]
def _get_orchestrator_execution_details(cur: cursor, run_id: str) -> Any:
    """Return full details of a specific orchestrator run."""
    cur.execute(
        """
        SELECT run_id, run_date, started_at, completed_at, overall_status,
               phase_results, summary, halt_reason, phases_completed,
               phases_halted, phases_errored
        FROM orchestrator_execution_log
        WHERE run_id = %s
    """,
        (run_id,),
    )
    row = cur.fetchone()
    if not row:
        return error_response(404, "not_found", f"Run {run_id} not found")

    result = safe_json_serialize(safe_dict_convert(row))
    # Parse phase_results JSONB
    if result.get("phase_results"):
        try:
            result["phase_results"] = json.loads(result["phase_results"])
        except (psycopg2.DatabaseError, psycopg2.OperationalError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Orchestrator phase_results JSON parsing failed for run {run_id}: {e}") from e
    return success_response(result)


@db_route_handler("fetch orchestrator execution failed")  # type: ignore[untyped-decorator]
@validate_api_response("run")  # type: ignore[untyped-decorator]
def _get_orchestrator_execution_failed(cur: cursor, days: int = 30) -> Any:
    """Return failed/halted orchestrator runs."""
    cur.execute(
        """
        SELECT run_id, run_date, started_at, overall_status, summary, halt_reason
        FROM orchestrator_execution_log
        WHERE run_date >= CURRENT_DATE - %s
          AND overall_status IN ('halted', 'error')
        ORDER BY started_at DESC
    """,
        (days,),
    )
    rows = cur.fetchall()
    return list_response([safe_json_serialize(safe_dict_convert(r)) for r in rows], total=len(rows))


@db_route_handler("fetch orchestrator execution patterns")  # type: ignore[untyped-decorator]
@validate_api_response("run")  # type: ignore[untyped-decorator]
def _get_orchestrator_execution_patterns(cur: cursor, days: int = 30) -> Any:
    """Analyze halt patterns - which phases halt most often."""
    cur.execute(
        """
        SELECT
            phase_results->>'name' as phase_name,
            COUNT(*) as halt_count,
            array_agg(DISTINCT phase_results->>'summary') as reasons
        FROM orchestrator_execution_log,
             jsonb_array_elements(phase_results) as phase_results
        WHERE run_date >= CURRENT_DATE - %s
          AND phase_results->>'status' = 'halt'
        GROUP BY phase_results->>'name'
        ORDER BY halt_count DESC
    """,
        (days,),
    )
    rows = cur.fetchall()
    patterns = [
        {
            "phase": r["phase_name"],
            "total_halts": r["halt_count"],
            "example_reasons": r["reasons"][:3] if r["reasons"] else [],
        }
        for r in rows
    ]
    return success_response({"patterns": patterns, "period_days": days})


@db_route_handler("fetch orchestrator execution recent")  # type: ignore[untyped-decorator]
@validate_api_response("exec_hist")  # type: ignore[untyped-decorator]
def _get_orchestrator_execution_recent(cur: cursor, days: int = 7, limit: int = 50) -> Any:
    """Return recent orchestrator execution runs."""
    try:
        cur.execute(
            """
            SELECT run_id, run_date, started_at, completed_at, overall_status, summary,
                   COALESCE(ARRAY(
                       SELECT 'P' || (p->>'phase')
                       FROM jsonb_array_elements(COALESCE(phase_results, '[]'::jsonb)) p
                       WHERE p->>'status' = 'success'
                   ), ARRAY[]::text[]) AS phases_completed,
                   COALESCE(ARRAY(
                       SELECT 'P' || (p->>'phase')
                       FROM jsonb_array_elements(COALESCE(phase_results, '[]'::jsonb)) p
                       WHERE p->>'status' = 'halt'
                   ), ARRAY[]::text[]) AS phases_halted,
                   COALESCE(ARRAY(
                       SELECT 'P' || (p->>'phase')
                       FROM jsonb_array_elements(COALESCE(phase_results, '[]'::jsonb)) p
                       WHERE p->>'status' = 'error'
                   ), ARRAY[]::text[]) AS phases_errored
            FROM orchestrator_execution_log
            WHERE run_date >= CURRENT_DATE - %s
            ORDER BY started_at DESC
            LIMIT %s
        """,
            (days, limit),
        )
        rows = cur.fetchall()
        if not rows:
            return list_response([], total=0, limit=limit)
        try:
            items = [safe_json_serialize(safe_dict_convert(r)) for r in rows]
            return list_response(items, total=len(rows), limit=limit)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as ser_e:
            raise RuntimeError(
                f"Orchestrator execution serialization failed: {type(ser_e).__name__}: {ser_e}"
            ) from ser_e
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Orchestrator execution recent query failed: {type(e).__name__}: {e}") from e


@db_route_handler("fetch orchestrator execution stats")  # type: ignore[untyped-decorator]
@validate_api_response("run")  # type: ignore[untyped-decorator]
def _get_orchestrator_execution_stats(cur: cursor, days: int = 7) -> Any:
    """Return execution statistics."""
    cur.execute(
        """
        SELECT
            overall_status,
            COUNT(*) as count
        FROM orchestrator_execution_log
        WHERE run_date >= CURRENT_DATE - %s
        GROUP BY overall_status
    """,
        (days,),
    )
    rows = cur.fetchall()

    stats_by_status = {r["overall_status"]: r["count"] for r in rows}
    total = sum(stats_by_status.values())

    # Provide 0 counts for any missing statuses (no runs of that type in period is valid)
    expected_statuses = {"success", "halted", "error"}
    for status in expected_statuses:
        stats_by_status.setdefault(status, 0)

    success_count = int(stats_by_status["success"])
    halt_count = int(stats_by_status["halted"])
    error_count = int(stats_by_status["error"])

    return success_response(
        {
            "total_runs": total,
            "by_status": stats_by_status,
            "success_rate": (f"{(success_count / total * 100):.1f}%" if total > 0 else None),
            "halt_rate": (f"{(halt_count / total * 100):.1f}%" if total > 0 else None),
            "error_rate": (f"{(error_count / total * 100):.1f}%" if total > 0 else None),
            "period_days": days,
        }
    )
