"""API Router - dispatcher."""

import json
import logging
import os
import threading
from typing import Any

# Set up imports for Lambda API - ensures routes and api_utils are importable
import setup_imports  # noqa: F401
from psycopg2.extensions import cursor

logger = logging.getLogger(__name__)


# health is the only truly critical route — if it fails the API can't self-report its own status
try:
    from routes import health
except ImportError as e:
    raise RuntimeError(f"CRITICAL: Failed to import routes.health (required for API to function): {e}") from e

# Import routes gracefully - if a single module fails, others still work
_ROUTE_IMPORT_ERRORS = {}  # Track which routes failed to import: {module_name: error_msg}
_AVAILABLE_ROUTES = {}  # Track which routes loaded successfully
_CRITICAL_ROUTES = {"health"}

# All optional routes: loaded with graceful fallback — one module failing doesn't break others
_OPTIONAL_ROUTE_MODULES = [
    "algo",
    "openapi_spec",
    "logs",
    "financials",
    "earnings",
    "signals",
    "prices",
    "stocks",
    "sectors",
    "industries",
    "market",
    "economic",
    "sentiment",
    "scores",
    "research",
    "audit",
    "trades",
    "admin",
    "contact",
    "settings",
    "risk_dashboard",
    "data_coverage",
]

# Track startup state for diagnostics (thread-safe)
_STARTUP_TIME = None
_IMPORT_DURATION = None
_STARTUP_LOCK = threading.Lock()  # Protects startup time and import duration updates

# Populate health (statically imported above)
_AVAILABLE_ROUTES["health"] = health

# Dynamically import optional routes with error handling
for module_name in _OPTIONAL_ROUTE_MODULES:
    try:
        module = __import__(f"routes.{module_name}", fromlist=[module_name])
        _AVAILABLE_ROUTES[module_name] = module
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"
        _ROUTE_IMPORT_ERRORS[module_name] = error_msg
        logger.warning(
            f"Failed to import optional routes.{module_name}: {error_msg}",
            exc_info=True,
        )

# Report startup status: log all failures with clear visibility
if _ROUTE_IMPORT_ERRORS:
    failed_modules = list(_ROUTE_IMPORT_ERRORS.keys())
    critical_failures = [m for m in failed_modules if m in _CRITICAL_ROUTES]

    # Log structured status for monitoring
    logger.error(
        f"ROUTE_IMPORT_STATUS: failed_count={len(failed_modules)}, critical_count={len(critical_failures)}, modules={failed_modules}"
    )

    # If critical routes failed, the API cannot function
    if critical_failures:
        error_detail = {
            "error": "CRITICAL_ROUTE_IMPORT_FAILURE",
            "critical_failures": critical_failures,
            "all_failures": failed_modules,
            "details": {m: _ROUTE_IMPORT_ERRORS[m] for m in critical_failures},
        }
        logger.error(f"CRITICAL_ROUTE_IMPORT_FAILURE: {json.dumps(error_detail)}")
        # Set environment variable that monitoring can detect
        os.environ["API_CRITICAL_ROUTES_FAILED"] = json.dumps(critical_failures)

# Build handler mappings from available routes (some may be missing if they failed to import)
PUBLIC_HANDLERS = {}
HANDLERS = {}

# Health endpoints must be public and checked first
if "health" in _AVAILABLE_ROUTES:
    PUBLIC_HANDLERS["/api/health"] = _AVAILABLE_ROUTES["health"]
    PUBLIC_HANDLERS["/health"] = _AVAILABLE_ROUTES["health"]
else:
    logger.error("CRITICAL: health route module failed to import - health endpoints will not work")

# API documentation endpoints (public, no auth required)
if "openapi_spec" in _AVAILABLE_ROUTES:
    PUBLIC_HANDLERS["/api/openapi.json"] = _AVAILABLE_ROUTES["openapi_spec"]
    PUBLIC_HANDLERS["/api/swagger"] = _AVAILABLE_ROUTES["openapi_spec"]
    PUBLIC_HANDLERS["/api/redoc"] = _AVAILABLE_ROUTES["openapi_spec"]
else:
    logger.error("WARNING: openapi_spec route module failed to import - API documentation unavailable")

# Frontend error logging endpoint (public, may be called before auth)
if "logs" in _AVAILABLE_ROUTES:
    PUBLIC_HANDLERS["/api/logs"] = _AVAILABLE_ROUTES["logs"]

