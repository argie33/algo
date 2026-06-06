"""Route: financials"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict
import logging
from .utils import error_response, list_response, json_response, safe_limit, handle_db_error, check_data_freshness, execute_with_timeout

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
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
            rows = execute_with_timeout(cur, """
                SELECT
                    vm.symbol,
                    CURRENT_DATE AS date,
                    vm.pe_ratio,
                    vm.pb_ratio AS price_to_book,
                    vm.ps_ratio AS price_to_sales,
                    vm.peg_ratio,
                    vm.dividend_yield,
                    vm.fcf_yield,
                    qm.debt_to_equity,
                    qm.roe AS return_on_equity,
                    qm.roa AS return_on_assets,
                    qm.net_margin AS profit_margin,
                    qm.current_ratio,
                    qm.quick_ratio,
                    cp.market_cap,
                    pm.insider_ownership AS held_percent_insiders,
                    pm.institutional_ownership AS held_percent_institutions
                FROM value_metrics vm
                LEFT JOIN quality_metrics qm ON vm.symbol = qm.symbol
                LEFT JOIN company_profile cp ON vm.symbol = cp.ticker
                LEFT JOIN positioning_metrics pm ON vm.symbol = pm.symbol
                WHERE vm.symbol = %s AND vm.symbol IS NOT NULL
                ORDER BY vm.symbol DESC
                LIMIT %s
            """, params=(sym, limit), timeout_sec=5)
            freshness = check_data_freshness(cur, 'value_metrics', 'created_at', warning_days=7)
            return list_response([dict(r) for r in rows] if rows else [], data_freshness=freshness)

        if endpoint == 'income-statement':
            if period == 'quarterly':
                income_query = """
                    SELECT * FROM quarterly_income_statement
                    WHERE symbol = %s ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT %s
                """
            else:
                income_query = """
                    SELECT * FROM annual_income_statement
                    WHERE symbol = %s ORDER BY fiscal_year DESC LIMIT %s
                """
            rows = execute_with_timeout(cur, income_query, params=(sym, limit), timeout_sec=5)
            return list_response([dict(r) for r in rows] if rows else [])

        if endpoint == 'balance-sheet':
            if period == 'quarterly':
                balance_query = """
                    SELECT * FROM quarterly_balance_sheet
                    WHERE symbol = %s ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT %s
                """
            else:
                balance_query = """
                    SELECT * FROM annual_balance_sheet
                    WHERE symbol = %s ORDER BY fiscal_year DESC LIMIT %s
                """
            rows = execute_with_timeout(cur, balance_query, params=(sym, limit), timeout_sec=5)
            return list_response([dict(r) for r in rows] if rows else [])

        if endpoint == 'cash-flow':
            if period == 'quarterly':
                cur.execute(psycopg2.sql.SQL("""
                    SELECT * FROM quarterly_cash_flow
                    WHERE symbol = %s ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT %s
                """), (sym, limit))
            else:
                cur.execute(psycopg2.sql.SQL("""
                    SELECT * FROM annual_cash_flow
                    WHERE symbol = %s ORDER BY fiscal_year DESC LIMIT %s
                """), (sym, limit))
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows] if rows else [])

        return error_response(404, 'not_found', f'No financials handler for {path}')
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        code, error_type, message = handle_db_error(e, 'handle financials')
            return error_response(code, error_type, message)
