"""Route: stocks"""
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
        """Handle /api/stocks and /api/stocks/* endpoints."""
        if path == '/api/stocks/deep-value':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=50000, default=50000)
            return _get_deep_value_stocks(limit)
        elif path == '/api/stocks' or path == '/api/stocks/list':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=50000, default=50000)
            symbol_filter = params.get('symbol', [None])[0] if params else None
            industry_filter = params.get('industry', [None])[0] if params else None
            try:
                query = """
                    SELECT ss.symbol, ss.security_name as company_name,
                           cp.sector, cp.industry, ss.is_sp500
                    FROM stock_symbols ss
                    LEFT JOIN company_profile cp ON cp.ticker = ss.symbol
                    WHERE 1=1
                """
                args = []
                if symbol_filter:
                    query += " AND ss.symbol ILIKE %s"
                    args.append(f'%{symbol_filter}%')
                if industry_filter:
                    query += " AND cp.industry = %s"
                    args.append(industry_filter)
                query += " ORDER BY ss.symbol LIMIT %s"
                args.append(limit)
                cur.execute(query, args)
                stocks = cur.fetchall()
                return list_response([dict(s) for s in stocks])
            except psycopg2.errors.UndefinedTable as e:
                logger.error(f'Required table not found: {e}', extra={'operation': 'handle stocks'})
                return error_response(503, 'service_unavailable', 'Data pipeline loading')
            except psycopg2.errors.UndefinedColumn as e:
                logger.error(f'Column not found: {e}', extra={'operation': 'handle stocks'})
                return error_response(503, 'service_unavailable', 'Data schema mismatch')
            except psycopg2.OperationalError as e:
                logger.error(f'Database connection error: {e}', extra={'operation': 'handle stocks'})
                return error_response(503, 'service_unavailable', 'Database unavailable')
            except psycopg2.DatabaseError as e:
                logger.error(f'Database error: {e}', extra={'operation': 'handle stocks', 'error_type': type(e).__name__})
                return error_response(500, 'internal_error', 'Database query failed')
            except Exception as e:
                logger.error(f'Unexpected error: {e}', extra={'operation': 'handle stocks', 'error_type': type(e).__name__})
                return error_response(500, 'internal_error', 'Failed to fetch stocks')
        elif path.startswith('/api/stocks/'):
            symbol = path.split('/api/stocks/')[-1]
            if not _validate_symbol(symbol):
                return error_response(400, 'bad_request', 'Symbol format invalid (1-20 chars, letters/numbers/dash/dot)')
            try:
                cur.execute("""
                    SELECT ss.symbol, ss.security_name as company_name,
                           cp.sector, cp.industry, cp.website, cp.employees,
                           km.market_cap
                    FROM stock_symbols ss
                    LEFT JOIN company_profile cp ON cp.ticker = ss.symbol
                    LEFT JOIN key_metrics km ON km.ticker = ss.symbol
                    WHERE ss.symbol = %s
                """, (symbol.upper(),))
                row = cur.fetchone()
                return json_response(200, dict(row) if row else {})
            except psycopg2.errors.UndefinedTable as e:
                logger.error(f'Required table not found: {e}', extra={'operation': 'handle stocks'})
                return error_response(503, 'service_unavailable', 'Data pipeline loading')
            except psycopg2.errors.UndefinedColumn as e:
                logger.error(f'Column not found: {e}', extra={'operation': 'handle stocks'})
                return error_response(503, 'service_unavailable', 'Data schema mismatch')
            except psycopg2.OperationalError as e:
                logger.error(f'Database connection error: {e}', extra={'operation': 'handle stocks'})
                return error_response(503, 'service_unavailable', 'Database unavailable')
            except psycopg2.DatabaseError as e:
                logger.error(f'Database error: {e}', extra={'operation': 'handle stocks', 'error_type': type(e).__name__})
                return error_response(500, 'internal_error', 'Database query failed')
            except Exception as e:
                logger.error(f'Unexpected error: {e}', extra={'operation': 'handle stocks', 'error_type': type(e).__name__})
                return error_response(500, 'internal_error', 'Failed to fetch stock details')
        else:
            return error_response(404, 'not_found', f'No stocks handler for {path}')

