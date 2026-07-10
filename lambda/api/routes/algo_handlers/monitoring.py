"""Route: algo"""

from __future__ import annotations

import logging
import os
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
    """Return algo audit log entries with pagination."""
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
    """Get the most recent orchestrator run with halt reason."""
    cur.execute("""
        SELECT run_id, run_date, overall_status, halt_reason, started_at, completed_at,
               phase_results
        FROM orchestrator_execution_log
        ORDER BY created_at DESC
        LIMIT 1
    """)
    latest = cur.fetchone()
    if latest is None:
        return error_response(503, "no_data", "No orchestrator run data available yet")

    latest_dict = safe_json_serialize(safe_dict_convert(latest))

    run_id = latest_dict.get("run_id")
    overall_status = latest_dict.get("overall_status")
    halt_reason = latest_dict.get("halt_reason")
    started_at = latest_dict.get("started_at")
    completed_at = latest_dict.get("completed_at")
    phase_results = latest_dict.get("phase_results")

    # Compute phases_completed from phase_results JSONB
    phases_completed = 0
    if phase_results:
        try:
            if isinstance(phase_results, str):
                import json
                phase_results = json.loads(phase_results)
            if isinstance(phase_results, list):
                phases_completed = len([p for p in phase_results if p.get("status") == "success"])
        except (ValueError, TypeError, KeyError):
            phases_completed = 0

    if not run_id:
        return error_response(503, "invalid_data", "Run ID missing from orchestrator execution log")
    if overall_status is None:
        return error_response(503, "invalid_data", "Overall status missing from orchestrator execution log")

    # Determine success/halted/errored from overall_status
    success = overall_status == "success"
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


@db_route_handler("fetch notifications")
@validate_api_response("notifs")
def _get_notifications(
    cur: cursor, params: dict[str, Any] | None = None, jwt_claims: dict[str, Any] | None = None
) -> Any:
    """Get recent notifications. System broadcasts visible to all authenticated users."""
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
    """Get data patrol findings with pagination."""
    cur.execute("SELECT COUNT(*) as total FROM data_patrol_log")
    row = cur.fetchone()
    total = row["total"] if row else 0

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
