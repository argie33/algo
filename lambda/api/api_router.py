"""API Router - dispatcher."""
import logging, sys, os, json, threading
from pathlib import Path

# Ensure routes module and utils can be imported (needed for dev_server.py)
api_dir = str(Path(__file__).parent)
lambda_dir = str(Path(__file__).parent.parent)
root_dir = str(Path(__file__).parent.parent.parent)

# CRITICAL: Ensure /lambda/api comes BEFORE /utils root in sys.path
# Remove and reorder paths to ensure correct import resolution
_path_list = list(sys.path)
for p in [api_dir, lambda_dir, root_dir]:
    if p in _path_list:
        _path_list.remove(p)
_path_list.insert(0, api_dir)
_path_list.insert(1, lambda_dir)
_path_list.insert(2, root_dir)
sys.path[:] = _path_list

logger = logging.getLogger(__name__)

# Static imports for critical routes - import errors fail fast at startup
try:
    from routes import health
except ImportError as e:
    raise RuntimeError(f"CRITICAL: Failed to import routes.health (required for API to function): {e}") from e

try:
    from routes import algo
except ImportError as e:
    raise RuntimeError(f"CRITICAL: Failed to import routes.algo (required for API to function): {e}") from e

# Import routes gracefully - if a single module fails, others still work
_ROUTE_IMPORT_ERRORS = {}  # Track which routes failed to import: {module_name: error_msg}
_AVAILABLE_ROUTES = {}  # Track which routes loaded successfully
_CRITICAL_ROUTES = {'health', 'algo'}  # Routes that must load for API to function

# Critical routes are imported statically above; these are optional routes with graceful fallback
_OPTIONAL_ROUTE_MODULES = [
    'financials', 'earnings', 'signals', 'prices', 'stocks',
    'sectors', 'industries', 'market', 'economic', 'sentiment',
    'scores', 'research', 'audit', 'trades', 'admin', 'contact', 'settings', 'risk_dashboard',
    'data_coverage'
]

# Track startup state for diagnostics (thread-safe)
_STARTUP_TIME = None
_IMPORT_DURATION = None
_STARTUP_LOCK = threading.Lock()  # Protects startup time and import duration updates

# Populate available routes with statically imported critical routes
_AVAILABLE_ROUTES['health'] = health
_AVAILABLE_ROUTES['algo'] = algo

# Dynamically import optional routes with error handling
for module_name in _OPTIONAL_ROUTE_MODULES:
    try:
        module = __import__(f'routes.{module_name}', fromlist=[module_name])
        _AVAILABLE_ROUTES[module_name] = module
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"
        _ROUTE_IMPORT_ERRORS[module_name] = error_msg
        logger.warning(f"Failed to import optional routes.{module_name}: {error_msg}", exc_info=True)

# Report startup status: log all failures with clear visibility
if _ROUTE_IMPORT_ERRORS:
    failed_modules = list(_ROUTE_IMPORT_ERRORS.keys())
    critical_failures = [m for m in failed_modules if m in _CRITICAL_ROUTES]

    # Log structured status for monitoring
    logger.error(f"ROUTE_IMPORT_STATUS: failed_count={len(failed_modules)}, critical_count={len(critical_failures)}, modules={failed_modules}")

    # If critical routes failed, the API cannot function
    if critical_failures:
        error_detail = {
            "error": "CRITICAL_ROUTE_IMPORT_FAILURE",
            "critical_failures": critical_failures,
            "all_failures": failed_modules,
            "details": {m: _ROUTE_IMPORT_ERRORS[m] for m in critical_failures}
        }
        logger.error(f"CRITICAL_ROUTE_IMPORT_FAILURE: {json.dumps(error_detail)}")
        # Set environment variable that monitoring can detect
        os.environ['API_CRITICAL_ROUTES_FAILED'] = json.dumps(critical_failures)

# Build handler mappings from available routes (some may be missing if they failed to import)
PUBLIC_HANDLERS = {}
HANDLERS = {}

