"""Route: financials"""
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
        """Handle /api/financials/{symbol}/* endpoints."""
        try:
            parts = path.split('/')
            if len(parts) < 4:
                return error_response(400, 'bad_request', 'Path must include symbol: /api/financials/{symbol}/{endpoint}')
            symbol = parts[3].upper()
            endpoint = parts[4] if len(parts) > 4 else None
            if not endpoint:
                return error_response(400, 'bad_request', 'Path must include endpoint (income-statement, balance-sheet, cash-flow, key-metrics)')
            period = params.get('period', ['annual'])[0] if params else 'annual'

            if endpoint == 'income-statement':
                if period == 'quarterly':
                    cur.execute("""
                        SELECT fiscal_year, fiscal_quarter, revenue, net_income, earnings_per_share
                        FROM quarterly_income_statement WHERE symbol = %s
                        ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT 12
                    """, (symbol,))
                else:
                    cur.execute("""
                        SELECT fiscal_year, revenue, cost_of_revenue, gross_profit,
                               operating_income, net_income, earnings_per_share
                        FROM annual_income_statement WHERE symbol = %s
                        ORDER BY fiscal_year DESC LIMIT 5
                    """, (symbol,))
                rows = cur.fetchall()
                return list_response([dict(r) for r in rows])

            elif endpoint == 'balance-sheet':
                if period == 'quarterly':
                    cur.execute("""
                        SELECT fiscal_year, fiscal_quarter, total_assets,
                               total_liabilities, stockholders_equity
                        FROM quarterly_balance_sheet WHERE symbol = %s
                        ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT 12
                    """, (symbol,))
                else:
                    cur.execute("""
                        SELECT fiscal_year, total_assets, current_assets,
                               total_liabilities, stockholders_equity
                        FROM annual_balance_sheet WHERE symbol = %s
                        ORDER BY fiscal_year DESC LIMIT 5
                    """, (symbol,))
                rows = cur.fetchall()
                return list_response([dict(r) for r in rows])

            elif endpoint == 'cash-flow':
                if period == 'quarterly':
                    cur.execute("""
                        SELECT fiscal_year, fiscal_quarter, operating_cash_flow, free_cash_flow
                        FROM quarterly_cash_flow WHERE symbol = %s
                        ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT 12
                    """, (symbol,))
                else:
                    cur.execute("""
                        SELECT fiscal_year, operating_cash_flow, investing_cash_flow,
                               financing_cash_flow, free_cash_flow
                        FROM annual_cash_flow WHERE symbol = %s
                        ORDER BY fiscal_year DESC LIMIT 5
                    """, (symbol,))
                rows = cur.fetchall()
                return list_response([dict(r) for r in rows])

            elif endpoint == 'key-metrics':
                cur.execute("""
                    SELECT km.market_cap, km.held_percent_insiders, km.held_percent_institutions,
                           cp.sector, cp.industry, cp.company_name
                    FROM key_metrics km
                    LEFT JOIN company_profile cp ON cp.ticker = km.ticker
                    WHERE km.ticker = %s
                """, (symbol,))
                row = cur.fetchone()
                if not row:
                    return json_response(200, {'metricsData': {}})
                r = dict(row)
                # Transform flat response into nested structure expected by frontend
                metrics_data = {
                    'Company Info': {
                        'metrics': {
                            'Name': r.get('company_name'),
                            'Sector': r.get('sector'),
                            'Industry': r.get('industry'),
                        }
                    },
                    'Valuation': {
                        'metrics': {
                            'Market Cap': r.get('market_cap'),
                        }
                    },
                    'Ownership': {
                        'metrics': {
                            'Insider Ownership %': r.get('held_percent_insiders'),
                            'Institutional Ownership %': r.get('held_percent_institutions'),
                        }
                    }
                }
                return json_response(200, {'metricsData': metrics_data})

            return error_response(400, 'bad_request', f'Unknown financial endpoint: {endpoint}. Valid: income-statement, balance-sheet, cash-flow, key-metrics')
        except psycopg2.errors.UndefinedTable as e:
            logger.warning(f"financials: table not found - {str(e)[:100]}")
            return error_response(503, 'service_unavailable', 'Financial data not yet loaded. Check data pipeline status.')
        except psycopg2.errors.UndefinedColumn as e:
            logger.warning(f"financials: column not found - {str(e)[:100]}")
            return error_response(503, 'service_unavailable', 'Financial data schema outdated. Contact administrator.')
        except psycopg2.DatabaseError as e:
            logger.error(f"financials handler database error: {e}", exc_info=True)
            return error_response(503, 'service_unavailable', 'Temporary database issue. Please retry.')
        except Exception as e:
            logger.error(f"financials handler error: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Financials handler error')

