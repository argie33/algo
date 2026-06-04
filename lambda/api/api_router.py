"""API Router - dispatcher."""
import logging, sys
from pathlib import Path

# Ensure routes module can be imported
sys.path.insert(0, str(Path(__file__).parent))

from routes import (algo, financials, earnings, signals, prices, stocks,
                    sectors, industries, market, economic, sentiment,
                    scores, research, audit, trades, admin, contact, settings, health, risk_dashboard,
                    data_coverage)

logger = logging.getLogger(__name__)

# Health endpoint (public, no auth) must be checked first
PUBLIC_HANDLERS = {'/api/health': health}

HANDLERS = {
    '/api/algo/risk-dashboard': risk_dashboard,  # must come before /api/algo
    '/api/algo': algo, '/api/financials': financials, '/api/earnings': earnings,
    '/api/signals': signals, '/api/prices': prices, '/api/stocks': stocks,
    '/api/sectors': sectors, '/api/industries': industries,
    '/api/market': market, '/api/economic': economic, '/api/sentiment': sentiment,
    '/api/scores': scores, '/api/research': research, '/api/audit': audit,
    '/api/trades': trades, '/api/admin': admin,
    '/api/contact': contact, '/api/settings': settings,
    '/api/data-coverage': data_coverage,
}

def route_request(cur, path, method, params, body=None, jwt_claims=None):
    """Route request to handler. Public handlers checked first (no auth required)."""
    # Check public handlers first (health, etc.) - these don't require JWT
    for prefix, handler in PUBLIC_HANDLERS.items():
        if path.startswith(prefix):
            try:
                return handler.handle(cur, path, method, params, body, jwt_claims=jwt_claims)
            except Exception as e:
                logger.error(f"Public handler error for {path}: {e}", exc_info=True)
                return _format_handler_error(e)

    # Check authenticated handlers
    for prefix, handler in HANDLERS.items():
        if path.startswith(prefix):
            try:
                return handler.handle(cur, path, method, params, body, jwt_claims=jwt_claims)
            except Exception as e:
                logger.error(f"Handler error for {path}: {e}", exc_info=True)
                return _format_handler_error(e)
    return {"statusCode": 404, "errorType": "not_found", "message": "No handler"}


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
