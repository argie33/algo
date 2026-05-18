"""Route: earnings"""
import psycopg2, psycopg2.extras, psycopg2.errors
from typing import Dict
import logging
from .utils import error_response, list_response, json_response, safe_limit, handle_db_error

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
    try:
        parts = path.split('/')
        symbol = parts[3] if len(parts) > 3 else None

        if symbol:
            limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=200, default=20)
            cur.execute("""
                SELECT symbol, report_date, fiscal_period, eps_actual, eps_estimate,
                       eps_surprise, revenue_actual, revenue_estimate, revenue_surprise
                FROM earnings_history
                WHERE symbol = %s
                ORDER BY report_date DESC
                LIMIT %s
            """, (symbol.upper(), limit))
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows] if rows else [])

        limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=1000, default=100)
        cur.execute("""
            SELECT symbol, report_date, fiscal_period, eps_actual, eps_estimate, eps_surprise
            FROM earnings_history
            ORDER BY report_date DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        return list_response([dict(r) for r in rows] if rows else [])
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'handle earnings')