# Build authenticated handlers (order matters: /api/algo/risk-dashboard must come before /api/algo)
_HANDLER_CONFIG = [
    ("/api/algo/risk-dashboard", "risk_dashboard"),
    ("/api/algo", "algo"),
    ("/api/financials", "financials"),
    ("/api/earnings", "earnings"),
    ("/api/signals", "signals"),
    ("/api/prices", "prices"),
    ("/api/stocks", "stocks"),
    ("/api/sectors", "sectors"),
    ("/api/industries", "industries"),
    ("/api/market", "market"),
    ("/api/economic", "economic"),
    ("/api/sentiment", "sentiment"),
    ("/api/scores", "scores"),
    ("/api/research", "research"),
    ("/api/audit", "audit"),
    ("/api/trades", "trades"),
    ("/api/admin", "admin"),
    ("/api/contact", "contact"),
    ("/api/settings", "settings"),
    ("/api/data-coverage", "data_coverage"),
]

_SKIPPED_ROUTES = []  # Track which routes were skipped due to import failures

for path, module_name in _HANDLER_CONFIG:
    if module_name in _AVAILABLE_ROUTES:
        HANDLERS[path] = _AVAILABLE_ROUTES[module_name]
    else:
        _SKIPPED_ROUTES.append(
            {
                "path": path,
                "module": module_name,
                "error": _ROUTE_IMPORT_ERRORS.get(module_name, "unknown"),
            }
        )
        logger.warning(
            f"Route {path} SKIPPED - module routes.{module_name} failed to import: {_ROUTE_IMPORT_ERRORS.get(module_name, 'unknown')}"
        )

# Log final status
if _SKIPPED_ROUTES:
    logger.error(
        f"ROUTE_SKIP_STATUS: total_skipped={len(_SKIPPED_ROUTES)}, routes={[r['path'] for r in _SKIPPED_ROUTES]}"
    )


def _wrap_response(response: Any) -> Any:
    """Standardize response format for consistent client handling.

    All API responses follow a consistent format:
    - Success (200): {statusCode: 200, data: {...}, data_freshness?: {...}}
    - Error (4xx/5xx): {statusCode: code, errorType: "...", message: "...", _error: "..."}

    This function is a safety net for any legacy endpoints that don't use the
    response utility functions (success_response, list_response, json_response).
    Also cleans up responses that have extra fields added by intermediate processing
    and fixes double-nested data issues.

    IMPORTANT: ALL route handlers MUST return dicts (never strings or other types).
    The route_request dispatcher applies _wrap_response to every response from:
    - PUBLIC_HANDLERS (lines 376)
    - HANDLERS (line 387)
    - Error handlers (lines 378, 389)
    - Import errors (line 419)
    - 404 fallback (line 425)
    So routes are guaranteed to be wrapped regardless of handler implementation.
    """
    if not isinstance(response, dict):
        return response

    # Errors are returned as-is (already include errorType and _error)
    if response.get("errorType"):
        return response
    status_code = response.get("statusCode", 200)
    try:
        if int(status_code) >= 400:
            return response
    except (ValueError, TypeError):
        pass

    # Fix double-nested data issue: if data contains only a 'data' field (or data + extra fields), unwrap it
    if response.get("statusCode") == 200 and "data" in response:
        data_field = response["data"]
        # Check if data field is a dict with only 'data' and optional metadata keys
        if isinstance(data_field, dict) and "data" in data_field:
            # Check if 'data' is the only meaningful field (allow for pagination, total, etc.)
            meaningful_keys = [k for k in data_field.keys() if k not in ("data", "pagination", "total")]
            if len(meaningful_keys) == 0:
                # Double-nested: unwrap it
                response = dict(response)  # Make a copy
                response["data"] = data_field["data"]
                # Preserve pagination metadata if it exists
                if "pagination" in data_field:
                    response["data"]["pagination"] = data_field["pagination"]
                if "total" in data_field and "total" not in response["data"]:
                    response["data"]["total"] = data_field["total"]

    # Success responses should already have 'data' field from response utilities.
    # If they don't (legacy/direct returns), wrap them.
    if response.get("statusCode") == 200 and "data" not in response:
        # Extract core fields: items, total, etc. but exclude metadata/timestamps
        payload = {
            k: v
            for k, v in response.items()
            if k
            not in (
                "statusCode",
                "headers",
                "data_freshness",
                "success",
                "timestamp",
                "pagination",
            )
        }

        # If we have items but no data, wrap them properly
        if "items" in response and "items" not in payload:
            # Keep items and reconstruct pagination if needed
            payload["items"] = response.get("items")
            if "pagination" in response:
                payload["pagination"] = response["pagination"]
            pagination = response.get("pagination")
            total = pagination.get("total") if pagination and isinstance(pagination, dict) else None
            if total is None:
                total = len(response.get("items", []))
            payload["total"] = total

        wrapped = {"statusCode": 200, "data": payload}
        # Preserve data_freshness if it exists
        if "data_freshness" in response:
            wrapped["data_freshness"] = response["data_freshness"]
        # Preserve headers if they exist
        if "headers" in response:
            wrapped["headers"] = response["headers"]
        return wrapped

    return response


