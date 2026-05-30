"""API Router - dispatcher."""
import logging, inspect, sys
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

# Pre-compute which handlers accept jwt_claims (avoids TypeError fallback hacks)
_JWT_AWARE = {
    prefix for prefix, handler in HANDLERS.items()
    if 'jwt_claims' in inspect.signature(handler.handle).parameters
}

def route_request(cur, path, method, params, body=None, jwt_claims=None):
    """Route request to handler. Public handlers checked first (no auth required)."""
    # Check public handlers first (health, etc.) - these don't require JWT
    for prefix, handler in PUBLIC_HANDLERS.items():
        if path.startswith(prefix):
            try:
                return handler.handle(cur, path, method, params, body)
            except Exception as e:
                logger.error(f"Public handler error for {path}: {e}", exc_info=True)
                return {"statusCode": 500, "errorType": "error", "message": "Handler error"}

    # List-returning endpoints that should return 200+empty on failure (not 500)
    _LIST_ENDPOINTS = {'/api/scores', '/api/industries', '/api/sectors', '/api/algo/sector'}

    # Check authenticated handlers
    for prefix, handler in HANDLERS.items():
        if path.startswith(prefix):
            try:
                if prefix in _JWT_AWARE:
                    return handler.handle(cur, path, method, params, body, jwt_claims=jwt_claims)
                return handler.handle(cur, path, method, params, body)
            except Exception as e:
                logger.error(f"Handler error for {path}: {e}", exc_info=True)
                # Return 200+empty for data endpoints so browser doesn't log red F12 errors
                if any(path.startswith(ep) for ep in _LIST_ENDPOINTS):
                    return {"statusCode": 200, "items": [], "total": 0}
                return {"statusCode": 500, "errorType": "error", "message": "Handler error"}
    return {"statusCode": 404, "errorType": "not_found", "message": "No handler"}
