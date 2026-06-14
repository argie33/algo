"""Route: earnings"""
import psycopg2, psycopg2.extras, psycopg2.errors
from typing import Dict
import logging
from utils.error_handlers import make_error_response
from routes.utils import error_response, list_response, json_response, safe_limit, handle_db_error, check_data_freshness, safe_json_serialize

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    try:
        parts = path.split('/')
        symbol = parts[3] if len(parts) > 3 else None

        if symbol:
            limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=200, default=20)
            cur.execute("SET LOCAL statement_timeout = '3000ms'")
            cur.execute("""
                SELECT symbol,
                       earnings_date AS report_date,
                       CONCAT(fiscal_quarter, 'Q', fiscal_year) AS fiscal_period,
                       eps_actual, eps_estimate,
                       eps_surprise_pct AS eps_surprise,
                       revenue_actual, revenue_estimate,
                       revenue_surprise_pct AS revenue_surprise
                FROM earnings_history
                WHERE symbol = %s
                ORDER BY earnings_date DESC
                LIMIT %s
            """, (symbol.upper(), limit))
            rows = cur.fetchall()
            freshness = check_data_freshness(cur, 'earnings_history', 'earnings_date', warning_days=7)
            return list_response([safe_json_serialize(dict(r)) for r in rows] if rows else [], data_freshness=freshness)

        limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=1000, default=100)
        cur.execute("SET LOCAL statement_timeout = '5000ms'")
        cur.execute("""
            SELECT symbol,
                   earnings_date AS report_date,
                   CONCAT(fiscal_quarter, 'Q', fiscal_year) AS fiscal_period,
                   eps_actual, eps_estimate,
                   eps_surprise_pct AS eps_surprise
            FROM earnings_history
            ORDER BY earnings_date DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        freshness = check_data_freshness(cur, 'earnings_history', 'earnings_date', warning_days=7)
        return list_response([safe_json_serialize(dict(r)) for r in rows] if rows else [], data_freshness=freshness)
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        code, error_type, message = handle_db_error(e, 'handle earnings')
        return error_response(code, error_type, message)
