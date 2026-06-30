"""Route: health - Health check endpoints (basic, detailed, pipeline)"""

import logging
from datetime import datetime, timezone
from typing import Any

from api_utils.config import get_config
from psycopg2.extensions import cursor
from routes.utils import (
    error_response,
    execute_with_timeout,
    handle_db_error,
    safe_json_serialize,
    success_response,
)

from shared_contracts.response_validator import ResponseValidator

logger = logging.getLogger(__name__)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> Any:
    """Handle health check endpoints.

    /api/health — PUBLIC, no auth required. Basic system status.
    /api/health/cognito — PUBLIC, no auth required. C-7 FIX: Verify Cognito client ID matches configuration.
    /api/health/detailed — AUTHENTICATED. Database schema and table status.
    /api/health/pipeline — AUTHENTICATED. Data freshness of critical loaders.
    """

    # Route to appropriate handler
    if path.startswith(("/api/health/cognito", "/health/cognito")):
        return _handle_cognito(cur)
    elif path.startswith(("/api/health/detailed", "/health/detailed")):
        return _handle_detailed(cur, jwt_claims)
    elif path.startswith(("/api/health/pipeline", "/health/pipeline")):
        return _handle_pipeline(cur, jwt_claims)
    else:
        # Basic health check (default for /api/health)
        return _handle_basic(cur)


