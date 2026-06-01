"""Route: signals"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, handle_db_error, check_data_freshness

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
        """Handle /api/signals/* endpoints."""
        if not params:
            params = {}
        if path in ['/api/signals', '/api/signals/stocks'] or path.startswith('/api/signals?') or path.startswith('/api/signals/stocks?'):
            limit_list = params.get('limit', [])
            limit_str = limit_list[0] if limit_list else None
            limit = safe_limit(limit_str, max_val=50000, default=500)
            timeframe_list = params.get('timeframe', [])
            timeframe = timeframe_list[0] if timeframe_list else 'daily'
            symbol_list = params.get('symbol', [])
            symbol_filter = symbol_list[0] if symbol_list else None
            return _get_signals_stocks(cur, limit, timeframe, symbol_filter)
        elif path == '/api/signals/etf':
            limit_list = params.get('limit', [])
            limit_str = limit_list[0] if limit_list else None
            limit = safe_limit(limit_str, max_val=50000, default=500)
            return _get_signals_etf(cur, limit)
        else:
            return error_response(404, 'not_found', f'No signals handler for {path}')

def _get_signals_stocks(cur, limit: int = 500, timeframe: str = 'daily', symbol_filter: Optional[str] = None) -> Dict:
        """Get stock trading signals with all available technical and analytical data."""
        try:
            # SECURITY L-05: Validate timeframe parameter (currently only 'daily' supported)
            VALID_TIMEFRAMES = {'daily'}
            if timeframe.lower() not in VALID_TIMEFRAMES:
                return error_response(400, 'bad_request', f'Unsupported timeframe: {timeframe}. Only "daily" is currently supported.')

            cur.execute("SET statement_timeout TO '25s'")
            where_clause = "WHERE bsd.date >= CURRENT_DATE - INTERVAL '90 days' AND LOWER(bsd.signal) IN ('buy', 'sell')"
            params = [limit]

            if symbol_filter:
                # Validate symbol format before use
                # Only alphanumeric and common separators allowed
                import re
                if not re.match(r'^[A-Z0-9\-\^]{1,10}$', symbol_filter.upper()):
                    return error_response(400, 'bad_request', 'Invalid symbol format')
                where_clause += " AND bsd.symbol = %s"
                params.insert(0, symbol_filter.upper())

            cur.execute("""
                SELECT
                    bsd.id, bsd.symbol, bsd.signal, bsd.date,
                    bsd.timeframe, bsd.signal_type, bsd.strength,
                    bsd.entry_quality_score,
                    COALESCE(sqs.composite_sqs, bsd.signal_quality_score) AS signal_quality_score,
                    bsd.volume_surge_pct, bsd.risk_reward_ratio,
                    bsd.rsi, bsd.sma_50, bsd.sma_200, bsd.ema_21,
                    bsd.atr, bsd.adx, COALESCE(bsd.mansfield_rs, 0) as mansfield_rs,
                    bsd.rs_rating, bsd.breakout_quality, bsd.risk_pct,
                    bsd.current_gain_pct, bsd.days_in_position,
                    bsd.position_size_recommendation,
                    bsd.stage_number, bsd.reason, bsd.substage,
                    bsd.close, bsd.volume, bsd.base_type, bsd.base_length_days,
                    bsd.market_stage, bsd.buylevel, bsd.stoplevel,
                    bsd.signal_triggered_date, bsd.entry_price,
                    bsd.buy_zone_start, bsd.buy_zone_end,
                    bsd.pivot_price, bsd.initial_stop, bsd.trailing_stop,
                    bsd.sell_level,
                    bsd.profit_target_8pct, bsd.profit_target_20pct, bsd.profit_target_25pct,
                    bsd.exit_trigger_1_price, bsd.exit_trigger_2_price,
                    bsd.avg_volume_50d,
                    cp.sector, cp.industry
                FROM buy_sell_daily bsd
                LEFT JOIN company_profile cp ON cp.ticker = bsd.symbol
                LEFT JOIN LATERAL (
                    SELECT composite_sqs
                    FROM signal_quality_scores
                    WHERE symbol = bsd.symbol
                    ORDER BY date DESC
                    LIMIT 1
                ) sqs ON true
                """ + where_clause + """
                ORDER BY bsd.date DESC, COALESCE(sqs.composite_sqs, bsd.signal_quality_score, 0) DESC, bsd.symbol ASC
                LIMIT %s
            """, tuple(params))
            signals = cur.fetchall()

            # Check data freshness
            freshness = check_data_freshness(cur, 'buy_sell_daily', 'date', warning_days=1)

            return list_response([dict(s) for s in signals], data_freshness=freshness)
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

