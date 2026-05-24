"""Route: signals"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, handle_db_error

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/signals/* endpoints."""
        if path in ['/api/signals', '/api/signals/stocks'] or path.startswith('/api/signals?') or path.startswith('/api/signals/stocks?'):
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=50000, default=50000)
            timeframe = params.get('timeframe', ['daily'])[0] if params else 'daily'
            symbol_filter = params.get('symbol', [None])[0] if params else None
            return _get_signals_stocks(cur, limit, timeframe, symbol_filter)
        elif path == '/api/signals/etf':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=50000, default=50000)
            return _get_signals_etf(cur, limit)
        else:
            return error_response(404, 'not_found', f'No signals handler for {path}')

def _get_signals_stocks(cur, limit: int = 500, timeframe: str = 'daily', symbol_filter: Optional[str] = None) -> Dict:
        """Get stock trading signals with all available technical and analytical data."""
        try:
            where_clause = "WHERE bsd.date >= CURRENT_DATE - INTERVAL '90 days' AND LOWER(bsd.signal) IN ('buy', 'sell')"
            params = [limit]

            if symbol_filter:
                where_clause += " AND bsd.symbol = %s"
                params.insert(0, symbol_filter.upper())

            cur.execute("""
                SELECT
                    bsd.id, bsd.symbol, bsd.signal, bsd.date,
                    bsd.entry_quality_score, bsd.signal_quality_score,
                    bsd.entry_price, bsd.close, bsd.rsi, bsd.adx,
                    bsd.sma_50, bsd.sma_200, bsd.mansfield_rs,
                    bsd.base_type, bsd.base_length_days, bsd.breakout_quality,
                    bsd.risk_reward_ratio, bsd.risk_pct,
                    bsd.stage_number, bsd.substage, bsd.market_stage,
                    bsd.rs_rating, bsd.volume, bsd.avg_volume_50d,
                    bsd.reason, bsd.updated_at
                FROM buy_sell_daily bsd
                """ + where_clause + """
                ORDER BY bsd.date DESC, bsd.entry_quality_score DESC, bsd.symbol ASC
                LIMIT %s
            """, tuple(params))
            signals = cur.fetchall()
            return json_response(200, {'items': [dict(s) for s in signals]})
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'fetch stock signals')

def _get_signals_etf(cur, limit: int = 500) -> Dict:
        """Get ETF trading signals."""
        try:
            cur.execute("""
                SELECT
                    bsd.id, bsd.symbol, bsd.signal, bsd.date,
                    bsd.strength, NULL as reason,
                    COALESCE(td.close, 0) as close,
                    COALESCE(td.rsi_14, 0) as rsi,
                    COALESCE(td.sma_50, 0) as sma_50,
                    COALESCE(td.sma_200, 0) as sma_200,
                    COALESCE(tt.weinstein_stage::TEXT, 'unknown') as market_stage,
                    COALESCE(cp.short_name, cp.long_name, bsd.symbol) as company_name
                FROM buy_sell_daily_etf bsd
                LEFT JOIN technical_data_daily td ON bsd.symbol = td.symbol
                    AND bsd.date = td.date
                LEFT JOIN trend_template_data tt ON bsd.symbol = tt.symbol
                    AND bsd.date = tt.date
                LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
                WHERE bsd.date >= CURRENT_DATE - INTERVAL '90 days'
                AND bsd.symbol IN ('SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EFA')
                ORDER BY bsd.date DESC
                LIMIT %s
            """, (limit,))
            signals = cur.fetchall()
            return list_response([dict(s) for s in signals])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'fetch ETF signals')

