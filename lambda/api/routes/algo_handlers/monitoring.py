"""Route: algo"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from botocore.exceptions import ClientError
from psycopg2.extensions import cursor

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    db_route_handler,
    error_response,
    extract_param,
    handle_db_error,
    json_response,
    list_response,
    safe_dict_convert,
    safe_json_serialize,
    safe_limit,
    validate_api_response,
)

from shared_contracts.response_validator import ResponseValidator

logger = logging.getLogger(__name__)


@db_route_handler("get algo audit log")
@validate_api_response("audit")
def _get_algo_audit_log(cur: cursor, limit: int = 100, offset: int = 0, action_type: str | None = None) -> Any:
    if action_type:
        cur.execute(
            "SELECT COUNT(*) as total FROM algo_audit_log WHERE action_type = %s",
            (action_type,),
        )
    else:
        cur.execute("SELECT COUNT(*) as total FROM algo_audit_log")
    count_row = cur.fetchone()
    if count_row is None:
        raise RuntimeError("Failed to fetch audit log count: query returned no results")
    count_row = safe_dict_convert(count_row)
    total = count_row["total"]
    if total is None:
        raise RuntimeError("Audit log count query returned None for 'total' field")

    if action_type:
        cur.execute(
            """
                SELECT id, action_type, symbol, action_date, details, actor, status,
                       error_message AS error, created_at
                FROM algo_audit_log
                WHERE action_type = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """,
            (action_type, limit, offset),
        )
    else:
        cur.execute(
            """
                SELECT id, action_type, symbol, action_date, details, actor, status,
                       error_message AS error, created_at
                FROM algo_audit_log
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
    rows = cur.fetchall()
    return list_response(
        [safe_json_serialize(safe_dict_convert(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# FIXED Issue #6: Orchestrator execution history endpoints


@db_route_handler("get last run")
@validate_api_response("run")
def _get_last_run(cur: cursor) -> Any:
    # Phase-level detail lives in orchestrator_execution_log (written by
    # OrchestratorExecutionTracker with the same run_id) -- the orchestrator's own
    # INSERT into algo_orchestrator_runs never populates its phase_results column.
    cur.execute("""
        SELECT r.run_id, r.run_date, r.overall_status, r.halt_reason, r.started_at, r.completed_at,
               l.phase_results, l.phases_completed
        FROM algo_orchestrator_runs r
        LEFT JOIN orchestrator_execution_log l ON l.run_id = r.run_id
        ORDER BY r.started_at DESC
        LIMIT 1
    """)
    latest = cur.fetchone()
    if latest is None:
        return error_response(503, "no_data", "No orchestrator run data available yet")

    latest_dict = safe_json_serialize(safe_dict_convert(latest))

    # Validate required fields exist in orchestrator run record
    required_fields = ["run_id", "overall_status", "started_at"]
    for field in required_fields:
        if field not in latest_dict or latest_dict[field] is None:
            raise ValueError(f"Orchestrator run missing required field '{field}'")

    # Extract required fields (guaranteed non-None by validation above)
    run_id = latest_dict["run_id"]
    overall_status = latest_dict["overall_status"]
    started_at = latest_dict["started_at"]

    # Optional fields may be None
    halt_reason = latest_dict.get("halt_reason")
    completed_at = latest_dict.get("completed_at")
    phase_results = latest_dict.get("phase_results")

    # Compute phases_completed: prefer the tracker's own count (it counts status
    # "ok", which is what OrchestratorExecutionTracker records per phase)
    phases_completed = latest_dict.get("phases_completed")
    if phases_completed is None:
        # Fall back to counting phase_results if available
        if phase_results:
            try:
                if isinstance(phase_results, str):
                    import json

                    phase_results = json.loads(phase_results)
                if isinstance(phase_results, list):
                    phases_completed = len([p for p in phase_results if p.get("status") in ("ok", "success")])
            except (ValueError, TypeError, KeyError):
                pass
        if phases_completed is None:
            logger.warning(
                "[MONITORING] phases_completed missing from orchestrator run data - cannot determine execution progress"
            )
            # INTENTIONAL DESIGN: When phase tracking data is unavailable, 0 is the correct default
            # (no phases executed according to available data). This prevents cascading failures when
            # orchestrator_execution_log is incomplete or corrupted.
            phases_completed = 0

    if not run_id:
        return error_response(503, "invalid_data", "Run ID missing from latest orchestrator run")
    if overall_status is None:
        return error_response(503, "invalid_data", "Overall status missing from latest orchestrator run")

    # Determine success/halted/errored from overall_status.
    # "ok" is a real, healthy terminal state (e.g. Phase 8 correctly blocked by the
    # market-hours guard while Phase 9 still completed) - see orchestrator.py's own
    # authoritative `result["success"] = overall_status in ("success", "ok")`.
    # Checking only "success" here made this endpoint disagree with the orchestrator
    # and report success=False for every healthy "ok" run (the common case for any
    # run outside 9:30-4:00 ET), which the CLI dashboard's status pill (health.py)
    # renders as the vague "[dim]RUN[/]" fallback instead of "COMPLETED".
    success = overall_status in ("success", "ok")
    halted = overall_status in ("halted", "halt")
    errored = overall_status == "error"

    # Parse phase_results from JSONB (array of phase execution objects)
    phases = []
    if phase_results:
        try:
            if isinstance(phase_results, str):
                import json

                phase_results = json.loads(phase_results)
            if isinstance(phase_results, list):
                phases = phase_results
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse phase_results for run {run_id}: {e}")
            phases = []

    response_data = {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "success": success,
        "halted": halted,
        "errored": errored,
        "summary": halt_reason if (halted or errored) else f"Completed successfully ({phases_completed} phases)",
        "halt_reason": halt_reason if (halted or errored) else None,
        "phases_completed": phases_completed,
        "phases": phases,
        "phase_results": phases,
    }

    return json_response(200, response_data)


@db_route_handler("get orchestrator history extended")
@validate_api_response("freshness_extended")
def _get_orchestrator_history_extended(cur: cursor, params: dict[str, Any] | None = None) -> Any:
    """Get extended orchestrator run history with phase breakdown, failure patterns, and loader health.

    Returns:
    - run_history: Last 20 runs with status, duration, phase breakdown, halt reasons
    - phase_health: Success/failure rates for all 9 phases across 30 days
    - failure_patterns: Most common halt reasons and their frequency
    - loader_health: Loader reliability metrics (failure streaks, success rates)
    - trend_summary: Overall health trend (improving/degrading/stable)
    """
    limit = safe_limit(extract_param(params, "limit"), max_val=50, default=20)

    try:
        # 1. Get recent run history (last N runs)
        cur.execute(f"""
            SELECT r.run_id, r.run_date, r.overall_status, r.halt_reason, r.started_at, r.completed_at,
                   l.phase_results, l.phases_completed, l.phases_halted, l.phases_errored
            FROM algo_orchestrator_runs r
            LEFT JOIN orchestrator_execution_log l ON l.run_id = r.run_id
            ORDER BY r.started_at DESC
            LIMIT %s
        """, (limit,))

        run_rows = cur.fetchall()
        run_history = []

        for row in run_rows:
            # DEFENSIVE (2026-08-04): one malformed row (e.g. legacy/hand-patched
            # phase_results shape) used to 500 this entire dashboard endpoint - a
            # `TypeError`/`AttributeError` anywhere in this per-row block was caught by
            # the outer db_route_handler as a generic "Invalid request" with no indication
            # which run_id caused it (live-observed 2026-08-03 14:50-14:55, never
            # reproduced afterward - the bad row/state was transient, but nothing here
            # stopped it from taking every other row down with it). Skip the offending
            # row and keep serving the rest instead of failing the whole response.
            try:
                run_dict = safe_dict_convert(row)
                row_data = safe_json_serialize(run_dict)

                # Parse phase results
                phase_results = row_data.get("phase_results")
                phases_list = []
                if phase_results:
                    try:
                        if isinstance(phase_results, str):
                            phase_results = json.loads(phase_results)
                        if isinstance(phase_results, list):
                            phases_list = [p for p in phase_results if isinstance(p, dict)]
                    except (ValueError, TypeError):
                        pass

                # Build phase badge summary
                phase_summary = {
                    "completed": len([p for p in phases_list if p.get("status") in ("ok", "success")]),
                    "halted": len([p for p in phases_list if p.get("status") in ("halt", "halted", "warn", "degraded")]),
                    "skipped": len([p for p in phases_list if p.get("status") == "skipped"]),
                    "errored": len([p for p in phases_list if p.get("status") in ("error", "failed")]),
                }

                run_history.append({
                    "run_id": row_data.get("run_id"),
                    "run_date": row_data.get("run_date"),
                    "status": row_data.get("overall_status"),
                    "started_at": row_data.get("started_at"),
                    "completed_at": row_data.get("completed_at"),
                    "halt_reason": row_data.get("halt_reason"),
                    "phase_summary": phase_summary,
                    "phases": phases_list[:9],  # All 9 phases
                })
            except Exception as row_err:
                bad_run_id = row[0] if row else "unknown"
                logger.warning(
                    f"[FRESHNESS_EXTENDED] Skipping malformed run_history row (run_id={bad_run_id}): "
                    f"{type(row_err).__name__}: {row_err}"
                )
                continue

        # 2. Calculate phase-level health (success rates for each phase across 30 days)
        phase_health = {}
        cur.execute("""
            WITH phase_stats AS (
                SELECT
                    jsonb_array_elements(phase_results) ->> 'phase' as phase_num,
                    jsonb_array_elements(phase_results) ->> 'status' as phase_status,
                    COUNT(*) as count
                FROM orchestrator_execution_log
                WHERE started_at > NOW() - INTERVAL '30 days'
                AND phase_results IS NOT NULL
                GROUP BY phase_num, phase_status
            )
            SELECT
                phase_num,
                SUM(count) as total_runs,
                SUM(CASE WHEN phase_status IN ('ok', 'success') THEN count ELSE 0 END) as successful_runs
            FROM phase_stats
            GROUP BY phase_num
            ORDER BY phase_num::int ASC
        """)

        for row in cur.fetchall():
            try:
                row_dict = safe_dict_convert(row)
                phase_num = row_dict.get("phase_num")
                total = row_dict.get("total_runs") or 0
                success = row_dict.get("successful_runs") or 0
                success_rate = (success / total * 100) if total > 0 else 0
                phase_health[phase_num] = {
                    "total_runs": total,
                    "successful_runs": success,
                    "success_rate": round(success_rate, 1),
                }
            except Exception as row_err:
                logger.warning(f"[FRESHNESS_EXTENDED] Skipping malformed phase_health row: {type(row_err).__name__}: {row_err}")
                continue

        # 3. Get failure patterns (most common halt reasons)
        cur.execute("""
            SELECT halt_reason, COUNT(*) as occurrences
            FROM orchestrator_execution_log
            WHERE halt_reason IS NOT NULL
            AND started_at > NOW() - INTERVAL '30 days'
            GROUP BY halt_reason
            ORDER BY occurrences DESC
            LIMIT 10
        """)

        failure_patterns = []
        for row in cur.fetchall():
            row_dict = safe_dict_convert(row)
            failure_patterns.append({
                "reason": row_dict.get("halt_reason"),
                "occurrences": row_dict.get("occurrences"),
            })

        # 4. Get loader health (failure streaks and success rates)
        #
        # data_loader_status.status is written by two independent, competing vocabularies
        # that share this one column (see utils/loader_infrastructure.py's
        # update_loader_status docstring): the loader's own execution result
        # (COMPLETED/FAILED/success/OK) and algo/monitoring/pipeline_health.py's
        # unconditional per-run freshness sweep (HEALTHY/STALE/VERY_STALE/MISSING/ERROR/
        # DEPRECATED), which overwrites the same column for ~95 tracked tables on every
        # orchestrator run and, per that sweep's own comments, leaves most tables sitting
        # on "HEALTHY" far more often than "COMPLETED". A naive `status != "COMPLETED"`
        # check flags every one of those as a false "loader issue" - this is the same
        # multi-vocabulary trap loaders/load_buy_sell_daily.py's own upstream-readiness
        # check already had to whitelist around. DEPRECATED tables are intentionally
        # frozen (see pipeline_health.py's TableHealth.is_healthy) and count as healthy
        # too, not unhealthy.
        # No LIMIT here: consecutive_failures DESC would silently drop genuinely-unhealthy
        # tables that happen to sit at 0 consecutive_failures (e.g. STALE/ERROR/MISSING from
        # the pipeline_health.py sweep, which never touches consecutive_failures) once more
        # than ~30 tables are tracked - the table count (~95 per pipeline_health.py) already
        # exceeds that. Fetch every row and let Python separate healthy from unhealthy so the
        # unhealthy count below is real, not truncated before it's even computed.
        cur.execute("""
            SELECT table_name, status, consecutive_failures, retry_count, last_success_at,
                   execution_completed, completion_pct
            FROM data_loader_status
            WHERE table_name IS NOT NULL
            ORDER BY consecutive_failures DESC, table_name ASC
        """)

        healthy_loader_statuses = ("COMPLETED", "success", "OK", "ok", "HEALTHY", "DEPRECATED")

        loader_health_total_tracked = 0
        loader_health = []
        for row in cur.fetchall():
            loader_health_total_tracked += 1
            try:
                row_dict = safe_dict_convert(row)
                table_name = row_dict.get("table_name")
                status = row_dict.get("status")
                cons_failures = row_dict.get("consecutive_failures") or 0
                retry_count = row_dict.get("retry_count") or 0
                last_success = row_dict.get("last_success_at")
                is_unhealthy = cons_failures > 0 or status not in healthy_loader_statuses

                if is_unhealthy:
                    loader_health.append({
                        "table_name": table_name,
                        "status": status,
                        "consecutive_failures": cons_failures,
                        "retry_count": retry_count,
                        "last_success_at": last_success,
                        "is_unhealthy": is_unhealthy,
                    })
            except Exception as row_err:
                logger.warning(f"[FRESHNESS_EXTENDED] Skipping malformed loader_health row: {type(row_err).__name__}: {row_err}")
                continue

        loader_health_total_unhealthy = len(loader_health)

        # 5. Calculate trend summary (7-day vs 30-day comparison)
        cur.execute("""
            SELECT
                COUNT(*) as total_7d,
                SUM(CASE WHEN overall_status IN ('success', 'ok') THEN 1 ELSE 0 END) as successful_7d
            FROM orchestrator_execution_log
            WHERE started_at > NOW() - INTERVAL '7 days'
        """)

        trend_7d_row = cur.fetchone()
        if trend_7d_row:
            trend_7d_dict = safe_dict_convert(trend_7d_row)
            total_7d = trend_7d_dict.get("total_7d") or 0
            successful_7d = trend_7d_dict.get("successful_7d") or 0
            success_rate_7d = (successful_7d / total_7d * 100) if total_7d > 0 else 0
        else:
            success_rate_7d = 0

        cur.execute("""
            SELECT
                COUNT(*) as total_30d,
                SUM(CASE WHEN overall_status IN ('success', 'ok') THEN 1 ELSE 0 END) as successful_30d
            FROM orchestrator_execution_log
            WHERE started_at > NOW() - INTERVAL '30 days'
        """)

        trend_30d_row = cur.fetchone()
        if trend_30d_row:
            trend_30d_dict = safe_dict_convert(trend_30d_row)
            total_30d = trend_30d_dict.get("total_30d") or 0
            successful_30d = trend_30d_dict.get("successful_30d") or 0
            success_rate_30d = (successful_30d / total_30d * 100) if total_30d > 0 else 0
        else:
            success_rate_30d = 0

        trend = "improving" if success_rate_7d > success_rate_30d else ("degrading" if success_rate_7d < success_rate_30d else "stable")

        trend_summary = {
            "trend": trend,
            "success_rate_7d": round(success_rate_7d, 1),
            "success_rate_30d": round(success_rate_30d, 1),
            "total_runs_7d": total_7d if trend_7d_row else 0,
            "total_runs_30d": total_30d if trend_30d_row else 0,
        }

        response_data = {
            "run_history": run_history,
            "phase_health": phase_health,
            "failure_patterns": failure_patterns,
            "loader_health": loader_health[:15],
            "loader_health_total_unhealthy": loader_health_total_unhealthy,
            "loader_health_total_tracked": loader_health_total_tracked,
            "trend_summary": trend_summary,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        return json_response(200, response_data)

    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn, psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        code, error_type, message = handle_db_error(e, "get orchestrator history extended")
        return error_response(code, error_type, message)


@db_route_handler("fetch notifications")
@validate_api_response("notifs")
def _get_notifications(
    cur: cursor, params: dict[str, Any] | None = None, jwt_claims: dict[str, Any] | None = None
) -> Any:
    try:
        if params is None:
            params = {}
        kind = extract_param(params, "kind")
        severity = extract_param(params, "severity")
        unread = extract_param(params, "unread")
        limit = safe_limit(extract_param(params, "limit"), max_val=10000, default=100)

        # SECURITY M-04: Validate kind and severity against whitelists
        valid_kinds = {
            "signal",
            "halt",
            "alert",
            "error",
            "trade",
            "position",
            "market",
            "system",
            "safeguard",
        }
        valid_severities = {"info", "warning", "error", "critical"}

        if kind and kind not in valid_kinds:
            return error_response(400, "bad_request", f"Invalid kind: {kind}")
        if severity and severity not in valid_severities:
            return error_response(400, "bad_request", f"Invalid severity: {severity}")

        where_clauses: list[str] = []
        where_params: list[str | int] = []

        if kind:
            where_clauses.append("kind = %s")
            where_params.append(kind)
        if severity:
            where_clauses.append("severity = %s")
            where_params.append(severity)
        if unread and unread.lower() in ("true", "1", "yes"):
            where_clauses.append("seen = FALSE")

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

        query = f"""
                SELECT id, created_at, kind, severity, title, message, seen, seen_at, symbol, details
                FROM algo_notifications
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT %s
            """
        where_params.append(limit)

        cur.execute(query, tuple(where_params))
        notifs = cur.fetchall()
        response = list_response([safe_json_serialize(safe_dict_convert(n)) for n in notifs])

        # Validate notifications response against contract schema
        is_valid, error_msg = ResponseValidator.validate_endpoint_response("notifs", response["data"])
        if not is_valid:
            logger.error(f"Notifications response validation failed: {error_msg}")
            return error_response(500, "response_validation_error", error_msg)

        return response
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch notifications")
        return error_response(code, error_type, message)


@db_route_handler("get patrol log")
@validate_api_response("health")
def _get_patrol_log(cur: cursor, limit: int = 50, offset: int = 0) -> Any:
    cur.execute("SELECT COUNT(*) as total FROM data_patrol_log")
    row = cur.fetchone()
    if not row:
        # COUNT(*) always returns a row, even if table is empty (result is 0)
        raise RuntimeError("[PATROL_LOG] COUNT(*) query returned no row - database may be corrupted")

    row = safe_dict_convert(row)
    total_raw = row.get("total")
    if total_raw is None:
        raise RuntimeError("[PATROL_LOG] COUNT(*) returned NULL total - database corruption detected")
    try:
        total = int(total_raw)
    except (ValueError, TypeError) as e:
        raise ValueError(f"[PATROL_LOG] COUNT(*) total invalid type ({total_raw}): {e}") from e

    cur.execute(
        """
            SELECT created_at, check_name, severity, target_table, message, patrol_run_id
            FROM data_patrol_log
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """,
        (limit, offset),
    )
    findings = cur.fetchall()
    return list_response([safe_json_serialize(safe_dict_convert(f)) for f in findings], total=total)


@db_route_handler("trigger data patrol")
def _trigger_data_patrol() -> Any:
    """Trigger async data patrol ECS task."""
    try:
        ecs = boto3.client("ecs")

        cluster_arn = os.getenv("ECS_CLUSTER_ARN", "")
        task_def_arn = os.getenv("PATROL_TASK_DEFINITION_ARN", "")
        subnet_ids = os.getenv("PATROL_SUBNET_IDS", "").split(",") if os.getenv("PATROL_SUBNET_IDS") else []
        sg_id = os.getenv("PATROL_SECURITY_GROUP_ID", "")

        # FIXED Issue #19: Validate patrol task definition before attempting to run
        if not cluster_arn or not task_def_arn:
            logger.error("Patrol task not configured (missing ECS_CLUSTER_ARN or PATROL_TASK_DEFINITION_ARN)")
            return error_response(
                400,
                "bad_request",
                "Patrol service not configured (check environment variables)",
            )

        # Validate task definition ARN format
        if not task_def_arn.startswith("arn:aws:ecs:"):
            logger.error(f"Invalid patrol task definition ARN format: {task_def_arn}")
            return error_response(400, "bad_request", "Invalid patrol task definition configuration")

        # Attempt to validate task definition exists (early fail if misconfigured)
        try:
            ecs.describe_task_definition(taskDefinition=task_def_arn)
            logger.info(f"Patrol task definition validated: {task_def_arn}")
        except ClientError as desc_err:
            if desc_err.response["Error"]["Code"] == "ClientException":
                logger.error(f"Patrol task definition not found: {task_def_arn}")
                return error_response(400, "bad_request", "Patrol task definition not found")
            raise  # Re-raise other errors to be caught by outer exception handler

        response = ecs.run_task(
            cluster=cluster_arn,
            taskDefinition=task_def_arn,
            launchType="FARGATE",
            networkConfiguration=(
                {
                    "awsvpcConfiguration": {
                        "subnets": subnet_ids,
                        "securityGroups": [sg_id] if sg_id else [],
                        "assignPublicIp": "DISABLED",
                    }
                }
                if subnet_ids and sg_id
                else None
            ),
        )

        if response["tasks"]:
            task_arn = response["tasks"][0]["taskArn"]
            logger.info(f"Triggered data patrol ECS task: {task_arn}")
            return json_response(
                202,
                {
                    "status": "triggered",
                    "message": "Data patrol triggered",
                    "task_arn": task_arn,
                    "task_id": task_arn.split("/")[-1],
                },
            )
        else:
            logger.error(f"Failed to run patrol task: {response.get('failures')}")
            return error_response(500, "internal_error", "Failed to trigger patrol task")
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ClusterNotFoundException":
            logger.error(f"ECS cluster not found: {error_code}")
            return error_response(503, "service_unavailable", "Patrol service not configured")
        elif error_code == "InvalidParameterException":
            logger.error(f"Invalid ECS parameters: {error_code}")
            return error_response(503, "service_unavailable", "Patrol service configuration invalid")
        else:
            logger.error(f"AWS error triggering patrol: {error_code}", exc_info=True)
            return error_response(503, "service_unavailable", "Unable to trigger patrol service")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "trigger data patrol")
        return error_response(code, error_type, message)
