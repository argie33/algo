"""Route: admin"""

import logging
import os
from datetime import datetime, timedelta, timezone

import boto3
import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from models.requests import VerifyUserEmailRequest
from pydantic import ValidationError
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    list_response,
    normalize_to_utc_datetime,
    safe_json_serialize,
)

# setup_imports is imported by parent module (lambda_function or api_router),
# so utils is already available in sys.path
from utils.rate_limiting import ADMIN_RATE_LIMITS, check_admin_rate_limit
from utils.validation import CognitoValidator

from ..types import JWTClaims, RouteBody, RouteParams, RouteResponse


logger = logging.getLogger(__name__)


def _check_admin_access(jwt_claims: dict) -> bool:
    """Check if user has admin access from verified JWT claims only.

    Checks the 'cognito:groups' claim for 'admin' group membership.
    Never trust role from query params - only from JWT signature.
    Validates JWT claims structure before checking group membership.
    """
    return CognitoValidator.validate_admin_access(jwt_claims)


def _audit_log_admin_action(
    cur, user_id: str, endpoint: str, status: str = "success", details: str = ""
) -> None:
    """Log all admin actions for accountability."""
    try:
        import json as _json

        cur.execute(
            """
            INSERT INTO algo_audit_log (action_type, actor, status, details, action_date, created_at)
            VALUES (%s, %s, %s, %s, NOW(), NOW())
        """,
            (
                "admin_access",
                user_id,
                status,
                _json.dumps({"endpoint": endpoint, "details": details}),
            ),
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        logger.warning(f"[AUDIT_LOG] Database error: {type(e).__name__}: {e}")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.warning(f"[AUDIT_LOG] Unexpected error: {type(e).__name__}: {e}")


def handle(
    cur,
    path: str,
    method: str,
    params: RouteParams,
    body: RouteBody | None = None,
    jwt_claims: JWTClaims | None = None,
) -> RouteResponse:
    """Handle /api/admin/* endpoints for operational visibility."""
    try:
        # Require admin role for all admin endpoints (bypass in dev mode)
        if not _check_admin_access(
            jwt_claims
        ):
            user_id = (jwt_claims or {}).get("sub", "unknown")
            _audit_log_admin_action(
                cur, user_id, path, "denied", "insufficient permissions"
            )
            return error_response(403, "forbidden", "Admin access required")

        user_id = (jwt_claims or {}).get("sub", "unknown")

        # SECURITY FIX S-09: Rate limit admin endpoints to prevent abuse
        if path in ADMIN_RATE_LIMITS:
            limits = ADMIN_RATE_LIMITS[path]
            is_allowed, error_msg = check_admin_rate_limit(
                user_id,
                path,
                max_requests=limits["max_requests"],
                window_seconds=limits["window"],
            )
            if not is_allowed:
                _audit_log_admin_action(
                    cur, user_id, path, "denied", f"rate_limited: {error_msg}"
                )
                return error_response(429, "too_many_requests", error_msg)

        if path == "/api/admin/loader-status":
            result = _get_loader_status(cur)
            _audit_log_admin_action(cur, user_id, path, "success")
            return result
        elif path == "/api/admin/system-health":
            result = _get_system_health(cur)
            _audit_log_admin_action(cur, user_id, path, "success")
            return result
        elif path == "/api/admin/database-stats":
            result = _get_database_stats(cur)
            _audit_log_admin_action(cur, user_id, path, "success")
            return result
        elif path == "/api/admin/data-quality":
            result = _get_data_quality(cur)
            _audit_log_admin_action(cur, user_id, path, "success")
            return result
        elif path == "/api/admin/verify-user-email" and method == "POST":
            result = _verify_user_email(body)
            _audit_log_admin_action(
                cur,
                user_id,
                path,
                "success",
                f"verified: {body.get('username', 'unknown')}",
            )
            return result

        _audit_log_admin_action(cur, user_id, path, "failed", "endpoint not found")
        return error_response(404, "not_found", f"No admin handler for {path}")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle admin")
        return error_response(code, error_type, message)


@db_route_handler("get loader status")
def _get_loader_status(cur) -> dict:
    """Get status of all data loaders from data_loader_status table.

    Reads from data_loader_status, which OptimalLoader updates after each run
    with the table's current row count and latest watermark date.
    """
    cur.execute("SET LOCAL statement_timeout = '5000ms'")
    cur.execute("""
        SELECT
            table_name,
            row_count,
            latest_date,
            last_updated,
            status,
            error_message
        FROM data_loader_status
        ORDER BY last_updated DESC NULLS LAST, table_name
    """)
    rows = cur.fetchall()

    if not rows:
        response = list_response([], total=0, limit=None, offset=None)
        response["data"]["status"] = "no_runs"
        response["data"]["message"] = "No loader runs recorded yet"
        return response

    now = datetime.now(timezone.utc)
    loaders = []
    for row in rows:
        last_updated = normalize_to_utc_datetime(row["last_updated"])
        if last_updated:
            age_hours = (now - last_updated).total_seconds() / 3600
        else:
            age_hours = 9999
        # Loaders run on weekdays only; allow up to 72h (covers 3-day weekends)
        health = "stale" if age_hours > 72 else "fresh"
        status = row["status"] or ("fresh" if age_hours <= 72 else "stale")

        loaders.append(
            {
                "name": row["table_name"],
                "table": row["table_name"],
                "last_run": last_updated.isoformat() if last_updated else None,
                "row_count": row["row_count"],
                "latest_date": (
                    row["latest_date"].isoformat() if row["latest_date"] else None
                ),
                "status": status,
                "age_hours": round(age_hours, 1),
                "health": health,
                "error": row["error_message"],
            }
        )

    try:
        freshness = check_data_freshness(
            cur, "data_loader_status", "last_updated", warning_days=1
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        logger.warning(
            f"[LOADER_STATUS] Freshness check failed: {type(e).__name__}: {e}"
        )
        freshness = None
    except Exception as e:
        logger.warning(
            f"[LOADER_STATUS] Unexpected error in freshness check: {type(e).__name__}: {e}"
        )
        freshness = None
    response = list_response(loaders, total=len(loaders), limit=None, offset=None)
    response["data"]["status"] = "ok"
    response["data"]["summary"] = {
        "total": len(loaders),
        "healthy": len([loader for loader in loaders if loader["health"] == "fresh"]),
        "stale": len([loader for loader in loaders if loader["health"] == "stale"]),
    }
    if freshness:
        response["data_freshness"] = freshness
    return response


@db_route_handler("get system health")
def _get_system_health(cur) -> dict:
    """Get overall system health status."""
    health_data = {"status": "healthy", "components": {}}
    cur.execute("SET LOCAL statement_timeout = '3000ms'")

    try:
        cur.execute("SELECT 1")
        health_data["components"]["database"] = "ok"
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ):
        health_data["components"]["database"] = "error"
        health_data["status"] = "degraded"

    cur.execute("SELECT date FROM price_daily ORDER BY date DESC LIMIT 1")
    last_price_date = next(
        iter(safe_json_serialize(dict(cur.fetchone() or {}).values())), 0
    )
    if last_price_date:
        today = datetime.now(timezone.utc).date()
        age_days = (today - last_price_date).days
        # Use trading-day-aware freshness: data is fresh if it's from the most
        # recent trading day. A hardcoded day threshold causes false 'degraded'
        # on 3-day holiday weekends where Friday data is 4 calendar days old.
        try:
            from algo.infrastructure import MarketCalendar

            expected = today - timedelta(days=1)
            for _ in range(10):
                if MarketCalendar.is_trading_day(expected):
                    break
                expected -= timedelta(days=1)
            is_fresh = last_price_date >= expected
        except ImportError as e:
            logger.warning(
                f"[MARKET_CALENDAR] Import failed: {e} - falling back to age-based check"
            )
            is_fresh = age_days <= 3
        except Exception as e:
            logger.warning(
                f"[MARKET_CALENDAR] Error computing expected trading day: {type(e).__name__}: {e}"
            )
            is_fresh = age_days <= 3
        health_data["components"]["data_freshness"] = "ok" if is_fresh else "stale"
        health_data["last_data_update"] = last_price_date.isoformat()
        if not is_fresh:
            health_data["status"] = "degraded"
    else:
        health_data["components"]["data_freshness"] = "no_data"
        health_data["status"] = "unhealthy"

    table_counts = {}
    tables = ["stock_symbols", "price_daily", "algo_trades", "algo_positions"]
    ",".join([psycopg2.sql.SQL("{}").format(psycopg2.sql.Identifier(t)).as_string(cur) for t in tables])
    try:
        cur.execute("""
            SELECT
                'stock_symbols' as table_name, COUNT(*) as cnt FROM stock_symbols
            UNION ALL
            SELECT 'price_daily', COUNT(*) FROM price_daily
            UNION ALL
            SELECT 'algo_trades', COUNT(*) FROM algo_trades
            UNION ALL
            SELECT 'algo_positions', COUNT(*) FROM algo_positions
        """)
        for row in cur.fetchall():
            row_dict = safe_json_serialize(dict(row))
            table_name = row_dict.get("table_name")
            count = row_dict.get("cnt", 0)
            table_counts[table_name] = count
    except (psycopg2.Error, TypeError, AttributeError) as e:
        logger.warning(f"Failed to count rows in tables: {e}")
        for table in tables:
            table_counts[table] = 0

    health_data["tables"] = table_counts
    health_data["timestamp"] = datetime.now(timezone.utc).isoformat()
    return json_response(200, health_data)


@db_route_handler("get database stats")
def _get_database_stats(cur) -> dict:
    """Get database statistics (schema-safe version - no table name exposure)."""
    stats = {}
    cur.execute("SET LOCAL statement_timeout = '5000ms'")

    # Count active connections without exposing table structure
    cur.execute("SELECT count(*) FROM pg_stat_activity WHERE state != 'idle'")
    stats["active_connections"] = next(
        iter(safe_json_serialize(dict(cur.fetchone() or {}).values())), 0
    )

    # Get high-level DB size without exposing individual table names
    cur.execute("""
        SELECT pg_size_pretty(pg_database_size(current_database())) as total_size
    """)
    size_row = cur.fetchone()
    stats["total_database_size"] = (
        safe_json_serialize(dict(size_row)).get("total_size", "unknown")
        if size_row
        else "unknown"
    )

    # Check if any tables exist without revealing names
    cur.execute("""
        SELECT COUNT(*) as table_count FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    """)
    table_count_row = cur.fetchone()
    stats["table_count"] = (
        safe_json_serialize(dict(table_count_row)).get("table_count", 0)
        if table_count_row
        else 0
    )

    stats["timestamp"] = datetime.now(timezone.utc).isoformat()
    return json_response(200, stats)


@db_route_handler("get data quality")
def _get_data_quality(cur) -> dict:
    """Get data quality metrics."""
    quality = {"timestamp": datetime.now(timezone.utc).isoformat(), "checks": {}}
    cur.execute("SET LOCAL statement_timeout = '10000ms'")

    cur.execute("""
        SELECT COUNT(*) FROM price_daily
        WHERE close IS NULL OR open IS NULL OR high IS NULL OR low IS NULL
    """)
    null_prices = next(
        iter(safe_json_serialize(dict(cur.fetchone() or {}).values())), 0
    )
    quality["checks"]["null_prices"] = {
        "count": null_prices,
        "status": "ok" if null_prices == 0 else "warning",
    }

    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT symbol, date, COUNT(*)
            FROM price_daily
            GROUP BY symbol, date HAVING COUNT(*) > 1
        ) t
    """)
    duplicate_prices = next(
        iter(safe_json_serialize(dict(cur.fetchone() or {}).values())), 0
    )
    quality["checks"]["duplicate_prices"] = {
        "count": duplicate_prices,
        "status": "ok" if duplicate_prices == 0 else "warning",
    }

    cur.execute("""
        SELECT COUNT(*) FROM price_daily
        WHERE high < low OR close > high OR close < low
    """)
    invalid_prices = next(
        iter(safe_json_serialize(dict(cur.fetchone() or {}).values())), 0
    )
    quality["checks"]["invalid_price_ranges"] = {
        "count": invalid_prices,
        "status": "ok" if invalid_prices == 0 else "error",
    }

    # Overall status
    quality["status"] = "healthy" if invalid_prices == 0 else "degraded"

    return json_response(200, quality)


def _verify_user_email(body: dict | None = None) -> dict:
    """Verify a user's email in Cognito (dev/testing only)."""
    try:
        req = VerifyUserEmailRequest(**(body or {}))
    except ValidationError as e:
        errors = e.errors()
        if errors:
            error_detail = errors[0]
            field = error_detail.get("loc", ("unknown",))[0]
            msg = error_detail.get("msg", "Validation failed")
            return error_response(400, "bad_request", f"Invalid {field}: {msg}")
        return error_response(400, "bad_request", "Invalid request")

    try:
        cognito_user_pool_id = os.getenv("COGNITO_USER_POOL_ID", "").strip()
        cognito_region = os.getenv("COGNITO_REGION", "us-east-1").strip()

        if not cognito_user_pool_id:
            return error_response(503, "service_unavailable", "Cognito service not configured")

        cognito_client = boto3.client("cognito-idp", region_name=cognito_region)
        username = req.username

        # Update user attributes to mark email as verified
        response = cognito_client.admin_update_user_attributes(
            UserPoolId=cognito_user_pool_id,
            Username=username,
            UserAttributes=[{"Name": "email_verified", "Value": "true"}],
        )

        # Validate Cognito response
        if not isinstance(response, dict):
            logger.error(
                f"Invalid Cognito response type: {type(response).__name__}. "
                f"Expected dict."
            )
            return error_response(
                503, "cognito_error", "Invalid response from Cognito service"
            )

        # Check for error in response
        if response.get("Error"):
            error_msg = response["Error"].get("Message", "Unknown error")
            logger.error(f"Cognito error: {error_msg}")
            return error_response(503, "cognito_error", f"Cognito error: {error_msg}")

        # Verify HTTP status indicates success
        http_status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if http_status not in (200, 201):
            logger.error(
                f"Cognito returned unexpected status code: {http_status}. "
                f"Expected 200 or 201."
            )
            return error_response(
                503,
                "cognito_error",
                f"Cognito operation failed with status {http_status}",
            )

        logger.info(f"Email verified for user: {username}")
        return json_response(
            200,
            {
                "status": "success",
                "message": f"Email verified for {username}",
                "username": username,
            },
        )
    except Exception as e:
        error_str = str(e)
        if "UserNotFoundException" in error_str:
            return error_response(
                404, "not_found", f'User not found: {body.get("username")}'
            )
        logger.error(f"Failed to verify email: {e}")
        return error_response(503, "service_unavailable", "Failed to verify email with Cognito service")
