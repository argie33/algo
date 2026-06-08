"""API Router - dispatcher."""
import logging, sys
from pathlib import Path

# Ensure routes module can be imported
sys.path.insert(0, str(Path(__file__).parent))

logger = logging.getLogger(__name__)

# Import routes gracefully - if a single module fails, others still work
_ROUTE_IMPORT_ERRORS = {}  # Track which routes failed to import
_AVAILABLE_ROUTES = {}  # Track which routes loaded successfully

_ROUTE_MODULES = [
    'algo', 'financials', 'earnings', 'signals', 'prices', 'stocks',
    'sectors', 'industries', 'market', 'economic', 'sentiment',
    'scores', 'research', 'audit', 'trades', 'admin', 'contact', 'settings', 'health', 'risk_dashboard',
    'data_coverage'
]

for module_name in _ROUTE_MODULES:
    try:
        module = __import__(f'routes.{module_name}', fromlist=[module_name])
        _AVAILABLE_ROUTES[module_name] = module
    except Exception as e:
        _ROUTE_IMPORT_ERRORS[module_name] = f"{type(e).__name__}: {str(e)[:100]}"
        logger.error(f"Failed to import routes.{module_name}: {type(e).__name__}: {str(e)}", exc_info=True)

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

for path, module_name in _HANDLER_CONFIG:
    if module_name in _AVAILABLE_ROUTES:
        HANDLERS[path] = _AVAILABLE_ROUTES[module_name]
    else:
        logger.warning(f"Route {path} skipped - module routes.{module_name} failed to import")

def _add_cors_headers(response):
    """Add CORS headers to response (applies to both success and error responses)."""
    if not isinstance(response, dict):
        response = {"statusCode": 500, "errorType": "internal_error", "message": "Invalid response format"}

    # CORS headers must be present on all responses, including errors
    response['headers'] = response.get('headers', {})
    response['headers'].update({
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
        'Content-Type': 'application/json'
    })
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
            logger.error(f"Route {path} requested but handler module {module_name} failed to import: {error}")
            return _add_cors_headers({
                "statusCode": 503,
                "errorType": "route_load_error",
                "message": f"Route handler unavailable: {module_name} module failed to load"
            })

    # No handler found - return properly formatted 404 with CORS headers
    logger.warning(f"No handler found for path: {path}")
    return _add_cors_headers({"statusCode": 404, "errorType": "not_found", "message": "Endpoint not found"})


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
