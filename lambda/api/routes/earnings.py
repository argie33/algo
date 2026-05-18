"""Route: earnings"""
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

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/earnings/* endpoints. Returns upcoming/past earnings dates."""
        try:
            period = params.get('period', ['upcoming'])[0] if params else 'upcoming'
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=50000, default=50000)
            symbol = params.get('symbol', [None])[0] if params else None

            if period == 'upcoming':
                sql = """
                    SELECT symbol, quarter, earnings_date, eps_estimate, eps_actual, eps_surprise_pct
                    FROM earnings_history
                    WHERE earnings_date >= CURRENT_DATE
                    ORDER BY earnings_date ASC
                    LIMIT %s
                """
                params_tuple = (limit,)
            elif period == 'past':
                sql = """
                    SELECT symbol, quarter, earnings_date, eps_estimate, eps_actual, eps_surprise_pct
                    FROM earnings_history
                    WHERE earnings_date < CURRENT_DATE
                    ORDER BY earnings_date DESC
                    LIMIT %s
                """
                params_tuple = (limit,)
            else:
                return error_response(400, 'bad_request', f'Period must be "upcoming" or "past", got "{period}"')

            if symbol:
                sql = sql.replace('WHERE earnings_date', 'WHERE symbol = %s AND earnings_date')
                params_tuple = (symbol,) + params_tuple

            cur.execute(sql, params_tuple)
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows], total=len(rows))
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'handle earnings'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'handle earnings'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'handle earnings'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'handle earnings', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'handle earnings', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Earnings handler error')
