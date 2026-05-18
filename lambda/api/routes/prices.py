"""Route: prices"""
import psycopg2, psycopg2.extras, psycopg2.errors
from typing import Dict
import logging
from .utils import error_response, list_response, json_response, safe_limit, handle_db_error

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
    try:
        parts = path.split('/')
        # /api/prices/history/{symbol}
        if len(parts) >= 5 and parts[3] == 'history':
            symbol = parts[4]
            limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=2000, default=252)
            timeframe = (params.get('timeframe', [None])[0] if params else None) or 'daily'
            days = params.get('days', [None])[0] if params else None

            if timeframe == 'daily':
                table = 'price_daily'
            elif timeframe == 'weekly':
                table = 'price_weekly'
            elif timeframe == 'monthly':
                table = 'price_monthly'
            else:
                table = 'price_daily'

            where = "symbol = %s"
            qparams = [symbol.upper()]
            if days:
                try:
                    where += f" AND date >= CURRENT_DATE - INTERVAL '{int(days)} days'"
                except ValueError:
                    pass

            cur.execute(f"""
                SELECT date, open, high, low, close, volume
                FROM {table}
                WHERE {where}
                ORDER BY date DESC
                LIMIT %s
            """, qparams + [limit])
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows] if rows else [])

        return error_response(404, 'not_found', f'No prices handler for {path}')
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'handle prices')
