"""Route: algo"""

import logging
import os

import boto3
import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from botocore.exceptions import ClientError

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    list_response,
    safe_dict_convert,
    safe_json_serialize,
    safe_limit,
)


logger = logging.getLogger(__name__)



@db_route_handler("get algo audit log")
def _get_algo_audit_log(
    cur, limit: int = 100, offset: int = 0, action_type: str = None
) -> dict:
    """Return algo audit log entries with pagination."""
    if action_type:
        cur.execute(
            "SELECT COUNT(*) as total FROM algo_audit_log WHERE action_type = %s",
            (action_type,),
        )
    else:
        cur.execute("SELECT COUNT(*) as total FROM algo_audit_log")
    total = cur.fetchone()["total"]

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
def _get_last_run(cur) -> dict:
    """Get the most recent orchestrator run with per-phase status."""
    cur.execute("""
        SELECT details->>'run_id' AS run_id, MAX(created_at) AS run_at
        FROM algo_audit_log
        WHERE details->>'run_id' IS NOT NULL
        GROUP BY details->>'run_id'
        ORDER BY MAX(created_at) DESC
        LIMIT 1
    """)
    latest = cur.fetchone()
    if not latest or not latest["run_id"]:
        return json_response(
            200, {"run_id": None, "run_at": None, "halted": False, "phases": []}
        )

    run_id = latest["run_id"]
    run_at = latest["run_at"]

    cur.execute(
        """
        SELECT action_type, status, action_date, created_at,
               details->>'summary' AS summary,
               error_message AS error
        FROM algo_audit_log
        WHERE details->>'run_id' = %s
        ORDER BY created_at ASC
    """,
        (run_id,),
    )
    phases = [safe_json_serialize(safe_dict_convert(r)) for r in cur.fetchall()]

    halted = any(p.get("status") in ("halt", "halted") for p in phases)
    errored = any(p.get("status") == "error" for p in phases)
    success = len(phases) > 0 and not errored and not halted

    return json_response(
        200,
        {
            "run_id": run_id,
            "run_at": run_at.isoformat() if run_at else None,
            "success": success,
            "halted": halted,
            "phases": phases,
        },
    )



@db_route_handler("fetch notifications")
def _get_notifications(cur, params: dict = None, jwt_claims: dict = None) -> dict:
    """Get recent notifications. System broadcasts visible to all authenticated users."""
    try:
        params = params or {}
        kind = params.get("kind", [None])[0] if params.get("kind") else None
        severity = params.get("severity", [None])[0] if params.get("severity") else None
        unread = params.get("unread", [None])[0] if params.get("unread") else None
        limit_str = params.get("limit", [None])[0] if params.get("limit") else None
        limit = safe_limit(limit_str, max_val=10000, default=100)

        # SECURITY M-04: Validate kind and severity against whitelists
        VALID_KINDS = {
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
        VALID_SEVERITIES = {"info", "warning", "error", "critical"}

        if kind and kind not in VALID_KINDS:
            return error_response(400, "bad_request", f"Invalid kind: {kind}")
        if severity and severity not in VALID_SEVERITIES:
            return error_response(400, "bad_request", f"Invalid severity: {severity}")

        where_clauses = []
        where_params = []

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
        return list_response(
            [safe_json_serialize(safe_dict_convert(n)) for n in notifs]
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Failed to fetch notifications: {type(e).__name__}: {e!s}\n  Operation: Query algo_notifications\n  Endpoint: GET /api/algo/notifications",
            exc_info=True,
        )
        return error_response(500, "internal_error", "Failed to fetch notifications")



@db_route_handler("get patrol log")
def _get_patrol_log(cur, limit: int = 50, offset: int = 0) -> dict:
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
    return list_response(
        [safe_json_serialize(safe_dict_convert(f)) for f in findings], total=total
    )



@db_route_handler("trigger data patrol")
def _trigger_data_patrol() -> dict:
    """Trigger async data patrol ECS task."""
    try:
        ecs = boto3.client("ecs")

        cluster_arn = os.getenv("ECS_CLUSTER_ARN", "")
        task_def_arn = os.getenv("PATROL_TASK_DEFINITION_ARN", "")
        subnet_ids = (
            os.getenv("PATROL_SUBNET_IDS", "").split(",")
            if os.getenv("PATROL_SUBNET_IDS")
            else []
        )
        sg_id = os.getenv("PATROL_SECURITY_GROUP_ID", "")

        # FIXED Issue #19: Validate patrol task definition before attempting to run
        if not cluster_arn or not task_def_arn:
            logger.error(
                "Patrol task not configured (missing ECS_CLUSTER_ARN or PATROL_TASK_DEFINITION_ARN)"
            )
            return error_response(
                400,
                "bad_request",
                "Patrol service not configured (check environment variables)",
            )

        # Validate task definition ARN format
        if not task_def_arn.startswith("arn:aws:ecs:"):
            logger.error(f"Invalid patrol task definition ARN format: {task_def_arn}")
            return error_response(
                400, "bad_request", "Invalid patrol task definition configuration"
            )

        # Attempt to validate task definition exists (early fail if misconfigured)
        try:
            ecs.describe_task_definition(taskDefinition=task_def_arn)
            logger.info(f"Patrol task definition validated: {task_def_arn}")
        except ClientError as desc_err:
            if desc_err.response["Error"]["Code"] == "ClientException":
                logger.error(f"Patrol task definition not found: {task_def_arn}")
                return error_response(
                    400, "bad_request", "Patrol task definition not found"
                )
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
            logger.error(f"Failed to run patrol task: {response.get('failures', [])}")
            return error_response(
                500, "internal_error", "Failed to trigger patrol task"
            )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ClusterNotFoundException":
            logger.error(f"ECS cluster not found: {error_code}")
            return error_response(
                503, "service_unavailable", "Patrol service not configured"
            )
        elif error_code == "InvalidParameterException":
            logger.error(f"Invalid ECS parameters: {error_code}")
            return error_response(
                503, "service_unavailable", "Patrol service configuration invalid"
            )
        else:
            logger.error(f"AWS error triggering patrol: {error_code}", exc_info=True)
            return error_response(
                503, "service_unavailable", "Unable to trigger patrol service"
            )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "trigger data patrol")
        return error_response(code, error_type, message)



