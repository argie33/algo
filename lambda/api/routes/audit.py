"""Route: audit"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, safe_offset, handle_db_error, check_data_freshness

logger = logging.getLogger(__name__)

def _check_admin_access(jwt_claims: Dict) -> bool:
    """Check if user has admin access from verified JWT claims.

    Only admin users can view audit logs.
    Audit logs contain sensitive trading decisions and system internals.
    """
    if not jwt_claims:
        return False
    groups = jwt_claims.get('cognito:groups') or []
    is_admin = 'admin' in groups
    if not is_admin:
        logger.info(f"Audit access denied: user {jwt_claims.get('sub')} not in admin group. Groups: {groups}")
    return is_admin

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
        """Handle /api/audit/* endpoints."""
        # Require admin authorization for all audit endpoints
        if not _check_admin_access(jwt_claims):
            return error_response(403, 'forbidden', 'Admin access required to view audit logs')

        try:
            limit_str = params.get('limit', [None])[0] if params else None
            offset_str = params.get('offset', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=5000, default=500)
            offset = safe_offset(offset_str)
            cur.execute("SET LOCAL statement_timeout = '10000ms'")

            if path == '/api/audit/trail' or path.startswith('/api/audit/trail?'):
                cur.execute("""
                    SELECT id, created_at AS timestamp, action_type AS action,
                           actor AS user_id, status, details
                    FROM algo_audit_log
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                audits = cur.fetchall()
                cur.execute("SELECT COUNT(*) FROM algo_audit_log")
                total = next(iter(dict(cur.fetchone() or {}).values()), 0)
                freshness = check_data_freshness(cur, 'algo_audit_log', 'created_at', warning_days=1)
                return list_response([dict(a) for a in audits] if audits else [], total=total, data_freshness=freshness)

            elif path == '/api/audit/trades' or path.startswith('/api/audit/trades?'):
                cur.execute("""
                    SELECT id, created_at AS timestamp, action_type,
                           symbol, actor, status, error_message, details
                    FROM algo_audit_log
                    WHERE action_type IN ('entry', 'exit', 'partial_exit', 'pyramid')
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                audits = cur.fetchall()
                cur.execute("""
                    SELECT COUNT(*) FROM algo_audit_log
                    WHERE action_type IN ('entry', 'exit', 'partial_exit', 'pyramid')
                """)
                total = next(iter(dict(cur.fetchone() or {}).values()), 0)
                freshness = check_data_freshness(cur, 'algo_audit_log', 'created_at', warning_days=1)
                return list_response([dict(a) for a in audits] if audits else [], total=total, data_freshness=freshness)

            elif path == '/api/audit/config' or path.startswith('/api/audit/config?'):
                cur.execute("""
                    SELECT id, created_at AS timestamp, action_type,
                           actor, status, error_message, details
                    FROM algo_audit_log
                    WHERE action_type LIKE 'config%' OR action_type = 'settings_change'
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                audits = cur.fetchall()
                cur.execute("""
                    SELECT COUNT(*) FROM algo_audit_log
                    WHERE action_type LIKE 'config%' OR action_type = 'settings_change'
                """)
                total = next(iter(dict(cur.fetchone() or {}).values()), 0)
                freshness = check_data_freshness(cur, 'algo_audit_log', 'created_at', warning_days=1)
                return list_response([dict(a) for a in audits] if audits else [], total=total, data_freshness=freshness)

            elif path == '/api/audit/safeguards' or path.startswith('/api/audit/safeguards?'):
                cur.execute("""
                    SELECT id, created_at AS timestamp, action_type,
                           actor, status, error_message, details
                    FROM algo_audit_log
                    WHERE action_type IN ('circuit_breaker_halt', 'circuit_breaker', 'safeguard', 'halt', 'exposure_policy')
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                audits = cur.fetchall()
                cur.execute("""
                    SELECT COUNT(*) FROM algo_audit_log
                    WHERE action_type IN ('circuit_breaker_halt', 'circuit_breaker', 'safeguard', 'halt', 'exposure_policy')
                """)
                total = next(iter(dict(cur.fetchone() or {}).values()), 0)
                freshness = check_data_freshness(cur, 'algo_audit_log', 'created_at', warning_days=1)
                return list_response([dict(a) for a in audits] if audits else [], total=total, data_freshness=freshness)

            return error_response(404, 'not_found', f'No audit handler for {path}')
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'handle audit')
