"""Route: health - Health check endpoints (basic, detailed, pipeline)"""

from typing import Dict
import logging
from datetime import datetime, timezone
from routes.utils import (
    success_response,
    error_response,
    execute_with_timeout,
    handle_db_error,
    safe_json_serialize,
)

# Import get_config from lambda/api/api_utils/config.py
from api_utils.config import get_config

# C-4 FIX: Import route status for health endpoint
try:
    from api_router import get_import_status as get_api_import_status
except (ImportError, ModuleNotFoundError):
    # Fallback if api_router not available (shouldn't happen in normal execution)
    def get_api_import_status():
        return {"failed_routes": 0, "critical_failures": []}


logger = logging.getLogger(__name__)


def handle(
    cur,
    path: str,
    method: str,
    params: Dict,
    body: Dict = None,
    jwt_claims: Dict = None,
) -> Dict:
    """Handle health check endpoints.

    /api/health — PUBLIC, no auth required. Basic system status.
    /api/health/cognito — PUBLIC, no auth required. C-7 FIX: Verify Cognito client ID matches configuration.
    /api/health/detailed — AUTHENTICATED. Database schema and table status.
    /api/health/pipeline — AUTHENTICATED. Data freshness of critical loaders.
    """

    # Route to appropriate handler
    if path.startswith("/api/health/cognito") or path.startswith("/health/cognito"):
        return _handle_cognito(cur)
    elif path.startswith("/api/health/detailed") or path.startswith("/health/detailed"):
        return _handle_detailed(cur, jwt_claims)
    elif path.startswith("/api/health/pipeline") or path.startswith("/health/pipeline"):
        return _handle_pipeline(cur, jwt_claims)
    else:
        # Basic health check (default for /api/health)
        return _handle_basic(cur)


def _handle_basic(cur) -> Dict:
    """Basic health check - PUBLIC, no auth required.

    Fast health check: DB connectivity + key metrics (optimized).
    Uses simple, indexed queries only. Complex checks move to /health/detailed.
    """
    import_status = get_api_import_status()

    health = {
        "status": "healthy",
        "version": "v2-2026-06-06",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    has_critical = False

    # C-4 FIX: Report API route import failures in health check
    if import_status.get("failed_routes", 0) > 0:
        health["api_route_imports"] = {
            "status": "degraded",
            "failed_count": import_status["failed_routes"],
            "critical_failures": import_status["critical_failures"],
            "failed_modules": import_status["failed_modules"],
        }
        if import_status.get("critical_failures"):
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
        try:
            signal_check = execute_with_timeout(
                cur,
                """
                SELECT created_at AS latest_signal
                FROM swing_trader_scores
                ORDER BY created_at DESC
                LIMIT 1
            """,
                timeout_sec=2,
            )

            if signal_check and len(signal_check) > 0:
                latest = signal_check[0]["latest_signal"]
                if latest:
                    age_hours = (
                        datetime.now(timezone.utc) - latest.replace(tzinfo=timezone.utc)
                    ).total_seconds() / 3600
                    config = get_config()
                    if age_hours > config.signal_stale_threshold_hours:
                        has_critical = True
                        health["freshness"] = {
                            "status": "STALE",
                            "signal_age_hours": round(age_hours, 1),
                        }
                    else:
                        health["freshness"] = {
                            "status": "OK",
                            "signal_age_hours": round(age_hours, 1),
                        }
                else:
                    health["freshness"] = {"status": "UNKNOWN"}
        except Exception as e:
            logger.debug(f"Signal freshness check unavailable: {str(e)[:60]}")
            health["freshness"] = {"status": "UNKNOWN"}

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
                        latest_load.isoformat()
                        if hasattr(latest_load, "isoformat")
                        else str(latest_load)
                    )
        except Exception as e:
            logger.debug(f"Loader check unavailable: {str(e)[:60]}")

        if has_critical:
            health["status"] = "degraded"

        return success_response(health)

    except Exception as e:
        logger.error(f"Health check error: {str(e)[:100]}")
        code, error_type, message = handle_db_error(e, "health check")
        return error_response(code, error_type, message)


