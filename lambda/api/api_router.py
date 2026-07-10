"""API Router - dispatcher."""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

# Set up imports for Lambda API - ensures routes and api_utils are importable
import setup_imports  # noqa: F401
from psycopg2.extensions import cursor

logger = logging.getLogger(__name__)

# Import consolidated response handling service
try:
    from utils.response_service import wrap_response, format_handler_error, build_error_response
except ImportError:
    # Fallback for different import contexts
    try:
        from api_utils.response_service import wrap_response, format_handler_error, build_error_response
    except ImportError:
        # If response_service doesn't exist, create stubs (shouldn't happen in production)
        logger.warning("response_service.py not found - using stub implementations")
        def wrap_response(r: Any) -> Any: return r
        def format_handler_error(e: Exception) -> dict[str, Any]:
            return {"statusCode": 500, "errorType": "error", "message": str(e)}
        def build_error_response(code: int, err_type: str, msg: str) -> dict[str, Any]:
            return {"statusCode": code, "errorType": err_type, "message": msg}


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
    "diagnostics",  # Position data sync health check endpoint
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

# Diagnostics endpoint (public, for debugging data sync issues)
if "diagnostics" in _AVAILABLE_ROUTES:
    PUBLIC_HANDLERS["/api/diagnostics"] = _AVAILABLE_ROUTES["diagnostics"]
else:
    logger.error("WARNING: diagnostics route module failed to import - diagnostics endpoint unavailable")

# Dashboard data endpoints (public, for analytics/monitoring - no sensitive data)
# These endpoints return portfolio snapshots, performance metrics, and trading statistics
# which are safe to expose publicly for dashboard consumption
if "algo" in _AVAILABLE_ROUTES:
    dashboard_endpoints = [
        "/api/algo/portfolio",      # Portfolio snapshot data
        "/api/algo/positions",      # Open position list
        "/api/algo/performance",    # Performance metrics
        "/api/algo/risk-metrics",   # Risk analytics
        "/api/algo/last-run",       # Latest orchestrator run status
        "/api/algo/status",         # Algorithm execution status (alternative to last-run)
        "/api/algo/trades",         # Trade history
        "/api/algo/config",         # System configuration
        "/api/algo/data-status",    # Data freshness status
        "/api/algo/markets",        # Market data
        "/api/algo/scores",         # Stock scores
        "/api/algo/dashboard-signals",  # Signal data for dashboard
        "/api/algo/circuit-breakers",  # Circuit breaker status
        "/api/algo/daily-return-histogram",  # Daily return distribution
        "/api/algo/equity-curve",   # Portfolio equity curve
        "/api/algo/holding-period-distribution",  # Holding period histogram
        "/api/algo/stage-distribution",  # Market stage distribution
        "/api/algo/trade-distribution",  # Trade outcome distribution
        "/api/algo/swing-scores",   # Swing score rankings
        "/api/algo/swing-scores-history",  # Historical swing scores
        "/api/algo/sector-rotation",  # Sector rotation metrics
        "/api/algo/sector-breadth",  # Sector breadth indicators
        "/api/algo/sector-stage2",  # Sector stage 2 stocks
        "/api/algo/execution/stats",  # Execution statistics
        "/api/algo/execution/recent",  # Recent execution records
        "/api/algo/notifications",  # System notifications
        "/api/algo/patrol",         # Data patrol status
        "/api/algo/patrol-log",     # Patrol history
    ]
    for endpoint in dashboard_endpoints:
        PUBLIC_HANDLERS[endpoint] = _AVAILABLE_ROUTES["algo"]

    # Also register endpoint aliases as public
    alias_endpoints = [
        "/api/portfolio",   # Alias for /api/algo/portfolio
        "/api/positions",   # Alias for /api/algo/positions
    ]
    for endpoint in alias_endpoints:
        PUBLIC_HANDLERS[endpoint] = _AVAILABLE_ROUTES["algo"]

    logger.info(f"[STARTUP] Registered {len(dashboard_endpoints)} dashboard endpoints + {len(alias_endpoints)} aliases as public")
    logger.info(f"[STARTUP] Dashboard aliases /api/portfolio and /api/positions are now public")

