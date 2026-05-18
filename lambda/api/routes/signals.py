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
        """Get stock trading signals with technical enrichment from normalized tables."""
        try:
            where_clause = "WHERE bsd.date >= CURRENT_DATE - INTERVAL '90 days' AND bsd.signal IN ('BUY', 'SELL')"
            params = [limit]

            if symbol_filter:
                where_clause += " AND bsd.symbol = %s"
                params.insert(0, symbol_filter.upper())  # Insert at beginning for parameter order

            cur.execute(f"""
                SELECT
                    bsd.id, bsd.symbol, bsd.signal, bsd.date,
                    COALESCE(bsd.signal_triggered_date, bsd.date) as signal_triggered_date,
                    bsd.strength, bsd.reason,
                    COALESCE(td.close, 0) as close,
                    COALESCE(td.rsi, 0) as rsi,
                    COALESCE(td.adx, 0) as adx,
                    COALESCE(td.atr, 0) as atr,
                    COALESCE(td.sma_50, 0) as sma_50,
                    COALESCE(td.sma_200, 0) as sma_200,
                    COALESCE(td.ema_12, 0) as ema_12,
                    COALESCE(td.ema_21, 0) as ema_21,
                    COALESCE(td.ema_26, 0) as ema_26,
                    COALESCE(td.mansfield_rs, 0) as mansfield_rs,
                    COALESCE(tt.weinstein_stage::TEXT, 'unknown') as market_stage,
                    COALESCE(tt.trend_direction, 'unknown') as trend,
                    ss.security_name, cp.sector, cp.industry,
                    COALESCE(swg.score, 0) AS swing_score,
                    swg.components->>'grade' AS grade,
                    COALESCE(bsd.base_type, NULL) as base_type,
                    COALESCE(bsd.base_length_days, NULL) as base_length_days,
                    COALESCE(bsd.buylevel, 0) as buylevel,
                    COALESCE(bsd.stoplevel, 0) as stoplevel,
                    COALESCE(bsd.risk_reward_ratio, 0) as risk_reward_ratio,
                    COALESCE(bsd.volume_surge_pct, 0) as volume_surge_pct,
                    COALESCE(bsd.entry_quality_score, 0) as entry_quality_score,
                    COALESCE(bsd.signal_quality_score, 0) as signal_quality_score,
                    COALESCE(bsd.buy_zone_start, 0) as buy_zone_start,
                    COALESCE(bsd.buy_zone_end, 0) as buy_zone_end,
                    COALESCE(bsd.pivot_price, 0) as pivot_price,
                    COALESCE(bsd.initial_stop, 0) as initial_stop,
                    COALESCE(bsd.trailing_stop, 0) as trailing_stop,
                    COALESCE(bsd.position_size_recommendation, NULL) as position_size_recommendation,
                    COALESCE(bsd.profit_target_8pct, 0) as profit_target_8pct,
                    COALESCE(bsd.profit_target_20pct, 0) as profit_target_20pct,
                    COALESCE(bsd.profit_target_25pct, 0) as profit_target_25pct,
                    COALESCE(bsd.exit_trigger_1_price, 0) as exit_trigger_1_price,
                    COALESCE(bsd.exit_trigger_2_price, 0) as exit_trigger_2_price,
                    COALESCE(bsd.sell_level, 0) as sell_level,
                    COALESCE(bsd.rs_rating, 0) as rs_rating,
                    COALESCE(bsd.avg_volume_50d, 0) as avg_volume_50d
                FROM buy_sell_daily bsd
                LEFT JOIN technical_data_daily td ON bsd.symbol = td.symbol
                    AND bsd.date = td.date
                LEFT JOIN trend_template_data tt ON bsd.symbol = tt.symbol
                    AND bsd.date = tt.date
                LEFT JOIN stock_symbols ss ON bsd.symbol = ss.symbol
                LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
                LEFT JOIN swing_trader_scores swg ON bsd.symbol = swg.symbol
                    AND swg.date >= CURRENT_DATE - INTERVAL '1 day'
                {where_clause}
                ORDER BY bsd.date DESC, bsd.symbol ASC
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
                    COALESCE(td.rsi, 0) as rsi,
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