# Health endpoints must be public and checked first
if 'health' in _AVAILABLE_ROUTES:
    PUBLIC_HANDLERS['/api/health'] = _AVAILABLE_ROUTES['health']
    PUBLIC_HANDLERS['/health'] = _AVAILABLE_ROUTES['health']
else:
    logger.error("CRITICAL: health route module failed to import - health endpoints will not work")

# Build authenticated handlers (order matters: /api/algo/risk-dashboard must come before /api/algo)
_HANDLER_CONFIG = [
    ('/api/algo/risk-dashboard', 'risk_dashboard'),
    ('/api/algo', 'algo'),
    ('/api/financials', 'financials'),
    ('/api/earnings', 'earnings'),
    ('/api/signals', 'signals'),
    ('/api/prices', 'prices'),
    ('/api/stocks', 'stocks'),
    ('/api/sectors', 'sectors'),
    ('/api/industries', 'industries'),
    ('/api/market', 'market'),
    ('/api/economic', 'economic'),
    ('/api/sentiment', 'sentiment'),
    ('/api/scores', 'scores'),
    ('/api/research', 'research'),
    ('/api/audit', 'audit'),
    ('/api/trades', 'trades'),
    ('/api/admin', 'admin'),
    ('/api/contact', 'contact'),
    ('/api/settings', 'settings'),
    ('/api/data-coverage', 'data_coverage'),
]

_SKIPPED_ROUTES = []  # Track which routes were skipped due to import failures

for path, module_name in _HANDLER_CONFIG:
    if module_name in _AVAILABLE_ROUTES:
        HANDLERS[path] = _AVAILABLE_ROUTES[module_name]
    else:
        _SKIPPED_ROUTES.append({"path": path, "module": module_name, "error": _ROUTE_IMPORT_ERRORS.get(module_name, "unknown")})
        logger.warning(f"Route {path} SKIPPED - module routes.{module_name} failed to import: {_ROUTE_IMPORT_ERRORS.get(module_name, 'unknown')}")

# Log final status
if _SKIPPED_ROUTES:
    logger.error(f"ROUTE_SKIP_STATUS: total_skipped={len(_SKIPPED_ROUTES)}, routes={[r['path'] for r in _SKIPPED_ROUTES]}")

def _wrap_response(response):
    """Standardize response format for consistent client handling.

    Issue 2.1 FIX: Wrap all responses in 'data' field so dashboard can consistently:
    1. Access response payload via response['data']
    2. Extract errors via response['_error'] (always at top level)

    Formats handled:
    - list_response: {"statusCode": 200, "items": [...]} → {"statusCode": 200, "data": {"items": [...]}}
    - json_response: {"statusCode": 200, "data": {...}} → unchanged (already wrapped)
    - error_response: {"statusCode": 4xx, "errorType": "...", "message": "..."} → unchanged (no data field)
    """
    if not isinstance(response, dict):
        return response

    # Errors don't need wrapping - they're returned as-is
    if response.get('errorType') or response.get('statusCode', 200) >= 400:
        return response

    # Already wrapped in 'data' field (json_response format)
    if 'data' in response:
        return response

    # Wrap other successful responses (list_response format: {items: [...], total: N})
    if response.get('statusCode') == 200 and not response.get('_error'):
        # Extract all top-level fields except statusCode/headers
        payload = {k: v for k, v in response.items() if k not in ('statusCode', 'headers')}
        response = {
            'statusCode': 200,
            'data': payload
        }
        if 'headers' in response:
            response['headers'] = response['headers']

    return response

