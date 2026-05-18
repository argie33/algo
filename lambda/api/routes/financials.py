"""Route: financials"""
import psycopg2, psycopg2.extras, psycopg2.errors
from typing import Dict
import logging
from .utils import error_response, list_response, json_response, safe_limit, handle_db_error

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
    try:
        parts = path.split('/')
        symbol = parts[3] if len(parts) > 3 else None
        endpoint = parts[4] if len(parts) > 4 else None

        if not symbol:
            return error_response(400, 'bad_request', 'Symbol required')

        sym = symbol.upper()
        period = (params.get('period', [None])[0] if params else None) or 'annual'
        limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=40, default=8)

        if endpoint == 'key-metrics':
            cur.execute("""
                SELECT km.symbol, km.date, km.pe_ratio, km.price_to_book, km.price_to_sales,
                       km.ev_to_ebitda, km.debt_to_equity, km.return_on_equity, km.return_on_assets,
                       km.profit_margin, km.current_ratio, km.quick_ratio
                FROM key_metrics km
                WHERE km.symbol = %s
                ORDER BY km.date DESC
                LIMIT %s
            """, (sym, limit))
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows] if rows else [])

        if endpoint == 'income-statement':
            table = 'income_statement_quarterly' if period == 'quarterly' else 'income_statement_annual'
            cur.execute(f"""
                SELECT * FROM {table} WHERE symbol = %s ORDER BY date DESC LIMIT %s
            """, (sym, limit))
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows] if rows else [])

        if endpoint == 'balance-sheet':
            table = 'balance_sheet_quarterly' if period == 'quarterly' else 'balance_sheet_annual'
            cur.execute(f"""
                SELECT * FROM {table} WHERE symbol = %s ORDER BY date DESC LIMIT %s
            """, (sym, limit))
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows] if rows else [])

        if endpoint == 'cash-flow':
            table = 'cash_flow_quarterly' if period == 'quarterly' else 'cash_flow_annual'
            cur.execute(f"""
                SELECT * FROM {table} WHERE symbol = %s ORDER BY date DESC LIMIT %s
            """, (sym, limit))
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows] if rows else [])

        return error_response(404, 'not_found', f'No financials handler for {path}')
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'handle financials')
