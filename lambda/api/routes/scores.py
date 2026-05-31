"""Route: scores"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, safe_offset, handle_db_error, check_data_freshness

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
        """Handle /api/scores/* endpoints."""
        try:
            if path in ['/api/scores', '/api/scores/stockscores'] or path.startswith('/api/scores?') or path.startswith('/api/scores/stockscores?'):
                limit_str = params.get('limit', [None])[0] if params else None
                limit = safe_limit(limit_str, max_val=1000, default=1000)
                offset_str = params.get('offset', [None])[0] if params else None
                offset = safe_offset(offset_str)
                sort_by = params.get('sortBy', ['composite_score'])[0] if params else 'composite_score'
                sort_order = params.get('sortOrder', ['desc'])[0] if params else 'desc'
                sp500_only = params.get('sp500Only', ['false'])[0] if params else 'false'
                symbol = params.get('symbol', [None])[0] if params else None

                allowed_sorts = ['composite_score', 'momentum_score', 'quality_score', 'value_score',
                               'growth_score', 'positioning_score', 'stability_score', 'symbol']
                if sort_by not in allowed_sorts:
                    return error_response(400, 'bad_request', f'Sort must be one of: {", ".join(allowed_sorts)}')
                if sort_order not in ['asc', 'desc']:
                    return error_response(400, 'bad_request', 'Sort order must be "asc" or "desc"')

                return _get_stock_scores(cur, limit, offset, sort_by, sort_order, sp500_only == 'true', symbol)
            else:
                return error_response(404, 'not_found', f'No scores handler for {path}')
        except Exception as e:
            logger.warning(f'Scores handler error: {e}')
            return list_response([])

def _get_stock_scores(cur, limit: int = 5000, offset: int = 0, sort_by: str = 'composite_score',
                         sort_order: str = 'desc', sp500_only: bool = False, symbol: str = None) -> Dict:
        """Get stock scores with multi-factor ranking."""
        try:
            cur.execute("SET statement_timeout TO '25s'")
            allowed_sorts = {
                'composite_score': 'sc.composite_score',
                'momentum_score': 'sc.momentum_score',
                'quality_score': 'sc.quality_score',
                'value_score': 'sc.value_score',
                'growth_score': 'sc.growth_score',
                'positioning_score': 'sc.positioning_score',
                'stability_score': 'sc.stability_score',
                'symbol': 'sc.symbol'
            }
            sort_col = allowed_sorts.get(sort_by, 'sc.composite_score')
            sort_direction = 'DESC' if sort_order == 'desc' else 'ASC'

            where_clause = """
            WHERE sc.composite_score > 0
            AND (ss.etf IS NULL OR ss.etf != 'Y')
            """
            params_list = []

            if sp500_only:
                where_clause += " AND ss.is_sp500 = TRUE"
            if symbol:
                where_clause += " AND sc.symbol = %s"
                params_list.append(symbol.upper())

            query = f"""
                WITH price_dates AS (
                    SELECT MAX(date) AS cur_date FROM price_daily
                ),
                latest_prices AS (
                    SELECT pd.symbol, pd.close AS current_close
                    FROM price_daily pd, price_dates
                    WHERE pd.date = price_dates.cur_date
                ),
                prev_prices AS (
                    SELECT pd.symbol, pd.close AS prev_close
                    FROM price_daily pd, price_dates
                    WHERE pd.date = (
                        SELECT MAX(date) FROM price_daily WHERE date < price_dates.cur_date
                    )
                )
                SELECT
                    sc.symbol,
                    ss.security_name AS company_name,
                    cp.sector, cp.industry,
                    sc.composite_score, sc.momentum_score, sc.quality_score,
                    sc.value_score, sc.growth_score, sc.positioning_score, sc.stability_score,
                    sc.updated_at AS last_updated,
                    lp.current_close AS current_price,
                    lp.current_close AS price,
                    ROUND(CASE
                        WHEN pp.prev_close IS NOT NULL THEN ((lp.current_close - pp.prev_close) / NULLIF(pp.prev_close, 0)) * 100
                        ELSE NULL
                    END, 2) AS change_percent,
                    km.market_cap,
                    vm.pe_ratio AS trailing_pe,
                    vm.pb_ratio AS price_to_book,
                    vm.ps_ratio AS ps_ratio_val,
                    vm.peg_ratio AS peg_ratio_val,
                    vm.dividend_yield,
                    qm.roe AS roe_pct,
                    qm.roa AS roa_val,
                    qm.debt_to_equity,
                    qm.current_ratio AS current_ratio_val,
                    qm.quick_ratio AS quick_ratio_val,
                    qm.operating_margin AS operating_margin_val,
                    qm.net_margin AS net_margin_val,
                    gm.revenue_growth_1y AS revenue_growth_yoy_pct,
                    gm.eps_growth_1y AS eps_growth_yoy_pct,
                    gm.revenue_growth_3y AS rev_growth_3y_val,
                    gm.eps_growth_3y AS eps_growth_3y_val,
                    sm.beta AS beta_val,
                    sm.volatility_252d AS volatility_12m_val,
                    pm.institutional_ownership AS inst_own_val,
                    pm.insider_ownership AS insider_own_val,
                    pm.short_interest_percent AS short_pct_val
                FROM stock_scores sc
                JOIN stock_symbols ss ON ss.symbol = sc.symbol
                LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
                LEFT JOIN key_metrics km ON km.symbol = sc.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
                LEFT JOIN stability_metrics sm ON sm.symbol = sc.symbol
                LEFT JOIN positioning_metrics pm ON pm.symbol = sc.symbol
                LEFT JOIN latest_prices lp ON lp.symbol = sc.symbol
                LEFT JOIN prev_prices pp ON pp.symbol = sc.symbol
                {where_clause}
                ORDER BY {sort_col} {sort_direction}
                LIMIT %s OFFSET %s
            """
            params_list.extend([limit, offset])
            cur.execute(query, params_list)
            scores = cur.fetchall()

            def _f(v):
                return float(v) if v is not None else None

            items = []
            for row in scores:
                d = dict(row)
                d['quality_inputs'] = {
                    'return_on_equity_pct': _f(d.get('roe_pct')),
                    'return_on_assets_pct': _f(d.get('roa_val')),
                    'debt_to_equity': _f(d.get('debt_to_equity')),
                    'current_ratio': _f(d.get('current_ratio_val')),
                    'quick_ratio': _f(d.get('quick_ratio_val')),
                    'operating_margin_pct': _f(d.get('operating_margin_val')),
                    'profit_margin_pct': _f(d.get('net_margin_val')),
                }
                d['value_inputs'] = {
                    'stock_pe': _f(d.get('trailing_pe')),
                    'stock_pb': _f(d.get('price_to_book')),
                    'stock_ps': _f(d.get('ps_ratio_val')),
                    'peg_ratio': _f(d.get('peg_ratio_val')),
                    'stock_dividend_yield': _f(d.get('dividend_yield')),
                }
                d['growth_inputs'] = {
                    'revenue_growth_yoy_pct': _f(d.get('revenue_growth_yoy_pct')),
                    'eps_growth_yoy_pct': _f(d.get('eps_growth_yoy_pct')),
                    'revenue_growth_3y_cagr': _f(d.get('rev_growth_3y_val')),
                    'eps_growth_3y_cagr': _f(d.get('eps_growth_3y_val')),
                }
                d['stability_inputs'] = {
                    'beta': _f(d.get('beta_val')),
                    'volatility_12m': _f(d.get('volatility_12m_val')),
                }
                d['positioning_inputs'] = {
                    'institutional_ownership_pct': _f(d.get('inst_own_val')),
                    'insider_ownership_pct': _f(d.get('insider_own_val')),
                    'short_percent_of_float': _f(d.get('short_pct_val')),
                }
                d['momentum_inputs'] = {
                    'current_price': _f(d.get('current_price')),
                }
                items.append(d)

            # Check data freshness
            freshness = check_data_freshness(cur, 'stock_scores', 'updated_at', warning_days=7)

            return list_response(items, data_freshness=freshness)
        except Exception as e:
            logger.warning(f'Stock scores unavailable: {e}')
            return list_response([])

