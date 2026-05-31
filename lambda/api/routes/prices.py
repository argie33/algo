"""Route: prices"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict
import logging
from .utils import error_response, list_response, handle_db_error, safe_limit, check_data_freshness

logger = logging.getLogger(__name__)

_TABLE_MAP = {
    'daily': 'price_daily',
    'weekly': 'price_weekly',
    'monthly': 'price_monthly',
}

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    try:
        parts = path.split('/')
        # /api/prices/history/{symbol}
        if len(parts) >= 5 and parts[3] == 'history':
            symbol = parts[4].upper()
            if not symbol or not all(c.isalnum() or c in ('-', '.', '^') for c in symbol):
                return error_response(400, 'bad_request', 'Invalid symbol')

            limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=2000, default=252)
            timeframe = (params.get('timeframe', [None])[0] if params else None) or 'daily'
            days_str = params.get('days', [None])[0] if params else None

            table_name = _TABLE_MAP.get(timeframe, 'price_daily')

            where_parts = [psycopg2.sql.SQL("symbol = %s")]
            qparams = [symbol]

            if days_str:
                try:
                    days_int = max(1, min(int(days_str), 3650))
                    where_parts.append(psycopg2.sql.SQL("date >= CURRENT_DATE - INTERVAL %s"))
                    qparams.append(f"{days_int} days")
                except ValueError:
                    pass

            query = psycopg2.sql.SQL("""
                SELECT date, open, high, low, close, volume
                FROM {}
                WHERE {}
                ORDER BY date DESC
                LIMIT %s
            """).format(
                psycopg2.sql.Identifier(table_name),
                psycopg2.sql.SQL(" AND ").join(where_parts),
            )
            cur.execute(query, qparams + [limit])
            rows = cur.fetchall()
            freshness = check_data_freshness(cur, table_name, 'date', warning_days=1)
            return list_response([dict(r) for r in rows] if rows else [], data_freshness=freshness)

        return error_response(404, 'not_found', f'No prices handler for {path}')
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'handle prices')