def _add_cors_headers(response: Any) -> Any:
    """Add CORS headers to response with origin whitelist.

    SECURITY: CORS is configured to whitelist specific origins from environment.
    This prevents unauthorized cross-origin requests and CSRF attacks.
    """
    if not isinstance(response, dict):
        msg = "Invalid response format"
        response = {
            "statusCode": 500,
            "errorType": "internal_error",
            "message": msg,
            "_error": msg,
        }
    if "headers" not in response:
        response["headers"] = {}

    # Get allowed origins from environment (comma-separated)
    # Default: only the CloudFront domain (set by Terraform)
    allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not allowed_origins_str:
        # Fallback: fetch CloudFront domain from Secrets Manager
        try:
            from lambda_function import fetch_cloudfront_domain_from_secrets

            cf_domain, _ = fetch_cloudfront_domain_from_secrets()
        except (ImportError, AttributeError):
            cf_domain = None
        allowed_origins = [cf_domain] if cf_domain else []
    else:
        allowed_origins = [o.strip() for o in allowed_origins_str.split(",")]

    # Get request origin from event (passed via Lambda context if available)
    # For now, set generic headers. In production, check Origin header.
    response["headers"]["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response["headers"]["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response["headers"]["Vary"] = "Origin"

    # Only set Allow-Origin if we have whitelisted origins
    if allowed_origins and allowed_origins[0]:
        response["headers"]["Access-Control-Allow-Origin"] = allowed_origins[0]
        response["headers"]["Access-Control-Allow-Credentials"] = "true"

    return response


def route_request(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Route request to handler. Public handlers checked first (no auth required)."""

    # Issue #11 FIX: Use strict path matching to distinguish /api/algo from /api/algorithm
    def matches_route(request_path: str, route_prefix: str) -> bool:
        if request_path == route_prefix:
            return True
        if request_path.startswith(route_prefix + "/"):
            return True
        return False

    # Check public handlers first (health, etc.) - these don't require JWT
    for prefix, handler in PUBLIC_HANDLERS.items():
        if matches_route(path, prefix):
            try:
                response = handler.handle(cur, path, method, params, body, jwt_claims=jwt_claims)
                return _add_cors_headers(_wrap_response(response))
            except Exception as e:
                return _add_cors_headers(_wrap_response(_format_handler_error(e)))

    # Check authenticated handlers
    for prefix, handler in HANDLERS.items():
        if matches_route(path, prefix):
            try:
                response = handler.handle(cur, path, method, params, body, jwt_claims=jwt_claims)
                return _add_cors_headers(_wrap_response(response))
            except Exception as e:
                return _add_cors_headers(_wrap_response(_format_handler_error(e)))

    # Check if the path matches a route module that failed to import
    # More specific routes are checked first (they appear first in _HANDLER_CONFIG)
    # This properly distinguishes between:
    # - Routes that should exist but failed to load (e.g., /api/algo) → 503
    # - Truly missing endpoints (e.g., /api/algorithm when no /api/algo* route) → 404
    for route_path, module_name in _HANDLER_CONFIG:
        if module_name in _ROUTE_IMPORT_ERRORS and matches_route(path, route_path):
            error = _ROUTE_IMPORT_ERRORS[module_name]
            import_status = get_import_status()
            logger.error(f"Route {path} requested but handler module {module_name} failed to import: {error}")
            # Include diagnostic information for dashboard/clients
            msg = f"Route handler unavailable: {module_name} module failed to load"
            response = {
                "statusCode": 503,
                "errorType": "route_load_error",
                "message": msg,
                "error": msg,
                "_error": msg,
                "_diagnostic": {
                    "failed_module": module_name,
                    "module_error": error,
                    "failed_route_count": import_status["failed_routes"],
                    "critical_failures": import_status["critical_failures"],
                    "all_failed_modules": import_status["failed_modules"],
                },
            }
            return _add_cors_headers(_wrap_response(response))

    # No handler found - return properly formatted 404 with CORS headers
    logger.warning(f"No handler found for path: {path}")
    msg = "Endpoint not found"
    return _add_cors_headers(
        _wrap_response({"statusCode": 404, "errorType": "not_found", "message": msg, "_error": msg})
    )


def get_import_status() -> dict[str, Any]:
    """Return structured import status for monitoring/diagnostics.

    Used by:
    - CloudWatch metrics: publish import_errors count
    - Health endpoint: report route failures
    - Dashboard alerts: show which routes are unavailable

    Returns:
        dict: {
            "total_routes": int,
            "successful_routes": int,
            "failed_routes": int,
            "failed_modules": list[str],
            "critical_failures": list[str],
            "failed_details": {module: error_msg},
            "skipped_routes": list[{"path": str, "module": str, "error": str}]
        }
    """
    total_route_modules = len(_CRITICAL_ROUTES) + len(_OPTIONAL_ROUTE_MODULES)
    critical_failures = [m for m in _ROUTE_IMPORT_ERRORS if m in _CRITICAL_ROUTES]
    return {
        "total_routes": total_route_modules,
        "successful_routes": len(_AVAILABLE_ROUTES),
        "failed_routes": len(_ROUTE_IMPORT_ERRORS),
        "critical_failures": critical_failures,
        "failed_modules": list(_ROUTE_IMPORT_ERRORS.keys()),
        "failed_details": _ROUTE_IMPORT_ERRORS,
        "skipped_routes": _SKIPPED_ROUTES,
        "has_critical_failures": len(critical_failures) > 0,
    }


def _publish_import_metrics() -> None:
    """Publish API route import status to CloudWatch metrics.

    Creates custom metrics:
    - APIRouteImportErrors: count of failed route imports
    - APICriticalRouteFailures: count of critical route failures (health/algo)

    These metrics trigger CloudWatch alarms for alerting.
    """
    try:
        import boto3

        cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")

        status = get_import_status()

        # Publish count of failed imports
        if status["failed_routes"] > 0:
            cloudwatch.put_metric_data(
                Namespace="AlgoTrading/API",
                MetricData=[
                    {
                        "MetricName": "APIRouteImportErrors",
                        "Value": status["failed_routes"],
                        "Unit": "Count",
                    },
                    {
                        "MetricName": "APICriticalRouteFailures",
                        "Value": len(status["critical_failures"]),
                        "Unit": "Count",
                    },
                ],
            )
            logger.info(
                f"Published CloudWatch metrics: APIRouteImportErrors={status['failed_routes']}, APICriticalRouteFailures={len(status['critical_failures'])}"
            )
    except Exception as e:
        logger.warning(f"Failed to publish CloudWatch metrics: {type(e).__name__}: {str(e)[:100]}")


# Publish metrics at startup
try:
    _publish_import_metrics()
except Exception as e:
    logger.warning(f"Metrics publishing failed at startup: {e}")


def _format_handler_error(e: Exception) -> dict[str, Any]:
    """Format exception as error response with diagnostic error types.

    Returns specific error type to client for debugging without exposing sensitive details.
    Logs full stack trace server-side for investigation.
    Error types documented in steering/system.md → API Error Handling section.
    All errors include _error field for consistent error detection by dashboard.
    """
    error_type = type(e).__name__
    error_msg = str(e)

    # Handle APIException first (has explicit status code and error type)
    api_exception_failed = False
    try:
        from exceptions import APIException

        if isinstance(e, APIException):
            # Sanitize message to remove credentials/sensitive info
            try:
                from utils.error_handlers import sanitize_error_message

                msg = sanitize_error_message(e.message)
            except (ImportError, AttributeError) as sanitize_err:
                logger.warning(
                    f"[ERROR_HANDLER] Failed to sanitize error message: {sanitize_err} — using fallback sanitization"
                )
                import re

                msg = re.sub(r"password=\S+|api.?key=\S+", "***", e.message)
            return {
                "statusCode": e.status_code,
                "errorType": e.error_type,
                "message": msg,
                "_error": msg,
            }
    except ImportError as import_err:
        logger.warning(f"[ERROR_HANDLER] APIException not available ({import_err}) — using generic error mapping")
        api_exception_failed = True
    except Exception as handler_err:
        logger.error(
            f"[ERROR_HANDLER] Unexpected error in exception handler ({type(handler_err).__name__}: {handler_err}) — using generic error mapping",
            exc_info=True,
        )
        api_exception_failed = True

    if api_exception_failed:
        logger.info(f"[ERROR_HANDLER] Falling back to generic error mapping for {error_type}: {error_msg[:100]}")

    # Map exception types to documented diagnostic error codes
    # Schema errors: missing tables, columns, or migration issues
    if "UndefinedTable" in error_type or "UndefinedColumn" in error_type:
        msg = "Database schema mismatch or migration issue"
        return {
            "statusCode": 503,
            "errorType": "schema_error",
            "message": msg,
            "_error": msg,
        }

    # Connection errors: RDS/proxy unavailable or network issues
    elif "OperationalError" in error_type or "Connection" in error_type or "failed to connect" in error_msg.lower():
        msg = "RDS/database connection failed"
        return {
            "statusCode": 503,
            "errorType": "connection_error",
            "message": msg,
            "_error": msg,
        }

    # Query execution errors: SQL syntax or constraint violations
    elif "ProgrammingError" in error_type or "IntegrityError" in error_type or "statement error" in error_msg.lower():
        msg = "Database query execution failed"
        return {
            "statusCode": 503,
            "errorType": "query_error",
            "message": msg,
            "_error": msg,
        }

    # Auth errors: JWT validation, token expiry, Cognito failures
    elif (
        "Unauthorized" in error_type or "Forbidden" in error_type or "JWT" in error_type or "token" in error_msg.lower()
    ):
        msg = "JWT validation or Cognito authorization failed"
        return {
            "statusCode": 403,
            "errorType": "auth_error",
            "message": msg,
            "_error": msg,
        }

    # Cognito config errors: missing or invalid Cognito environment variables
    elif (
        "COGNITO_USER_POOL_ID" in error_msg
        or "COGNITO_CLIENT_ID" in error_msg
        or "cognito.*config" in error_msg.lower()
    ):
        msg = "Cognito environment variables not configured"
        return {
            "statusCode": 500,
            "errorType": "cognito_config_error",
            "message": msg,
            "_error": msg,
        }

    # Data access errors: code bugs (AttributeError, KeyError, etc.) accessing response fields
    elif "AttributeError" in error_type or "KeyError" in error_type or "IndexError" in error_type:
        msg = "Code bug accessing data fields"
        return {
            "statusCode": 500,
            "errorType": "data_access_error",
            "message": msg,
            "_error": msg,
        }

    # No data errors: required data table is empty or missing
    elif "no.*data" in error_msg.lower() or "empty" in error_msg.lower() or "not.*found" in error_msg.lower():
        msg = "Required data table is empty or missing"
        return {
            "statusCode": 500,
            "errorType": "no_data_error",
            "message": msg,
            "_error": msg,
        }

    # Data processing errors: generic data transformation/processing failures
    elif (
        "process" in error_msg.lower()
        or "data" in error_msg.lower()
        or "ValueError" in error_type
        or "TypeError" in error_type
    ):
        msg = "Generic data processing failure"
        return {
            "statusCode": 500,
            "errorType": "data_processing_error",
            "message": msg,
            "_error": msg,
        }

    # Invalid input: malformed request parameters or body
    elif "invalid" in error_msg.lower() or "Bad Request" in error_msg:
        msg = "Client sent invalid query parameters or request body"
        return {
            "statusCode": 400,
            "errorType": "invalid_input",
            "message": msg,
            "_error": msg,
        }

    # Request timeouts
    elif "Timeout" in error_type or "timeout" in error_msg.lower():
        msg = "Request exceeded statement_timeout"
        return {
            "statusCode": 504,
            "errorType": "timeout",
            "message": msg,
            "_error": msg,
        }

    else:
        # Generic internal error for unknown exceptions (log type for debugging)
        logger.error(f"Unclassified error type '{error_type}': {error_msg}")
        msg = "Service error"
        return {
            "statusCode": 500,
            "errorType": "data_processing_error",
            "message": msg,
            "_error": msg,
        }
