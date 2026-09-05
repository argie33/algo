"""Stock Analytics Platform - API Lambda Handler.

Routes requests to extracted handler modules via api_router.
Deployment: Fixed Secrets Manager secret name for password sync.

Split 2026-09-05 (bloater decomposition, mechanical move, no behavior change): the request
routing/auth/CORS helper functions that used to live directly in this file now live in
sibling modules under this package (startup_checks, cors_headers, response_helpers,
auth_validation, request_parsing, error_classification) and are re-exported here so every
existing `from lambda_function import X` / `import lambda_function; lambda_function.X`
caller keeps working unchanged. lambda_handler itself (the actual Lambda entry point) was
left in place verbatim.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from typing import Any

import psycopg2

# Set up imports for Lambda API - ensures routes, api_utils, utils, and other packages are importable
# setup_imports only available in Lambda runtime; during local testing, continue anyway
try:
    import setup_imports
except ModuleNotFoundError as setup_err:
    if "AWS_LAMBDA_FUNCTION_NAME" in os.environ:
        # In Lambda, setup_imports is required
        raise RuntimeError(f"Lambda runtime setup failed: {setup_err}") from setup_err
    # In local testing, skip the import


IMPORT_ERROR = None
ENV_VALIDATION_ERROR = None
DB_CONNECTION_ERROR = None
_NAIVE_DB_TZ_CACHE: ZoneInfo | timezone | None = None  # DB session tz for naive `timestamp without time zone` cols
_NAIVE_DB_TZ_CACHE_TIME = None
_NAIVE_DB_TZ_CACHE_TTL_SECONDS = 86400  # Refresh DB timezone daily
_NAIVE_DB_TZ_LOCK = threading.Lock()

try:
    from datetime import date, datetime, timedelta, timezone
    from zoneinfo import ZoneInfo

    import api_router
    import requests
    from api_utils.database_context import DatabaseContext
except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
    IMPORT_ERROR = f"{type(e).__name__}: {str(e)[:200]}"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Re-exported helpers (moved to sibling modules - see module docstring above). Explicit
# `as`-aliasing (rather than a plain import) marks each name as a deliberate public
# re-export under mypy's strict-mode `implicit_reexport = False` behavior.
from . import auth_validation  # noqa: E402
from .auth_validation import _get_cognito_jwks as _get_cognito_jwks  # noqa: E402
from .auth_validation import get_bearer_token as get_bearer_token  # noqa: E402
from .auth_validation import require_auth as require_auth  # noqa: E402
from .auth_validation import validate_bearer_token as validate_bearer_token  # noqa: E402
from .cors_headers import _build_allowed_origins as _build_allowed_origins  # noqa: E402
from .cors_headers import get_cors_headers as get_cors_headers  # noqa: E402
from .error_classification import categorize_error as categorize_error  # noqa: E402
from .request_parsing import get_client_ip as get_client_ip  # noqa: E402
from .request_parsing import log_api_request as log_api_request  # noqa: E402
from .request_parsing import parse_query_params as parse_query_params  # noqa: E402
from .request_parsing import redact_sensitive_headers as redact_sensitive_headers  # noqa: E402
from .request_parsing import validate_query_param_type as validate_query_param_type  # noqa: E402
from .response_helpers import get_cache_headers as get_cache_headers  # noqa: E402
from .response_helpers import get_json_content_type as get_json_content_type  # noqa: E402
from .response_helpers import get_security_headers as get_security_headers  # noqa: E402
from .response_helpers import make_error_response as make_error_response  # noqa: E402
from .startup_checks import _apply_critical_migrations as _apply_critical_migrations  # noqa: E402
from .startup_checks import fetch_cloudfront_domain_from_secrets as fetch_cloudfront_domain_from_secrets  # noqa: E402
from .startup_checks import test_db_connection as test_db_connection  # noqa: E402
from .startup_checks import validate_environment as validate_environment  # noqa: E402

# Execute migrations on cold start
# CRITICAL: Must verify critical schema tables exist. Fail-fast if any critical table missing.
try:
    success, msg = _apply_critical_migrations()
    if not success:
        raise RuntimeError(
            f"[STARTUP CRITICAL] Database migrations failed - cannot proceed with API serving: {msg}. "
            f"API Gateway requires these migrations to serve requests correctly. "
            f"Check database connectivity and permissions."
        )
    logger.info(f"[STARTUP] Database migrations completed: {msg}")
except (RuntimeError, psycopg2.Error) as e:
    logger.critical(f"[STARTUP CRITICAL] Migration initialization failed - aborting API startup: {e}")
    raise RuntimeError(f"[STARTUP] API Lambda cannot start without schema: {e}") from e


# SECURITY FIX: API Rate Limiting is enforced ONLY at API Gateway level
# In-memory per-Lambda tracking is ineffective because:
# - Each Lambda cold start resets tracking dict
# - Each Lambda instance has independent tracking
# - Concurrent instances multiply effective rate limit
# Instead, rely on API Gateway throttling (100 req/sec burst, 50 req/sec sustained)
# which is GLOBAL across all instances
MAX_REQUEST_BODY_SIZE = 1024 * 100

# Public health endpoints exempt from in-Lambda rate limiting (uptime monitors hit these).
# /health/detailed and /api/health/detailed require authentication - they are NOT exempt,
# so authenticated clients share the same per-instance throttle as other endpoints.
RATE_LIMIT_EXEMPT_PATHS = {
    "/health",
    "/api/health",
    "/health/pipeline",
    "/api/health/pipeline",
}


# Module-level initialization: Run validation, DB test, and pre-cache values once at cold start
if not IMPORT_ERROR:
    env_valid, env_errors, env_warnings = validate_environment()
    if not env_valid:
        ENV_VALIDATION_ERROR = "; ".join(env_errors)
        logger.error(f"[MODULE_INIT_ENV_VALIDATION_FAILED] {ENV_VALIDATION_ERROR}")

    # DB connection test removed from module-level init.
    # Fetching the DB password from Secrets Manager (connect_timeout=10, read_timeout=15,
    # retries=2) can exceed the 25s Lambda function timeout on VPC cold-starts, causing
    # INIT timeouts that prevent Lambda from scaling. The first real request via
    # DatabaseContext will test connectivity with proper retries and error responses.

    # Determine if Cognito authentication is enabled
    with auth_validation._COGNITO_ENABLED_LOCK:
        auth_validation._COGNITO_ENABLED = bool(os.getenv("COGNITO_USER_POOL_ID"))
        if not auth_validation._COGNITO_ENABLED:
            # In production Lambda, Cognito MUST be configured for security
            is_production = "AWS_LAMBDA_FUNCTION_NAME" in os.environ
            if is_production:
                raise RuntimeError(
                    "[CRITICAL] COGNITO_USER_POOL_ID environment variable not set in production Lambda. "
                    "Authentication is required for production deployments. "
                    "Set COGNITO_USER_POOL_ID environment variable via Terraform or Lambda console."
                )
            logger.warning("[COGNITO] COGNITO_USER_POOL_ID not set - Cognito authentication is disabled (dev mode)")

    # Pre-cache allowed origins at module load to avoid building on every request
    _build_allowed_origins()


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle API Gateway v2 (HTTP API) requests by routing to extracted handler modules."""
    # STRUCTURED LOGGING: Log incoming event schema for validation and audit trail
    # This helps debugging event format issues and tracks which event types are being processed
    event_source = event.get("source")  # EventBridge: "eventbridge-scheduler", "warmup", etc.
    event_type = "eventbridge" if event_source else "api-gateway"  # Determine if EventBridge or API Gateway request
    request_context = event.get("requestContext", {})
    http_context = request_context.get("http", {})
    event_schema = {
        "type": event_type,
        "has_rawPath": "rawPath" in event,
        "has_path": "path" in event,
        "has_requestContext": "requestContext" in event,
        "has_httpMethod": "httpMethod" in event,
        "has_body": "body" in event,
        "has_headers": "headers" in event,
        "event_source": event_source,
        "top_level_keys": list(event.keys())[:10],  # First 10 keys for schema introspection
    }
    logger.debug(f"[LAMBDA_INPUT_SCHEMA] Event structure: {event_schema}")

    # GOVERNANCE FIX: Explicit path extraction (supports both HTTP API and REST API event formats)
    # HTTP API v2: uses "rawPath"; REST API v1: uses "path"
    path = event.get("rawPath")
    if not path:
        path = event.get("path")
    if not path:
        logger.warning(
            f"[LAMBDA_START] Request missing path field. Expected 'rawPath' (HTTP API v2) or 'path' (REST API v1). "
            f"Event keys: {list(event.keys())}. Using 'UNKNOWN' for logging."
        )
        path = "UNKNOWN"
    logger.info(
        f"[LAMBDA_START] Handling {event.get('httpMethod', http_context.get('method', 'GET'))} {path} "
        f"(event_type={event_type})"
    )

    # Credential cache uses 5-minute TTL to balance freshness with API costs
    # Expired entries are automatically skipped; clearing cache is optional for rotation speed.
    try:
        from algo.config.credential_manager import clear_expired_credentials

        clear_expired_credentials()
    except (ImportError, AttributeError):
        # Credential manager not available - skip cache clearing (non-critical for this invocation)
        logger.debug("Credential cache clearing unavailable (module not found)")
    except (RuntimeError, ValueError) as e:
        # Credential cache clearing failed - non-critical, don't abort request
        logger.warning(f"[CREDENTIAL_CACHE] Failed to clear expired credentials: {e}")
        # Don't fail the request for this non-critical operation, but log prominently

    # Extract path and method before ANY checks so health/CORS always work
    path = event.get("rawPath")
    if path is None:
        path = event.get("path", "/")

    _req_ctx = event.get("requestContext")
    _req_ctx = _req_ctx if _req_ctx is not None else {}
    http_ctx = _req_ctx.get("http")
    http_ctx = http_ctx if http_ctx is not None else {}
    method = http_ctx.get("method", event.get("httpMethod", "GET"))

    # CORS preflight: must succeed even during import failures (browsers need this)
    if method == "OPTIONS":
        cors_headers = get_cors_headers(event)
        return {
            "statusCode": 200,
            "headers": {
                **cors_headers,
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
                **get_security_headers(),
            },
        }

    # EventBridge warmup ping - return immediately without touching DB or Cognito.
    # Keeps one Lambda container alive to eliminate VPC cold-start 502s for real users.
    if event.get("source") == "warmup":
        return {"statusCode": 200, "body": "warm"}

    # EventBridge Orchestrator invocation (scheduled trading runs: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET)
    # Runs the algo orchestrator (Phase 1-9) to monitor positions and execute trades
    if event.get("source") == "eventbridge-scheduler":
        try:
            import subprocess

            run_id = event.get("run_identifier", "unknown")
            logger.info(f"[ORCHESTRATOR_TRIGGER] EventBridge invoked orchestrator: run_id={run_id}")

            # Invoke orchestrator as subprocess with run_identifier
            result = subprocess.run(
                [sys.executable, "-m", "algo.orchestration.orchestrator", f"--run-id={run_id}"],
                capture_output=True,
                text=True,
                timeout=600,  # 10 min timeout (orchestrator has 600s phase timeout)
            )

            logger.info(f"[ORCHESTRATOR_COMPLETE] run_id={run_id}, exit_code={result.returncode}")
            if result.stdout:
                logger.info(f"[ORCHESTRATOR_OUTPUT] {result.stdout[:500]}")
            if result.stderr:
                logger.warning(f"[ORCHESTRATOR_ERROR] {result.stderr[:500]}")

            return {
                "statusCode": 200 if result.returncode == 0 else 500,
                "body": json.dumps(
                    {
                        "orchestrator_run_id": run_id,
                        "exit_code": result.returncode,
                        "success": result.returncode == 0,
                    }
                ),
            }
        except FileNotFoundError as e:
            logger.error(f"[ORCHESTRATOR_FAILED] Python executable not found: {e}", exc_info=True)
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "orchestrator_failed", "message": "Python executable not found"}),
            }
        except subprocess.TimeoutExpired as e:
            logger.error(f"[ORCHESTRATOR_FAILED] Orchestrator exceeded 10-minute timeout: {e}", exc_info=True)
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "orchestrator_timeout", "message": "Orchestrator execution timeout"}),
            }
        except OSError as e:
            logger.error(
                f"[ORCHESTRATOR_FAILED] OS error during orchestrator execution: {type(e).__name__}: {e}", exc_info=True
            )
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "orchestrator_failed", "message": f"OS error: {e}"}),
            }
        except ImportError as e:
            logger.error(f"[ORCHESTRATOR_FAILED] Import error in orchestrator module: {e}", exc_info=True)
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "orchestrator_failed", "message": "Orchestrator module not available"}),
            }

    # Health checks are handled via api_router (routes/health.py) for consistent response format
    # All health endpoints (basic, detailed, pipeline) now route through normal flow
    # This ensures all API responses use the same {statusCode, data/items/error} structure

    # Import error check (after health so health always works despite missing modules)
    if IMPORT_ERROR:
        logger.error(f"[IMPORT_ERROR] {IMPORT_ERROR}")
        return make_error_response(500, "service_unavailable", "Service temporarily unavailable", event)

    # Environment validation and DB test are now run once at module load (not on every request)
    # This check ensures that if there were initialization errors, we return them
    if ENV_VALIDATION_ERROR:
        cors_headers = get_cors_headers(event)
        logger.error(f"[ENV_VALIDATION_FAILED] {ENV_VALIDATION_ERROR}")

        # Parse error message to extract individual errors for clearer diagnostics
        error_list = [e.strip() for e in ENV_VALIDATION_ERROR.split(";") if e.strip()]

        # Determine specific config error type for better client diagnostics
        error_type = "configuration_error"
        if any("COGNITO" in e for e in error_list):
            error_type = "cognito_config_error"
        elif any("DB_" in e or "database" in e.lower() for e in error_list):
            error_type = "database_config_error"
        elif any("FRONTEND_URL" in e for e in error_list):
            error_type = "cors_config_error"

        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": get_json_content_type(),
                **cors_headers,
                **get_security_headers(),
            },
            "body": json.dumps(
                {
                    "error": error_type,
                    "message": "Service configuration incomplete",
                    "missing_config": error_list,
                    "details": "Ensure all required environment variables are set in Lambda configuration",
                }
            ),
        }

    logger.info(f"[HANDLER_INVOKED] Event received: {path} {method}")

    # CRITICAL FIX: Clear thread-local cursor from previous request
    # In dev_server, threads are reused between requests. Without clearing,
    # the old (closed) cursor stays in thread-local storage, causing subsequent
    # requests using the same thread to fail when safe_dict_convert tries to use it.
    # This manifests as hangs on the 3rd+ request to endpoints.
    try:
        from routes.utils import clear_current_cursor

        clear_current_cursor()
    except ImportError:
        pass  # If not available, continue anyway

    try:
        logger.info(f"Request: {method} {path}")

        # Check authorization for protected endpoints
        requires_auth, is_authorized, auth_error, jwt_claims = require_auth(event, path)
        logger.info(
            f"[REQUIRE_AUTH] path={path}, requires_auth={requires_auth}, "
            f"is_authorized={is_authorized}, error={auth_error}"
        )

        if requires_auth and not is_authorized:
            logger.warning(f"Unauthorized access attempt to {path}: {auth_error}")
            log_api_request(event, 401, error_msg=auth_error)
            return make_error_response(401, "unauthorized", auth_error or "Unauthorized", event)

        # Detailed and pipeline health checks are handled via api_router (routes/health.py)
        # They verify authentication through the normal flow and provide consistent response format

        # Rate limiting enforced at API Gateway level (not per-Lambda)
        # All rate limiting is handled by API Gateway throttling, which is global across instances

        try:
            # Use read-only mode for GET/HEAD, write mode for POST/PUT/PATCH/DELETE
            http_method = method.upper() if method else "GET"
            db_mode = "write" if http_method in ("POST", "PUT", "PATCH", "DELETE") else "read"
            with DatabaseContext(db_mode) as cur:
                # statement_timeout is now set at RDS parameter group level (30s) - no per-request SET needed.

                params = parse_query_params(event)
                body = None
                if event.get("body"):
                    body_str = event["body"]
                    if len(body_str) > MAX_REQUEST_BODY_SIZE:
                        logger.warning(f"Request body exceeds max size: {len(body_str)} > {MAX_REQUEST_BODY_SIZE}")
                        log_api_request(event, 413, error_msg="request_entity_too_large")
                        return make_error_response(413, "request_entity_too_large", "Request body too large", event)
                    try:
                        body = json.loads(body_str)
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning(f"Failed to parse JSON body: {e}")
                        log_api_request(event, 400, error_msg="invalid_json")
                        return make_error_response(400, "invalid_json", "Request body must be valid JSON", event)

                # O-1: POST /api/logout - revoke current token server-side
                if method == "POST" and path == "/api/logout":
                    cors_headers = get_cors_headers(event)
                    if not is_authorized or not jwt_claims:
                        log_api_request(event, 401, error_msg="unauthorized")
                        return make_error_response(401, "unauthorized", "Authentication required", event)
                    jti = jwt_claims.get("jti")
                    exp = jwt_claims.get("exp")
                    if jti and exp:
                        try:
                            from api_utils.token_blocklist import revoke_token

                            revoke_token(jti, int(exp))
                        except (ValueError, ZeroDivisionError, TypeError) as e:
                            logger.error(f"[LOGOUT] Blocklist write failed: {e}")
                    logger.info(f"[LOGOUT] User {jwt_claims.get('sub')} logged out")
                    log_api_request(event, 200)
                    return {
                        "statusCode": 200,
                        "headers": {
                            "Content-Type": get_json_content_type(),
                            **cors_headers,
                            **get_security_headers(),
                        },
                        "body": json.dumps({"status": "logged_out"}),
                    }

                # Route request to appropriate handler
                response = api_router.route_request(cur, path, method, params, body, jwt_claims=jwt_claims)
        except (ValueError, ZeroDivisionError, TypeError) as e:
            cors_headers = get_cors_headers(event)

            # SECURITY FIX: Don't leak error details to client; log full details server-side only
            error_detail = f"{type(e).__name__}: {str(e)[:300]}"
            error_type = categorize_error(e)
            logger.error(
                f"[HANDLER_ERROR] path={path} error_type={error_type} {error_detail}",
                exc_info=True,
            )
            # Never expose error details to client (prevents info disclosure)
            msg = "Service temporarily unavailable. Please try again later."
            return {
                "statusCode": 503,
                "headers": {
                    "Content-Type": get_json_content_type(),
                    **cors_headers,
                    **get_security_headers(),
                },
                "body": json.dumps(
                    {
                        "statusCode": 503,
                        "errorType": "service_unavailable",
                        "message": msg,
                        "_error": msg,
                        "error_type": error_type,
                    }
                ),
            }

        # Ensure response has proper format
        def _naive_db_timezone() -> ZoneInfo | timezone:
            """Timezone naive `timestamp without time zone` DB columns are actually written in.

            Confirmed live (see lambda/api/routes/utils.py::normalize_to_utc_datetime and
            utils/bulk_insert_manager.py): this codebase's naive timestamp columns are written
            in the DB session's local wall-clock (`SHOW timezone`), not UTC. Without this,
            calling .isoformat() on a naive datetime below emits an offset-less string that
            every downstream consumer (e.g. dashboard/formatter_strategies.py's DataAgeFormatter)
            has to guess a zone for - and previously guessed Eastern, silently off by the
            session's actual UTC offset. Cached process-wide: this is a fixed connection
            setting, not a per-request value.
            """
            global _NAIVE_DB_TZ_CACHE, _NAIVE_DB_TZ_CACHE_TIME

            now = datetime.now(timezone.utc)
            cache_ttl = timedelta(seconds=_NAIVE_DB_TZ_CACHE_TTL_SECONDS)

            # Check if cache is still valid (within TTL)
            if (
                _NAIVE_DB_TZ_CACHE is not None
                and _NAIVE_DB_TZ_CACHE_TIME is not None
                and (now - _NAIVE_DB_TZ_CACHE_TIME) < cache_ttl
            ):
                return _NAIVE_DB_TZ_CACHE

            with _NAIVE_DB_TZ_LOCK:
                # Double-check pattern after acquiring lock
                if (
                    _NAIVE_DB_TZ_CACHE is not None
                    and _NAIVE_DB_TZ_CACHE_TIME is not None
                    and (now - _NAIVE_DB_TZ_CACHE_TIME) < cache_ttl
                ):
                    return _NAIVE_DB_TZ_CACHE

                if _NAIVE_DB_TZ_CACHE is None or _NAIVE_DB_TZ_CACHE_TIME is None:
                    try:
                        from utils.db.timezone_utils import get_db_timezone

                        _NAIVE_DB_TZ_CACHE = get_db_timezone()
                        _NAIVE_DB_TZ_CACHE_TIME = now
                    except (
                        ImportError,
                        RuntimeError,
                        ValueError,
                        psycopg2.DatabaseError,
                        psycopg2.OperationalError,
                    ) as tz_err:
                        logger.warning(
                            f"[JSON_DEFAULT] Could not resolve DB session timezone, assuming UTC: {type(tz_err).__name__}: {tz_err}"
                        )
                        _NAIVE_DB_TZ_CACHE = timezone.utc
                        _NAIVE_DB_TZ_CACHE_TIME = now
            return _NAIVE_DB_TZ_CACHE

        def _json_default(obj: Any) -> str | float | None:
            import math
            from decimal import Decimal

            if isinstance(obj, datetime):
                dt = obj if obj.tzinfo is not None else obj.replace(tzinfo=_naive_db_timezone())
                return dt.isoformat()
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                try:
                    val = float(obj)
                    if math.isnan(val) or math.isinf(val):
                        return None
                    return val
                except (ValueError, TypeError):
                    return None
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            if hasattr(obj, "__float__"):
                try:
                    val = float(obj)
                    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                        return None
                    return val
                except (ValueError, TypeError):
                    return str(obj)
            return str(obj)

        if isinstance(response, dict):
            status = response.get("statusCode", 200)
            cors_headers = get_cors_headers(event)
            headers = {
                "Content-Type": get_json_content_type(),
                **cors_headers,
                **get_security_headers(),
            }
            if "body" in response:
                body = (
                    response["body"]
                    if isinstance(response["body"], str)
                    else json.dumps(response["body"], default=_json_default)
                )
            else:
                # Route handlers return data dicts directly - exclude internal routing metadata from body
                body_data = {k: v for k, v in response.items() if k != "headers"}
                body = json.dumps(body_data, default=_json_default)

            # Log successful requests (2xx, 3xx)
            if status < 400:
                log_api_request(event, status)
            # Log errors (4xx, 5xx)
            elif status >= 400:
                error_msg = response.get("message")
                if error_msg is None:
                    error_msg = response.get("error")
                if error_msg is None:
                    error_msg = (
                        f"Error response missing 'message' and 'error' fields. Response keys: {list(response.keys())}"
                    )
                log_api_request(event, status, error_msg=str(error_msg))

            return {"statusCode": status, "headers": headers, "body": body}

        cors_headers = get_cors_headers(event)
        msg = "Handler returned invalid response format"
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": get_json_content_type(),
                **cors_headers,
                **get_security_headers(),
            },
            "body": json.dumps(
                {
                    "statusCode": 500,
                    "errorType": "invalid_response",
                    "message": msg,
                    "_error": msg,
                }
            ),
        }

    except (json.JSONDecodeError, ValueError) as e:
        error_msg = f"{type(e).__name__}: {e!s}"
        logger.error(f"[UNHANDLED_ERROR] {error_msg}", exc_info=True)
        cors_headers = get_cors_headers(event)
        msg = "An unexpected error occurred"
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": get_json_content_type(),
                **cors_headers,
                **get_security_headers(),
            },
            "body": json.dumps(
                {
                    "statusCode": 500,
                    "errorType": "internal_server_error",
                    "message": msg,
                    "_error": msg,
                }
            ),
        }
