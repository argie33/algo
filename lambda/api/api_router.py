"""API Router - dispatcher."""
import logging, inspect
from .routes import (algo, financials, earnings, signals, prices, stocks,
                      sectors, industries, market, economic, sentiment,
                      scores, research, audit, trades, admin, contact, settings)

logger = logging.getLogger(__name__)

HANDLERS = {
    '/api/algo': algo, '/api/financials': financials, '/api/earnings': earnings,
    '/api/signals': signals, '/api/prices': prices, '/api/stocks': stocks,
    '/api/sectors': sectors, '/api/industries': industries,
    '/api/market': market, '/api/economic': economic, '/api/sentiment': sentiment,
    '/api/scores': scores, '/api/research': research, '/api/audit': audit,
    '/api/trades': trades, '/api/admin': admin,
    '/api/contact': contact, '/api/settings': settings,
}

# Pre-compute which handlers accept jwt_claims (avoids TypeError fallback hacks)
_JWT_AWARE = {
    prefix for prefix, handler in HANDLERS.items()
    if 'jwt_claims' in inspect.signature(handler.handle).parameters
}


def route_request(cur, path, method, params, body=None, jwt_claims=None):
    """Route request to handler."""
    for prefix, handler in HANDLERS.items():
        if path.startswith(prefix):
            try:
                if prefix in _JWT_AWARE:
                    return handler.handle(cur, path, method, params, body, jwt_claims=jwt_claims)
                return handler.handle(cur, path, method, params, body)
            except Exception as e:
                logger.error(f"Handler error for {path}: {e}", exc_info=True)
                return {"statusCode": 500, "errorType": "error", "message": "Handler error"}
    return {"statusCode": 404, "errorType": "not_found", "message": "No handler"}
