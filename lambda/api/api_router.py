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
    """Format exception as error response with diagnostic details.

    Returns error type to client for debugging without exposing sensitive details.
    """
    error_type = type(e).__name__
    error_msg = str(e)

    # Map common exception types to diagnostic error codes
    if 'UndefinedTable' in error_type or 'UndefinedColumn' in error_type:
        return {"statusCode": 503, "errorType": "schema_error", "message": "Database schema issue"}
    elif 'OperationalError' in error_type or 'Connection' in error_type:
        return {"statusCode": 503, "errorType": "connection_error", "message": "Database connection failed"}
    elif 'Unauthorized' in error_type or 'Forbidden' in error_type or 'JWT' in error_type:
        return {"statusCode": 403, "errorType": "auth_error", "message": "Authorization failed"}
    elif 'ValueError' in error_type or 'TypeError' in error_type:
        return {"statusCode": 400, "errorType": "invalid_input", "message": error_msg}
    elif 'Timeout' in error_type:
        return {"statusCode": 504, "errorType": "timeout", "message": "Request timeout"}
    else:
        # Generic internal error for unknown exceptions
        return {"statusCode": 500, "errorType": error_type, "message": "Internal error"}