# Register other public analytics endpoints needed by dashboard
# These support market context, economic data, and analytical views
if all(m in _AVAILABLE_ROUTES for m in ["economic", "market", "sentiment", "prices", "stocks", "signals"]):
    analytics_endpoints = [
        ("/api/economic", _AVAILABLE_ROUTES.get("economic")),
        ("/api/market", _AVAILABLE_ROUTES.get("market")),
        ("/api/sentiment", _AVAILABLE_ROUTES.get("sentiment")),
        ("/api/prices", _AVAILABLE_ROUTES.get("prices")),
        ("/api/stocks", _AVAILABLE_ROUTES.get("stocks")),
        ("/api/signals", _AVAILABLE_ROUTES.get("signals")),
    ]
    for path, handler in analytics_endpoints:
        if handler:
            PUBLIC_HANDLERS[path] = handler
    logger.info(f"[STARTUP] Registered {len([e for e, h in analytics_endpoints if h])} analytics endpoints as public")

# Build authenticated handlers (order matters: /api/algo/risk-dashboard must come before /api/algo)
# Note: /api/positions and /api/portfolio aliases are now in PUBLIC_HANDLERS
_HANDLER_CONFIG = [
    ("/api/algo/risk-dashboard", "risk_dashboard"),
    # NOTE: /api/algo/scores is NOT routed to the "scores" module here — /api/algo below
    # matches it first (matches_route() is a prefix match), so it always dispatches to
    # routes/algo.py's _get_dashboard_scores instead. That's the live, working handler;
    # routes/scores.py's _get_stock_scores is a separate, considerably richer query
    # (sortBy, valuation fields) that was never actually reachable through this route.
    # Wiring it up would need its own verification pass against the dashboard/API
    # contract, not a routing reorder — left as-is to avoid an unverified regression.
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
    ("/api/scores", "scores"),  # Legacy /api/scores endpoint (for backwards compatibility)
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
    # Default: fetch CloudFront domain from Secrets Manager (set by Terraform)
    allowed_origins_str = os.getenv("ALLOWED_ORIGINS")
    if allowed_origins_str:
        allowed_origins_str = allowed_origins_str.strip()

    if not allowed_origins_str:
        # Fallback: fetch CloudFront domain from Secrets Manager
        try:
            from lambda_function import fetch_cloudfront_domain_from_secrets

            cf_domain, _ = fetch_cloudfront_domain_from_secrets()
        except (ImportError, AttributeError):
            cf_domain = None
        allowed_origins = [cf_domain] if cf_domain else []
    else:
        allowed_origins = [o.strip() for o in allowed_origins_str.split(",") if o.strip()]

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
                logger.debug(f"[ROUTE_REQUEST] Calling public handler for {path} (prefix {prefix})")
                response = handler.handle(cur, path, method, params, body, jwt_claims=jwt_claims)
                logger.debug(
                    f"[ROUTE_REQUEST] Public handler succeeded for {path}, status={response.get('statusCode')}"
                )
                return _add_cors_headers(wrap_response(response))
            except Exception as e:
                logger.error(
                    f"[ROUTE_REQUEST_EXCEPTION] Public handler {prefix} raised exception for {path}: "
                    f"{type(e).__name__}: {str(e)[:200]}",
                    exc_info=True,
                )
                return _add_cors_headers(wrap_response(format_handler_error(e)))

    # Check authenticated handlers
    for prefix, handler in HANDLERS.items():
        if matches_route(path, prefix):
            try:
                logger.debug(f"[ROUTE_REQUEST] Calling handler for {path} (prefix {prefix})")
                response = handler.handle(cur, path, method, params, body, jwt_claims=jwt_claims)
                logger.debug(f"[ROUTE_REQUEST] Handler succeeded for {path}, status={response.get('statusCode')}")
                return _add_cors_headers(wrap_response(response))
            except Exception as e:
                logger.error(
                    f"[ROUTE_REQUEST_EXCEPTION] Handler {prefix} raised exception for {path}: "
                    f"{type(e).__name__}: {str(e)[:200]}",
                    exc_info=True,
                )
                return _add_cors_headers(wrap_response(format_handler_error(e)))

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
        wrap_response(build_error_response(404, "not_found", msg))
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