def _handle_basic(cur: cursor) -> Any:
    """Basic health check - PUBLIC, no auth required.

    Fast health check: DB connectivity + key metrics (optimized).
    Uses simple, indexed queries only. Complex checks move to /health/detailed.
    """
    from api_router import get_import_status as get_api_import_status

    import_status = get_api_import_status()

    health: dict[str, Any] = {
        "status": "healthy",
        "version": "v2-2026-06-06",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    has_critical = False

    # C-4 FIX: Report API route import failures in health check (FAIL FAST)
    if "failed_routes" not in import_status or import_status["failed_routes"] is None:
        error_msg = (
            "[HEALTH CRITICAL] API route import status unavailable. Cannot report health without knowing route status."
        )
        logger.error(error_msg)
        return error_response(503, "route_import_status_unavailable", error_msg)

    failed_routes = int(import_status["failed_routes"])
    if failed_routes > 0:
        # CRITICAL: Never silently default to empty lists for failure data
        # Missing failure lists indicates data layer error, not "no failures"
        critical_failures = import_status.get("critical_failures")
        failed_modules = import_status.get("failed_modules")

        if critical_failures is None or failed_modules is None:
            error_msg = (
                f"[HEALTH] Import status degraded but failure details missing. "
                f"critical_failures={critical_failures}, failed_modules={failed_modules}. "
                f"Data layer error - cannot render complete health status."
            )
            logger.error(error_msg)
            return error_response(503, "incomplete_failure_data", error_msg)

        health["api_route_imports"] = {
            "status": "degraded",
            "failed_count": import_status["failed_routes"],
            "critical_failures": critical_failures,
            "failed_modules": failed_modules,
        }
        if critical_failures:
            has_critical = True
    else:
        health["api_route_imports"] = {"status": "healthy", "failed_count": 0}

    try:
        # Verify DB connectivity (2 second timeout)
        result = execute_with_timeout(cur, "SELECT 1", timeout_sec=2)
        if not result:
            return error_response(503, "connection_error", "Database connection failed")

        # Signal freshness check using swing_trader_scores (primary signal source).
        # signal_quality_scores was removed from the pipeline; swing_trader_scores replaced it.
        # MAX(date) uses the btree index on date; ORDER BY created_at had no index and scanned
        # the full table, timing out on every health request.
        try:
            from algo.infrastructure import MarketCalendar

            market_cal = MarketCalendar()
            market_is_open = market_cal.is_market_open(datetime.now(timezone.utc))

            signal_check = execute_with_timeout(
                cur,
                "SELECT MAX(date)::timestamp AS latest_signal FROM swing_trader_scores",
                timeout_sec=2,
            )

            if signal_check and len(signal_check) > 0:
                latest = signal_check[0]["latest_signal"]
                if latest:
                    age_hours = (
                        datetime.now(timezone.utc) - latest.replace(tzinfo=timezone.utc)
                    ).total_seconds() / 3600
                    config = get_config()
                    # Only mark as critical if market is open AND signals are stale
                    # During market closure (nights/weekends), stale data is expected
                    if age_hours > config.signal_stale_threshold_hours and market_is_open:
                        has_critical = True
                        health["freshness"] = {
                            "status": "STALE",
                            "signal_age_hours": round(age_hours, 1),
                            "market_open": market_is_open,
                        }
                    else:
                        health["freshness"] = {
                            "status": "OK",
                            "signal_age_hours": round(age_hours, 1),
                            "market_open": market_is_open,
                        }
                else:
                    # No signal data available — cannot verify freshness
                    error_msg = (
                        "[HEALTH CRITICAL] Signal data unavailable. Cannot assess signal freshness for health status."
                    )
                    logger.error(error_msg)
                    has_critical = True
                    health["freshness"] = {
                        "status": "NO_DATA",
                        "error": "Signal table empty or data unavailable",
                        "market_open": market_is_open,
                    }
        except Exception as e:
            from utils.error_handlers import sanitize_error_message

            sanitized = sanitize_error_message(str(e)[:60])
            logger.error(f"[HEALTH CRITICAL] Signal freshness check failed: {sanitized}")
            has_critical = True
            health["freshness"] = {
                "status": "ERROR",
                "error": f"Cannot verify signal freshness: {sanitized}",
            }

        # Last successful loader timestamp (indexed query, 1 second timeout)
        try:
            loader_check = execute_with_timeout(
                cur,
                """
                SELECT MAX(last_updated) as latest_load
                FROM data_loader_status
                WHERE status='success'
                LIMIT 1
            """,
                timeout_sec=1,
            )

            if loader_check and len(loader_check) > 0:
                latest_load = loader_check[0]["latest_load"]
                if latest_load:
                    health["last_load_time"] = (
                        latest_load.isoformat() if hasattr(latest_load, "isoformat") else str(latest_load)
                    )
        except Exception as e:
            from utils.error_handlers import sanitize_error_message

            sanitized = sanitize_error_message(str(e)[:60])
            logger.debug(f"Loader check unavailable: {sanitized}")

        if has_critical:
            logger.error(f"Health check detected critical issues: {health}")
            return error_response(503, "service_unavailable", "Critical health check failed - see details for issues")

        # Validate response matches contract before returning
        is_valid, error_msg = ResponseValidator.validate_endpoint_response("health", health)
        if not is_valid:
            logger.error(f"Health response validation failed: {error_msg}")
            return error_response(500, "response_validation_error", error_msg)

        return success_response(health)

    except Exception as e:
        code, error_type, message = handle_db_error(e, "health check")
        return error_response(code, error_type, message)


def _handle_cognito(cur: cursor) -> Any:
    """C-7 FIX: Verify Cognito client ID matches AWS Cognito configuration.

    This endpoint is called by pre-deploy validation (GitHub Actions) to ensure
    the COGNITO_CLIENT_ID environment variable matches the actual Cognito user pool
    configuration. If mismatch is detected, deployment should be blocked.

    Returns:
    - status: 'healthy' if client ID matches, 'misconfigured' if mismatch
    - configured_client_id: Value from COGNITO_CLIENT_ID env var
    - cognito_client_id: Actual client ID from Cognito (if verifiable)
    - cognito_user_pool_id: User pool ID from config
    """
    import os

    import boto3

    try:
        configured_client_id = os.getenv("COGNITO_CLIENT_ID", "").strip()
        cognito_user_pool_id = os.getenv("COGNITO_USER_POOL_ID", "").strip()
        cognito_region = os.getenv("AWS_REGION", "us-east-1").strip()

        health: dict[str, Any] = {
            "status": "healthy",
            "check_type": "cognito_configuration",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # If client ID not configured, flag as critical (security issue)
        if not configured_client_id:
            health["status"] = "misconfigured"
            health["error"] = "COGNITO_CLIENT_ID not configured"
            logger.error("CRITICAL: COGNITO_CLIENT_ID environment variable is missing")
            return error_response(503, "misconfigured", "Cognito client ID not configured")

        if not cognito_user_pool_id:
            health["status"] = "misconfigured"
            health["error"] = "COGNITO_USER_POOL_ID not configured"
            logger.error("CRITICAL: COGNITO_USER_POOL_ID environment variable is missing")
            return error_response(503, "misconfigured", "Cognito user pool ID not configured")

        health["configured_client_id"] = configured_client_id
        health["cognito_user_pool_id"] = cognito_user_pool_id
        health["cognito_region"] = cognito_region

        # Attempt to verify against actual Cognito configuration
        try:
            cognito = boto3.client("cognito-idp", region_name=cognito_region)

            # Get user pool description to find app client
            pool_response = cognito.describe_user_pool(UserPoolId=cognito_user_pool_id)

            # Validate pool response is a dict
            if not isinstance(pool_response, dict):
                return error_response(
                    503,
                    "cognito_configuration_error",
                    f"Cognito pool API returned invalid response type {type(pool_response).__name__} — cannot validate authentication configuration",
                )

            pool_data = pool_response.get("UserPool")
            if not pool_data:
                return error_response(
                    503,
                    "cognito_configuration_error",
                    f"Cognito pool API missing 'UserPool' field in response — response keys: {list(pool_response.keys())}",
                )

            # List app clients in this user pool
            apps_response = cognito.list_user_pool_clients(UserPoolId=cognito_user_pool_id, MaxResults=10)

            # Validate apps response is a dict
            if not isinstance(apps_response, dict):
                return error_response(
                    503,
                    "cognito_configuration_error",
                    f"Cognito clients API returned invalid response type {type(apps_response).__name__} — cannot validate application configuration",
                )

            clients = apps_response.get("UserPoolClients")
            if not clients:
                return error_response(
                    503,
                    "cognito_configuration_error",
                    f"Cognito clients API missing 'UserPoolClients' field in response — response keys: {list(apps_response.keys())}",
                )

            # Validate clients is a list
            if not isinstance(clients, list):
                return error_response(
                    503,
                    "cognito_configuration_error",
                    f"Cognito 'UserPoolClients' has invalid type {type(clients).__name__}, expected list — configuration may be corrupted",
                )

            # Find matching client
            matching_client = None
            for client in clients:
                # Validate each client is a dict before accessing
                if not isinstance(client, dict):
                    logger.warning(f"Invalid client type in list: {type(client).__name__}. Skipping.")
                    continue
                if client.get("ClientId") == configured_client_id:
                    matching_client = client
                    break

            if matching_client:
                health["cognito_client_found"] = True
                health["cognito_client_name"] = matching_client.get("ClientName", "unknown")
                health["validation_result"] = "PASS"
                return success_response(health)
            else:
                health["status"] = "misconfigured"
                health["cognito_client_found"] = False
                health["available_clients"] = [c.get("ClientId") for c in clients]
                health["validation_result"] = "FAIL - client ID not found in Cognito"
                logger.error(
                    f"CRITICAL: COGNITO_CLIENT_ID {configured_client_id} not found in user pool {cognito_user_pool_id}"
                )
                return error_response(
                    503,
                    "misconfigured",
                    f"Client ID {configured_client_id} not found in Cognito user pool",
                )

        except Exception as cognito_err:
            from utils.error_handlers import sanitize_error_message

            sanitized = sanitize_error_message(str(cognito_err)[:100])
            logger.warning(f"Could not verify Cognito client ID with API (will proceed with config): {sanitized}")
            # If we can't reach Cognito API, still report what we have configured (pre-deploy may not have IAM)
            health["cognito_verification_skipped"] = True
            health["cognito_error"] = sanitize_error_message(str(cognito_err)[:80])
            return success_response(health)

    except Exception as e:
        from utils.error_handlers import sanitize_error_message

        sanitized = sanitize_error_message(str(e)[:100])
        logger.error(f"Cognito health check error: {sanitized}")
        return error_response(503, "health_check_error", sanitized)


def _handle_detailed(cur: cursor, jwt_claims: dict[str, Any] | None) -> Any:
    """Detailed health check - AUTHENTICATED. Exposes schema information."""
    if not jwt_claims:
        return error_response(401, "unauthorized", "Authentication required")

    try:
        health_tables = (
            "price_daily",
            "swing_trader_scores",
            "stock_scores",
            "market_health_daily",
            "market_exposure_daily",
        )
        rows = execute_with_timeout(
            cur,
            """
            SELECT relname, n_live_tup
            FROM pg_stat_user_tables
            WHERE relname = ANY(%s)
            """,
            params=(health_tables,),
            timeout_sec=5,
        )
        table_counts = {row[0]: row[1] for row in rows}
        for t in health_tables:
            table_counts.setdefault(t, 0)

        return success_response({"status": "healthy", "dbStatus": "connected", "tables": table_counts})
    except Exception as e:
        code, error_type, message = handle_db_error(e, "detailed health check")
        return error_response(code, error_type, message)


def _handle_pipeline(cur: cursor, jwt_claims: dict[str, Any] | None) -> Any:
    """Pipeline health check - AUTHENTICATED. Data freshness of critical loaders."""
    if not jwt_claims:
        return error_response(401, "unauthorized", "Authentication required")

    try:
        # Query freshness of current pipeline critical tables (15s timeout)
        # buy_sell_daily and technical_data_daily were removed from pipelines;
        # signal_quality_scores is computed on-the-fly by orchestrator, not a pipeline table.
        query = """
            SELECT
                'price_daily' as table_name,
                COUNT(*) as row_count,
                EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) / 86400.0 as age_days
            FROM price_daily
            UNION ALL
            SELECT
                'swing_trader_scores',
                COUNT(*),
                EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) / 86400.0
            FROM swing_trader_scores
            UNION ALL
            SELECT
                'market_health_daily',
                COUNT(*),
                EXTRACT(EPOCH FROM (NOW() - MAX(date))) / 86400.0
            FROM market_health_daily
            UNION ALL
            SELECT
                'trend_template_data',
                COUNT(*),
                EXTRACT(EPOCH FROM (NOW() - MAX(date))) / 86400.0
            FROM trend_template_data
            UNION ALL
            SELECT
                'market_exposure_daily',
                COUNT(*),
                EXTRACT(EPOCH FROM (NOW() - MAX(date))) / 86400.0
            FROM market_exposure_daily
            UNION ALL
            SELECT
                'sector_ranking',
                COUNT(*),
                EXTRACT(EPOCH FROM (NOW() - MAX(date))) / 86400.0
            FROM sector_ranking
        """
        rows = execute_with_timeout(cur, query, timeout_sec=15, max_attempts=1)
        rows = [safe_json_serialize(dict(row)) for row in rows]

        config = get_config()
        tables = []
        for row in rows:
            # FAIL-FAST: age_days and row_count are critical for pipeline health assessment
            if row.get("age_days") is None:
                raise RuntimeError(
                    f"[PIPELINE HEALTH CRITICAL] Table {row.get('table_name', 'unknown')} missing age_days. "
                    f"Cannot determine freshness. Check that pipeline query is computing MAX(created_at) or MAX(date)."
                )
            if row.get("row_count") is None:
                raise RuntimeError(
                    f"[PIPELINE HEALTH CRITICAL] Table {row.get('table_name', 'unknown')} missing row_count. "
                    f"Cannot determine if table has data. Check pipeline query COUNT(*) result."
                )

            age = float(row["age_days"])
            row_count = int(row["row_count"])

            if age <= config.pipeline_healthy_days and row_count > 0:
                status = "HEALTHY"
            elif age <= config.pipeline_critical_days:
                status = "STALE"
            else:
                status = "CRITICAL"
            tables.append(
                {
                    "table_name": row["table_name"],
                    "row_count": row_count,
                    "age_days": round(age, 1),
                    "status": status,
                }
            )

        healthy = sum(1 for t in tables if t["status"] == "HEALTHY")
        return success_response(
            {
                "status": ("HEALTHY" if healthy == len(tables) and tables else "DEGRADED"),
                "healthy_count": healthy,
                "total_count": len(tables),
                "tables": tables,
            }
        )
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "pipeline health check")
        return error_response(code, error_type, message)
