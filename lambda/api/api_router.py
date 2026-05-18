"""API Router - dispatcher."""
import logging, psycopg2
from typing import Dict, Any, Optional
from routes import (algo, financials, earnings, signals, prices, stocks,
                     sectors, industries, market, economic, sentiment,
                     scores, research, audit, trades, admin)

logger = logging.getLogger(__name__)

HANDLERS = {
    '/api/algo': algo, '/api/financials': financials, '/api/earnings': earnings,
    '/api/signals': signals, '/api/prices': prices, '/api/stocks': stocks,
    '/api/sectors': sectors, '/api/industries': industries,
    '/api/market': market, '/api/economic': economic, '/api/sentiment': sentiment,
    '/api/scores': scores, '/api/research': research, '/api/audit': audit,
    '/api/trades': trades, '/api/admin': admin,
}

def route_request(cur, path, method, params, body=None):
    """Route request to handler."""
    for prefix, handler in HANDLERS.items():
        if path.startswith(prefix):
            try:
                return handler.handle(cur, path, method, params, body)
            except Exception as e:
                logger.error(f"Error: {e}", exc_info=True)
                return {"statusCode": 500, "errorType": "error", "message": "Handler error"}
    return {"statusCode": 404, "errorType": "not_found", "message": "No handler"}