def _get_deep_value_stocks(self, limit: int = 600) -> Dict:
        """Get deep value stock screener data from normalized metric tables."""
        try:
            cur.execute("""
                WITH price_stats AS (
                    SELECT
                        symbol,
                        close AS current_price,
                        MAX(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW) AS high_52w,
                        MAX(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 756 PRECEDING AND CURRENT ROW) AS high_3y,
                        MIN(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW) AS low_52w,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM price_daily
                ),
                latest_prices AS (
                    SELECT * FROM price_stats WHERE rn = 1
                ),
                sector_medians AS (
                    SELECT
                        sc.symbol,
                        vm.pe_ratio,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY vm2.pe_ratio) OVER (PARTITION BY cp.sector) AS sector_median_pe
                    FROM stock_scores sc
                    JOIN value_metrics vm ON vm.symbol = sc.symbol
                    LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
                    LEFT JOIN value_metrics vm2 ON vm2.symbol IN (
                        SELECT cp2.ticker FROM company_profile cp2 WHERE cp2.sector = cp.sector
                    )
                )
                SELECT
                    sc.symbol,
                    ss.security_name AS company_name,
                    cp.sector, cp.industry,
                    lp.current_price,
                    vm.pe_ratio AS trailing_pe,
                    vm.pb_ratio AS price_to_book,
                    vm.ps_ratio AS price_to_sales,
                    vm.peg_ratio,
                    vm.dividend_yield,
                    vm.fcf_yield,
                    vm.ev_to_ebitda,
                    qm.roe AS roe_pct,
                    qm.operating_margin AS op_margin_pct,
                    qm.gross_margin AS gross_margin_pct,
                    qm.net_margin AS net_margin_pct,
                    qm.roa AS roa_pct,
                    qm.debt_to_equity,
                    qm.current_ratio,
                    gm.revenue_growth_1y AS revenue_growth_yoy_pct,
                    gm.eps_growth_1y AS eps_growth_yoy_pct,
                    gm.revenue_growth_3y AS revenue_growth_3y_pct,
                    gm.eps_growth_3y AS eps_growth_3y_pct,
                    gm.fcf_growth_1y AS fcf_growth_yoy_pct,
                    gm.sustainable_growth_rate AS sustainable_growth_pct,
                    lp.high_52w,
                    lp.high_3y,
                    lp.low_52w,
                    COALESCE(ROUND((1 - lp.current_price / NULLIF(lp.high_52w, 0)) * 100, 1), NULL) AS drop_from_52w_high_pct,
                    COALESCE(ROUND((1 - lp.current_price / NULLIF(lp.high_3y, 0)) * 100, 1), NULL) AS drop_from_3y_high_pct,
                    sm.sector_median_pe,
                    (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pe_ratio) FROM value_metrics) AS market_median_pe,
                    COALESCE(ROUND((1 - vm.pe_ratio / NULLIF(sm.sector_median_pe, 0)) * 100, 1), NULL) AS discount_vs_sector_pe_pct,
                    COALESCE(ROUND((1 - vm.pe_ratio / NULLIF((SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pe_ratio) FROM value_metrics), 0)) * 100, 1), NULL) AS discount_vs_market_pe_pct,
                    0 AS intrinsic_value_per_share,
                    0 AS margin_of_safety_pct,
                    0 AS op_margin_trend_pp,
                    0 AS gross_margin_trend_pp,
                    0 AS roe_trend_pp,
                    CASE
                        WHEN qm.roe >= 25 AND qm.operating_margin >= 15 THEN 'tier1'
                        WHEN qm.roe >= 20 AND qm.operating_margin >= 12 THEN 'tier2'
                        ELSE 'other'
                    END AS quality_rank,
                    sc.composite_score,
                    sc.value_score,
                    sc.value_score AS generational_score
                FROM stock_scores sc
                JOIN stock_symbols ss ON ss.symbol = sc.symbol
                LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
                LEFT JOIN latest_prices lp ON lp.symbol = sc.symbol
                LEFT JOIN sector_medians sm ON sm.symbol = sc.symbol
                WHERE sc.value_score > 0
                ORDER BY sc.value_score DESC
                LIMIT %s
            """, (limit,))
            stocks = cur.fetchall()
            return list_response([dict(s) for s in stocks])
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get deep value stocks'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get deep value stocks'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get deep value stocks'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get deep value stocks', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get deep value stocks', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch value stocks')
