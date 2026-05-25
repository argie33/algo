"""Route: scores"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, safe_offset, handle_db_error

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/scores/* endpoints."""
        if path in ['/api/scores', '/api/scores/stockscores'] or path.startswith('/api/scores?') or path.startswith('/api/scores/stockscores?'):
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=50000, default=50000)
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

def _get_stock_scores(cur, limit: int = 5000, offset: int = 0, sort_by: str = 'composite_score',
                         sort_order: str = 'desc', sp500_only: bool = False, symbol: str = None) -> Dict:
        """Get stock scores with multi-factor ranking."""
        try:
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
            """
            params_list = []

            if sp500_only:
                where_clause += " AND ss.is_sp500 = TRUE"
            if symbol:
                where_clause += " AND sc.symbol = %s"
                params_list.append(symbol.upper())

            query = f"""
                SELECT
                    sc.symbol,
                    ss.security_name AS company_name,
                    cp.sector, cp.industry,
                    sc.composite_score, sc.momentum_score, sc.quality_score,
                    sc.value_score, sc.growth_score, sc.positioning_score, sc.stability_score,
                    pd.current_close AS current_price,
                    pd.current_close AS price,
                    ROUND(CASE
                        WHEN pd.prev_close IS NOT NULL THEN ((pd.current_close - pd.prev_close) / NULLIF(pd.prev_close, 0)) * 100
                        ELSE NULL
                    END, 2) AS change_percent,
                    km.market_cap,
                    vm.pe_ratio AS trailing_pe,
                    vm.pb_ratio AS price_to_book,
                    qm.roe AS roe_pct,
                    qm.debt_to_equity,
                    vm.dividend_yield,
                    gm.revenue_growth_1y AS revenue_growth_yoy_pct,
                    gm.eps_growth_1y AS eps_growth_yoy_pct
                FROM stock_scores sc
                JOIN stock_symbols ss ON ss.symbol = sc.symbol
                LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
                LEFT JOIN key_metrics km ON km.symbol = sc.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
                LEFT JOIN LATERAL (
                    SELECT
                        (SELECT close FROM price_daily p1
                         WHERE p1.symbol = sc.symbol ORDER BY p1.date DESC LIMIT 1) AS current_close,
                        (SELECT close FROM price_daily p2
                         WHERE p2.symbol = sc.symbol ORDER BY p2.date DESC LIMIT 1 OFFSET 1) AS prev_close
                ) pd ON true
                {where_clause}
                ORDER BY {sort_col} {sort_direction}
                LIMIT %s OFFSET %s
            """
            params_list.extend([limit, offset])
            cur.execute(query, params_list)
            scores = cur.fetchall()
            return list_response([dict(s) for s in scores])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'get stock scores')



