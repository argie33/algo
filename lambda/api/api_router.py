"""API Router - dispatcher."""
import logging, sys, os, json
from pathlib import Path

# Ensure routes module can be imported
sys.path.insert(0, str(Path(__file__).parent))

logger = logging.getLogger(__name__)

# Import routes gracefully - if a single module fails, others still work
_ROUTE_IMPORT_ERRORS = {}  # Track which routes failed to import: {module_name: error_msg}
_AVAILABLE_ROUTES = {}  # Track which routes loaded successfully
_CRITICAL_ROUTES = {'health', 'algo'}  # Routes that must load for API to function

_ROUTE_MODULES = [
    'algo', 'financials', 'earnings', 'signals', 'prices', 'stocks',
    'sectors', 'industries', 'market', 'economic', 'sentiment',
    'scores', 'research', 'audit', 'trades', 'admin', 'contact', 'settings', 'health', 'risk_dashboard',
    'data_coverage'
]

# Track startup state for diagnostics
_STARTUP_TIME = None
_IMPORT_DURATION = None

for module_name in _ROUTE_MODULES:
    try:
        module = __import__(f'routes.{module_name}', fromlist=[module_name])
        _AVAILABLE_ROUTES[module_name] = module
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"
        _ROUTE_IMPORT_ERRORS[module_name] = error_msg
        severity = "CRITICAL" if module_name in _CRITICAL_ROUTES else "WARNING"
        logger.error(f"[{severity}] Failed to import routes.{module_name}: {error_msg}", exc_info=True)

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

def _add_cors_headers(response):
    """Add CORS headers to response."""
    if not isinstance(response, dict):
        response = {"statusCode": 500, "errorType": "internal_error", "message": "Invalid response format"}
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
                return _add_cors_headers(response)
            except Exception as e:
                logger.error(f"Public handler error for {path}: {e}", exc_info=True)
                return _add_cors_headers(_format_handler_error(e))

    # Check authenticated handlers
    for prefix, handler in HANDLERS.items():
        if path.startswith(prefix):
            try:
                response = handler.handle(cur, path, method, params, body, jwt_claims=jwt_claims)
                return _add_cors_headers(response)
            except Exception as e:
                logger.error(f"Handler error for {path}: {e}", exc_info=True)
                return _add_cors_headers(_format_handler_error(e))

    # Check if the path matches a route module that failed to import
    # More specific routes are checked first (they appear first in _HANDLER_CONFIG)
    for route_path, module_name in _HANDLER_CONFIG:
        if module_name in _ROUTE_IMPORT_ERRORS and path.startswith(route_path):
            error = _ROUTE_IMPORT_ERRORS[module_name]
            import_status = get_import_status()
            logger.error(f"Route {path} requested but handler module {module_name} failed to import: {error}")
            # Include diagnostic information for dashboard/clients
            response = {
                "statusCode": 503,
                "errorType": "route_load_error",
                "message": f"Route handler unavailable: {module_name} module failed to load",
                "_diagnostic": {
                    "failed_module": module_name,
                    "module_error": error,
                    "failed_route_count": import_status['failed_routes'],
                    "critical_failures": import_status['critical_failures'],
                    "all_failed_modules": import_status['failed_modules'],
                }
            }
            return _add_cors_headers(response)

    # No handler found - return properly formatted 404 with CORS headers
    logger.warning(f"No handler found for path: {path}")
    return _add_cors_headers({"statusCode": 404, "errorType": "not_found", "message": "Endpoint not found"})


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
    """
    error_type = type(e).__name__
    error_msg = str(e)

    # Map exception types to documented diagnostic error codes
    # Schema errors: missing tables, columns, or migration issues
    if 'UndefinedTable' in error_type or 'UndefinedColumn' in error_type:
        return {"statusCode": 503, "errorType": "schema_error", "message": "Database schema mismatch or migration issue"}

    # Connection errors: RDS/proxy unavailable or network issues
    elif 'OperationalError' in error_type or 'Connection' in error_type or 'failed to connect' in error_msg.lower():
        return {"statusCode": 503, "errorType": "connection_error", "message": "RDS/database connection failed"}

    # Query execution errors: SQL syntax or constraint violations
    elif 'ProgrammingError' in error_type or 'IntegrityError' in error_type or 'statement error' in error_msg.lower():
        return {"statusCode": 503, "errorType": "query_error", "message": "Database query execution failed"}

    # Auth errors: JWT validation, token expiry, Cognito failures
    elif 'Unauthorized' in error_type or 'Forbidden' in error_type or 'JWT' in error_type or 'token' in error_msg.lower():
        return {"statusCode": 403, "errorType": "auth_error", "message": "JWT validation or Cognito authorization failed"}

    # Cognito config errors: missing or invalid Cognito environment variables
    elif 'COGNITO_USER_POOL_ID' in error_msg or 'COGNITO_CLIENT_ID' in error_msg or 'cognito.*config' in error_msg.lower():
        return {"statusCode": 500, "errorType": "cognito_config_error", "message": "Cognito environment variables not configured"}

    # Data access errors: code bugs (AttributeError, KeyError, etc.) accessing response fields
    elif 'AttributeError' in error_type or 'KeyError' in error_type or 'IndexError' in error_type:
        return {"statusCode": 500, "errorType": "data_access_error", "message": "Code bug accessing data fields"}

    # No data errors: required data table is empty or missing
    elif 'no.*data' in error_msg.lower() or 'empty' in error_msg.lower() or 'not.*found' in error_msg.lower():
        return {"statusCode": 500, "errorType": "no_data_error", "message": "Required data table is empty or missing"}

    # Data processing errors: generic data transformation/processing failures
    elif 'process' in error_msg.lower() or 'data' in error_msg.lower() or 'ValueError' in error_type or 'TypeError' in error_type:
        return {"statusCode": 500, "errorType": "data_processing_error", "message": "Generic data processing failure"}

    # Invalid input: malformed request parameters or body
    elif 'invalid' in error_msg.lower() or 'Bad Request' in error_msg:
        return {"statusCode": 400, "errorType": "invalid_input", "message": "Client sent invalid query parameters or request body"}

    # Request timeouts
    elif 'Timeout' in error_type or 'timeout' in error_msg.lower():
        return {"statusCode": 504, "errorType": "timeout", "message": "Request exceeded statement_timeout"}

    else:
        # Generic internal error for unknown exceptions (log type for debugging)
        logger.error(f"Unclassified error type '{error_type}': {error_msg}")
        return {"statusCode": 500, "errorType": "data_processing_error", "message": "Service error"}
