"""Route: prices"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone

logger = logging.getLogger(__name__)

def error_response(code, typ, msg):
    return {"statusCode": code, "errorType": typ, "message": msg}

def success_response(data):
    return {"statusCode": 200, "data": data}

def list_response(items, total=None):
    return {"statusCode": 200, "items": items, "total": total or len(items)}

def _safe_limit(limit_str, max_val=50000, default=500):
    if not limit_str:
        return default
    try:
        return min(int(limit_str), max_val)
    except:
        return default

def _handle_prices(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/prices/* endpoints."""
        match = re.match(r'/api/prices/history/([A-Z0-9.]+)', path)
        if match:
            symbol = match.group(1)
            timeframe = params.get('timeframe', ['daily'])[0] if params else 'daily'
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=50000, default=50000)
            return _get_price_history(symbol, timeframe, limit)
        else:
            return error_response(404, 'not_found', f'Invalid prices endpoint: {path}')

def _get_price_history(self, symbol: str, timeframe: str = 'daily', limit: int = 60) -> Dict:
        """Get price history for a symbol."""
        if not _validate_symbol(symbol):
            return error_response(400, 'bad_request', 'Symbol format invalid (1-20 chars, letters/numbers/dash/dot)')
        try:
            cur.execute("""
                SELECT date, open, high, low, close, volume
                FROM price_daily
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT %s
            """, (symbol.upper(), limit))
            prices = cur.fetchall()
            return list_response([dict(p) for p in reversed(prices)])
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found (price history): {e}', extra={'operation': 'fetch price history', 'symbol': symbol})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found (price history): {e}', extra={'operation': 'fetch price history', 'symbol': symbol})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error (price history): {e}', extra={'operation': 'fetch price history', 'symbol': symbol})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error (price history): {e}', extra={'operation': 'fetch price history', 'symbol': symbol, 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error (price history): {e}', extra={'operation': 'fetch price history', 'symbol': symbol, 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch price history')

