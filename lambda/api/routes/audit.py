"""Route: audit"""

import logging
import os
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    handle_db_error,
    list_response,
    safe_json_serialize,
    safe_limit,
    safe_offset,
)

logger = logging.getLogger(__name__)


def _check_admin_access(jwt_claims: dict | None) -> bool:
    """Check if user has admin access from verified JWT claims.

    Only admin users can view audit logs.
    Audit logs contain sensitive trading decisions and system internals.
    """
    if not jwt_claims:
        return False
    groups = jwt_claims.get("cognito:groups")
    if groups is None:
        groups = []
    is_admin = "admin" in groups
    if not is_admin:
        logger.info(f"Audit access denied: user {jwt_claims.get('sub')} not in admin group. Groups: {groups}")
    return is_admin


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/audit/* endpoints."""
    # Require admin authorization for all audit endpoints (bypass in dev mode)
    if os.environ.get("DEV_BYPASS_AUTH") != "true" and not _check_admin_access(jwt_claims):
        return error_response(403, "forbidden", "Admin access required to view audit logs")

    try:
        # CRITICAL: Fail-fast on malformed params. Extract safely with validation.
        limit_str = None
        offset_str = None

        if params:
            limit_list = params.get("limit")
            if limit_list:
                if not isinstance(limit_list, list) or not limit_list:
                    raise ValueError("CRITICAL: 'limit' parameter must be a non-empty list")
                limit_str = limit_list[0]
                if limit_str and not isinstance(limit_str, str):
                    limit_str = str(limit_str)

            offset_list = params.get("offset")
            if offset_list:
                if not isinstance(offset_list, list) or not offset_list:
                    raise ValueError("CRITICAL: 'offset' parameter must be a non-empty list")
                offset_str = offset_list[0]
                if offset_str and not isinstance(offset_str, str):
                    offset_str = str(offset_str)

        limit = safe_limit(limit_str or "500", max_val=5000)
        offset = safe_offset(offset_str or "0")
        cur.execute("SET LOCAL statement_timeout = '10000ms'")

        if path == "/api/audit/trail" or path.startswith("/api/audit/trail?"):
            cur.execute(
                """
                    SELECT id, created_at, action_type AS action,
                           actor AS user_id, status, details
                    FROM algo_audit_log
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            audits = cur.fetchall()
            cur.execute("SELECT COUNT(*) FROM algo_audit_log")
            count_row = cur.fetchone()
            total = next(iter(safe_json_serialize(dict(count_row).values())), 0) if count_row else 0
            freshness = check_data_freshness(cur, "algo_audit_log", "created_at", warning_days=1)
            return list_response(
                [safe_json_serialize(dict(a)) for a in audits] if audits else [],
                total=total,
                data_freshness=freshness,
            )

        elif path == "/api/audit/trades" or path.startswith("/api/audit/trades?"):
            cur.execute(
                """
                    SELECT id, created_at, action_type,
                           symbol, actor, status, error_message, details
                    FROM algo_audit_log
                    WHERE action_type IN ('entry', 'exit', 'partial_exit')
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            audits = cur.fetchall()
            cur.execute("""
                    SELECT COUNT(*) FROM algo_audit_log
                    WHERE action_type IN ('entry', 'exit', 'partial_exit')
                """)
            count_row = cur.fetchone()
            total = next(iter(safe_json_serialize(dict(count_row).values())), 0) if count_row else 0
            freshness = check_data_freshness(cur, "algo_audit_log", "created_at", warning_days=1)
            return list_response(
                [safe_json_serialize(dict(a)) for a in audits] if audits else [],
                total=total,
                data_freshness=freshness,
            )

        elif path == "/api/audit/config" or path.startswith("/api/audit/config?"):
            cur.execute(
                """
                    SELECT id, created_at, action_type,
                           actor, status, error_message, details
                    FROM algo_audit_log
                    WHERE action_type LIKE 'config%' OR action_type = 'settings_change'
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            audits = cur.fetchall()
            cur.execute("""
                    SELECT COUNT(*) FROM algo_audit_log
                    WHERE action_type LIKE 'config%' OR action_type = 'settings_change'
                """)
            count_row = cur.fetchone()
            total = next(iter(safe_json_serialize(dict(count_row).values())), 0) if count_row else 0
            freshness = check_data_freshness(cur, "algo_audit_log", "created_at", warning_days=1)
            return list_response(
                [safe_json_serialize(dict(a)) for a in audits] if audits else [],
                total=total,
                data_freshness=freshness,
            )

        elif path == "/api/audit/safeguards" or path.startswith("/api/audit/safeguards?"):
            cur.execute(
                """
                    SELECT id, created_at, action_type,
                           actor, status, error_message, details
                    FROM algo_audit_log
                    WHERE action_type IN ('circuit_breaker_halt', 'circuit_breaker', 'safeguard', 'halt', 'exposure_policy')
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            audits = cur.fetchall()
            cur.execute("""
                    SELECT COUNT(*) FROM algo_audit_log
                    WHERE action_type IN ('circuit_breaker_halt', 'circuit_breaker', 'safeguard', 'halt', 'exposure_policy')
                """)
            count_row = cur.fetchone()
            total = next(iter(safe_json_serialize(dict(count_row).values())), 0) if count_row else 0
            freshness = check_data_freshness(cur, "algo_audit_log", "created_at", warning_days=1)
            return list_response(
                [safe_json_serialize(dict(a)) for a in audits] if audits else [],
                total=total,
                data_freshness=freshness,
            )

        return error_response(404, "not_found", f"No audit handler for {path}")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle audit")
        return error_response(code, error_type, message)