def _handle_cognito(cur) -> Dict:
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

        health = {
            "status": "healthy",
            "check_type": "cognito_configuration",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # If client ID not configured, flag as critical (security issue)
        if not configured_client_id:
            health["status"] = "misconfigured"
            health["error"] = "COGNITO_CLIENT_ID not configured"
            logger.error("CRITICAL: COGNITO_CLIENT_ID environment variable is missing")
            return error_response(
                503, "misconfigured", "Cognito client ID not configured"
            )

        if not cognito_user_pool_id:
            health["status"] = "misconfigured"
            health["error"] = "COGNITO_USER_POOL_ID not configured"
            logger.error(
                "CRITICAL: COGNITO_USER_POOL_ID environment variable is missing"
            )
            return error_response(
                503, "misconfigured", "Cognito user pool ID not configured"
            )

        health["configured_client_id"] = configured_client_id
        health["cognito_user_pool_id"] = cognito_user_pool_id
        health["cognito_region"] = cognito_region

        # Attempt to verify against actual Cognito configuration
        try:
            cognito = boto3.client("cognito-idp", region_name=cognito_region)

            # Get user pool description to find app client
            pool_response = cognito.describe_user_pool(UserPoolId=cognito_user_pool_id)
            pool_response.get("UserPool", {})

            # List app clients in this user pool
            apps_response = cognito.list_user_pool_clients(
                UserPoolId=cognito_user_pool_id, MaxResults=10
            )
            clients = apps_response.get("UserPoolClients", [])

            # Find matching client
            matching_client = None
            for client in clients:
                if client.get("ClientId") == configured_client_id:
                    matching_client = client
                    break

            if matching_client:
                health["cognito_client_found"] = True
                health["cognito_client_name"] = matching_client.get(
                    "ClientName", "unknown"
                )
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
            logger.warning(
                f"Could not verify Cognito client ID with API (will proceed with config): {str(cognito_err)[:100]}"
            )
            # If we can't reach Cognito API, still report what we have configured (pre-deploy may not have IAM)
            health["cognito_verification_skipped"] = True
            health["cognito_error"] = str(cognito_err)[:80]
            return success_response(health)

    except Exception as e:
        logger.error(f"Cognito health check error: {str(e)[:100]}")
        return error_response(503, "health_check_error", str(e)[:100])


def _handle_detailed(cur, jwt_claims: Dict) -> Dict:
    """Detailed health check - AUTHENTICATED. Exposes schema information."""
    if not jwt_claims:
        return error_response(401, "unauthorized", "Authentication required")

    try:
        _HEALTH_TABLES = (
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
            params=(_HEALTH_TABLES,),
            timeout_sec=5,
        )
        table_counts = {row[0]: row[1] for row in rows}
        for t in _HEALTH_TABLES:
            table_counts.setdefault(t, 0)

        return success_response(
            {"status": "healthy", "dbStatus": "connected", "tables": table_counts}
        )
    except Exception as e:
        logger.error(f"[HEALTH_DETAILED_ERROR] {e}", exc_info=True)
        code, error_type, message = handle_db_error(e, "detailed health check")
        return error_response(code, error_type, message)


def _handle_pipeline(cur, jwt_claims: Dict) -> Dict:
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
            age = float(row.get("age_days")) if row.get("age_days") is not None else 999
            row_count = row.get("row_count")
            if (
                age <= config.pipeline_healthy_days
                and row_count is not None
                and row_count > 0
            ):
                status = "HEALTHY"
            elif age <= config.pipeline_critical_days:
                status = "STALE"
            else:
                status = "CRITICAL"
            tables.append(
                {
                    "table_name": row["table_name"],
                    "row_count": row.get("row_count", 0),
                    "age_days": round(age, 1),
                    "status": status,
                }
            )

        healthy = sum(1 for t in tables if t["status"] == "HEALTHY")
        return success_response(
            {
                "status": (
                    "HEALTHY" if healthy == len(tables) and tables else "DEGRADED"
                ),
                "healthy_count": healthy,
                "total_count": len(tables),
                "tables": tables,
            }
        )
    except Exception as e:
        logger.error(f"[HEALTH_PIPELINE_ERROR] {e}", exc_info=True)
        code, error_type, message = handle_db_error(e, "pipeline health check")
        return error_response(code, error_type, message)