def _add_cors_headers(response):
    """Add CORS headers to response."""
    if not isinstance(response, dict):
        msg = "Invalid response format"
        response = {"statusCode": 500, "errorType": "internal_error", "message": msg, "_error": msg}
    if 'headers' not in response:
        response['headers'] = {}
    response['headers']['Access-Control-Allow-Origin'] = '*'
    response['headers']['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response['headers']['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

def route_request(cur, path, method, params, body=None, jwt_claims=None):
    """Route request to handler. Public handlers checked first (no auth required)."""
    # Check public handlers first (health, etc.) - these don't require JWT
    for prefix, handler in PUBLIC_HANDLERS.items():
        if path.startswith(prefix):
            try:
                response = handler.handle(cur, path, method, params, body, jwt_claims=jwt_claims)
                return _add_cors_headers(_wrap_response(response))
            except Exception as e:
                logger.error(f"Public handler error for {path}: {e}", exc_info=True)
                return _add_cors_headers(_wrap_response(_format_handler_error(e)))

    # Check authenticated handlers
    for prefix, handler in HANDLERS.items():
        if path.startswith(prefix):
            try:
                response = handler.handle(cur, path, method, params, body, jwt_claims=jwt_claims)
                return _add_cors_headers(_wrap_response(response))
            except Exception as e:
                logger.error(f"Handler error for {path}: {e}", exc_info=True)
                return _add_cors_headers(_wrap_response(_format_handler_error(e)))

    # Check if the path matches a route module that failed to import
    # More specific routes are checked first (they appear first in _HANDLER_CONFIG)
    for route_path, module_name in _HANDLER_CONFIG:
        if module_name in _ROUTE_IMPORT_ERRORS and path.startswith(route_path):
            error = _ROUTE_IMPORT_ERRORS[module_name]
            import_status = get_import_status()
            logger.error(f"Route {path} requested but handler module {module_name} failed to import: {error}")
            # Include diagnostic information for dashboard/clients
            msg = f"Route handler unavailable: {module_name} module failed to load"
            response = {
                "statusCode": 503,
                "errorType": "route_load_error",
                "message": msg,
                "_error": msg,
                "_diagnostic": {
                    "failed_module": module_name,
                    "module_error": error,
                    "failed_route_count": import_status['failed_routes'],
                    "critical_failures": import_status['critical_failures'],
                    "all_failed_modules": import_status['failed_modules'],
                }
            }
            return _add_cors_headers(_wrap_response(response))

    # No handler found - return properly formatted 404 with CORS headers
    logger.warning(f"No handler found for path: {path}")
    msg = "Endpoint not found"
    return _add_cors_headers(_wrap_response({"statusCode": 404, "errorType": "not_found", "message": msg, "_error": msg}))


def get_import_status():
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
    critical_failures = [m for m in _ROUTE_IMPORT_ERRORS if m in _CRITICAL_ROUTES]
    return {
        "total_routes": len(_ROUTE_MODULES),
        "successful_routes": len(_AVAILABLE_ROUTES),
        "failed_routes": len(_ROUTE_IMPORT_ERRORS),
        "critical_failures": critical_failures,
        "failed_modules": list(_ROUTE_IMPORT_ERRORS.keys()),
        "failed_details": _ROUTE_IMPORT_ERRORS,
        "skipped_routes": _SKIPPED_ROUTES,
        "has_critical_failures": len(critical_failures) > 0,
    }

def _publish_import_metrics():
    """Publish API route import status to CloudWatch metrics.

    Creates custom metrics:
    - APIRouteImportErrors: count of failed route imports
    - APICriticalRouteFailures: count of critical route failures (health/algo)

    These metrics trigger CloudWatch alarms for alerting.
    """
    try:
        import boto3
        cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

        status = get_import_status()

        # Publish count of failed imports
        if status['failed_routes'] > 0:
            cloudwatch.put_metric_data(
                Namespace='AlgoTrading/API',
                MetricData=[
                    {
                        'MetricName': 'APIRouteImportErrors',
                        'Value': status['failed_routes'],
                        'Unit': 'Count',
                    },
                    {
                        'MetricName': 'APICriticalRouteFailures',
                        'Value': len(status['critical_failures']),
                        'Unit': 'Count',
                    }
                ]
            )
            logger.info(f"Published CloudWatch metrics: APIRouteImportErrors={status['failed_routes']}, APICriticalRouteFailures={len(status['critical_failures'])}")
    except Exception as e:
        logger.warning(f"Failed to publish CloudWatch metrics: {type(e).__name__}: {str(e)[:100]}")

# Publish metrics at startup
try:
    _publish_import_metrics()
except Exception as e:
    logger.warning(f"Metrics publishing failed at startup: {e}")

def _format_handler_error(e):
    """Format exception as error response with diagnostic error types.

    Returns specific error type to client for debugging without exposing sensitive details.
    Logs full stack trace server-side for investigation.
    Error types documented in steering/algo.md → Error Handling & Diagnostics section.
    All errors include _error field for consistent error detection by dashboard.
    """
    error_type = type(e).__name__
    error_msg = str(e)

    # Map exception types to documented diagnostic error codes
    # Schema errors: missing tables, columns, or migration issues
    if 'UndefinedTable' in error_type or 'UndefinedColumn' in error_type:
        msg = "Database schema mismatch or migration issue"
        return {"statusCode": 503, "errorType": "schema_error", "message": msg, "_error": msg}

    # Connection errors: RDS/proxy unavailable or network issues
    elif 'OperationalError' in error_type or 'Connection' in error_type or 'failed to connect' in error_msg.lower():
        msg = "RDS/database connection failed"
        return {"statusCode": 503, "errorType": "connection_error", "message": msg, "_error": msg}

    # Query execution errors: SQL syntax or constraint violations
    elif 'ProgrammingError' in error_type or 'IntegrityError' in error_type or 'statement error' in error_msg.lower():
        msg = "Database query execution failed"
        return {"statusCode": 503, "errorType": "query_error", "message": msg, "_error": msg}

    # Auth errors: JWT validation, token expiry, Cognito failures
    elif 'Unauthorized' in error_type or 'Forbidden' in error_type or 'JWT' in error_type or 'token' in error_msg.lower():
        msg = "JWT validation or Cognito authorization failed"
        return {"statusCode": 403, "errorType": "auth_error", "message": msg, "_error": msg}

    # Cognito config errors: missing or invalid Cognito environment variables
    elif 'COGNITO_USER_POOL_ID' in error_msg or 'COGNITO_CLIENT_ID' in error_msg or 'cognito.*config' in error_msg.lower():
        msg = "Cognito environment variables not configured"
        return {"statusCode": 500, "errorType": "cognito_config_error", "message": msg, "_error": msg}

    # Data access errors: code bugs (AttributeError, KeyError, etc.) accessing response fields
    elif 'AttributeError' in error_type or 'KeyError' in error_type or 'IndexError' in error_type:
        msg = "Code bug accessing data fields"
        return {"statusCode": 500, "errorType": "data_access_error", "message": msg, "_error": msg}

    # No data errors: required data table is empty or missing
    elif 'no.*data' in error_msg.lower() or 'empty' in error_msg.lower() or 'not.*found' in error_msg.lower():
        msg = "Required data table is empty or missing"
        return {"statusCode": 500, "errorType": "no_data_error", "message": msg, "_error": msg}

    # Data processing errors: generic data transformation/processing failures
    elif 'process' in error_msg.lower() or 'data' in error_msg.lower() or 'ValueError' in error_type or 'TypeError' in error_type:
        msg = "Generic data processing failure"
        return {"statusCode": 500, "errorType": "data_processing_error", "message": msg, "_error": msg}

    # Invalid input: malformed request parameters or body
    elif 'invalid' in error_msg.lower() or 'Bad Request' in error_msg:
        msg = "Client sent invalid query parameters or request body"
        return {"statusCode": 400, "errorType": "invalid_input", "message": msg, "_error": msg}

    # Request timeouts
    elif 'Timeout' in error_type or 'timeout' in error_msg.lower():
        msg = "Request exceeded statement_timeout"
        return {"statusCode": 504, "errorType": "timeout", "message": msg, "_error": msg}

    else:
        # Generic internal error for unknown exceptions (log type for debugging)
        logger.error(f"Unclassified error type '{error_type}': {error_msg}")
        msg = "Service error"
        return {"statusCode": 500, "errorType": "data_processing_error", "message": msg, "_error": msg}
