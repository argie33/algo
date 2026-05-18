"""Route: stocks"""
import psycopg2, psycopg2.extras, psycopg2.errors
from typing import Dict
import logging
from .utils import error_response, list_response, json_response, safe_limit, safe_offset, handle_db_error

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
    try:
        parts = path.split('/')
        symbol = parts[3] if len(parts) > 3 and parts[3] not in ('deep-value',) else None

        if symbol and path == f'/api/stocks/{symbol}':
            cur.execute("""
                SELECT ss.symbol, ss.security_name as company_name,
                       cp.sector, cp.industry, cp.market_cap, cp.description,
                       cp.website, cp.employees, cp.country, cp.exchange
                FROM stock_symbols ss
                LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
                WHERE ss.symbol = %s
            """, (symbol.upper(),))
            row = cur.fetchone()
            if row:
                return json_response(200, dict(row))
            return error_response(404, 'not_found', f'Stock {symbol} not found')

        if path == '/api/stocks/deep-value':
            limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=1000, default=600)
            cur.execute("""
                SELECT ss.symbol, ss.security_name as company_name,
                       cp.sector, cp.industry, cp.market_cap
                FROM stock_symbols ss
                LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
                WHERE ss.symbol NOT LIKE '^%%'
                ORDER BY ss.symbol
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows])

        limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=50000, default=500)
        offset = safe_offset(params.get('offset', [None])[0] if params else None)
        search = params.get('search', [None])[0] if params else None
        sector = params.get('sector', [None])[0] if params else None

        where_clauses = ["ss.symbol NOT LIKE '^%%'"]
        query_params = []

        if search:
            where_clauses.append("(ss.symbol ILIKE %s OR ss.security_name ILIKE %s)")
            query_params.extend([f'%{search}%', f'%{search}%'])
        if sector:
            where_clauses.append("cp.sector = %s")
            query_params.append(sector)

        where_sql = " AND ".join(where_clauses)
        cur.execute(f"""
            SELECT ss.symbol, ss.security_name as company_name,
                   cp.sector, cp.industry,
                   ss.is_sp500
            FROM stock_symbols ss
            LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
            WHERE {where_sql}
            ORDER BY ss.symbol
            LIMIT %s OFFSET %s
        """, query_params + [limit, offset])
        rows = cur.fetchall()

        cur.execute(f"""
            SELECT COUNT(*) FROM stock_symbols ss
            LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
            WHERE {where_sql}
        """, query_params)
        total = dict(cur.fetchone()).get('count', 0)

        return json_response(200, {
            'items': [dict(r) for r in rows],
            'total': total,
        })
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'handle stocks')
