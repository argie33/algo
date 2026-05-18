"""Route: market"""
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

def _handle_market(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/market/* endpoints."""
        try:
            if path == '/api/market/indices':
                return _get_markets()
            elif path == '/api/market/breadth':
                cur.execute("""
                    SELECT date,
                        COUNT(*) as total,
                        SUM(CASE WHEN close > open THEN 1 ELSE 0 END) as advances
                    FROM price_daily
                    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                    GROUP BY date
                    ORDER BY date DESC
                """)
                breadth = cur.fetchall()
                return list_response([dict(b) for b in breadth])
            elif path == '/api/market/technicals':
                cur.execute("""
                    SELECT date, advance_decline_ratio, new_highs_count, new_lows_count,
                           up_volume_percent, distribution_days_4w, breadth_momentum_10d,
                           vix_level, put_call_ratio, market_trend, market_stage
                    FROM market_health_daily
                    ORDER BY date DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                return json_response(200, dict(row) if row else {})
            elif path == '/api/market/top-movers':
                cur.execute("""
                    WITH today AS (
                        SELECT symbol, close
                        FROM price_daily
                        WHERE date = (SELECT MAX(date) FROM price_daily)
                    ),
                    yesterday AS (
                        SELECT symbol, close
                        FROM price_daily
                        WHERE date = (
                            SELECT MAX(date) FROM price_daily
                            WHERE date < (SELECT MAX(date) FROM price_daily)
                        )
                    )
                    SELECT t.symbol, ss.security_name,
                           ROUND(((t.close - y.close) / NULLIF(y.close, 0) * 100)::numeric, 2) as pct_change
                    FROM today t
                    JOIN yesterday y ON t.symbol = y.symbol
                    LEFT JOIN stock_symbols ss ON t.symbol = ss.symbol
                    WHERE y.close > 0
                    ORDER BY ABS(t.close - y.close) / y.close DESC
                    LIMIT 20
                """)
                movers = cur.fetchall()
                return list_response([dict(m) for m in movers] if movers else [])
            elif path == '/api/market/distribution-days':
                cur.execute("""
                    SELECT symbol, date, distribution_count
                    FROM distribution_days
                    ORDER BY date DESC
                    LIMIT 50
                """)
                dist = cur.fetchall()
                return list_response([dict(d) for d in dist] if dist else [])
            elif path == '/api/market/seasonality':
                # Seasonality tables are market-wide aggregates (SPY-based), no per-symbol filtering
                cur.execute("""
                    SELECT month, month_name, avg_return, best_return, worst_return,
                           winning_years, losing_years, years_counted
                    FROM seasonality_monthly_stats
                    ORDER BY month
                """)
                monthly = cur.fetchall()
                cur.execute("""
                    SELECT day, day_num, avg_return, win_rate, days_counted
                    FROM seasonality_day_of_week
                    ORDER BY day_num
                """)
                dow = cur.fetchall()
                return json_response(200, {
                    'monthly': [dict(r) for r in monthly],
                    'day_of_week': [dict(r) for r in dow],
                })
            elif path == '/api/market/sentiment':
                range_days = _parse_range_param(params) if params else 30
                cur.execute("""
                    SELECT date, fear_greed_value as value
                    FROM fear_greed_index
                    WHERE date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                    ORDER BY date DESC
                """, (range_days,))
                sentiment = cur.fetchall()
                return list_response([dict(s) for s in sentiment] if sentiment else [])
            elif path == '/api/market/fear-greed':
                range_days = _parse_range_param(params) if params else 30
                return _get_fear_greed_history(range_days)
            elif path == '/api/market/status':
                cur.execute("""
                    SELECT date, market_trend, market_stage, advance_decline_ratio,
                           new_highs_count, new_lows_count, vix_level, put_call_ratio,
                           distribution_days_4w
                    FROM market_health_daily
                    ORDER BY date DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                return json_response(200, dict(row) if row else {})
            elif path == '/api/market/naaim':
                cur.execute("""
                    SELECT date, naaim_number_mean, bullish, bearish
                    FROM naaim
                    ORDER BY date DESC
                    LIMIT 52
                """)
                rows = cur.fetchall()
                if rows:
                    current = rows[0][1]  # naaim_number_mean from most recent row
                    history = [{'date': dict(r)['date'], 'naaim_number_mean': dict(r)['naaim_number_mean']} for r in rows]
                    return json_response(200, {'current': current, 'history': history})
                else:
                    return json_response(200, {'current': None, 'history': []})
            elif path == '/api/market/latest':
                return _get_market_latest()
            elif path == '/api/market/cap-distribution':
                return json_response(501, {'status': 'not_implemented', 'message': 'Market cap distribution requires data aggregation'})
            elif path == '/api/market/correlation':
                return json_response(501, {'status': 'not_implemented', 'message': 'Correlation matrix requires additional computation'})
            return error_response(404, 'not_found', f'No market handler for {path}')
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'handle market'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'handle market'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'handle market'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'handle market', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'handle market', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch market data')
def _get_fear_greed_history(self, days: int = 30) -> Dict:
        """Get fear/greed index history."""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            cur.execute("""
                SELECT date, fear_greed_value as value, fear_greed_label as label
                FROM fear_greed_index
                WHERE date >= %s
                ORDER BY date DESC
            """, (cutoff_date,))
            history = cur.fetchall()
            return list_response([dict(h) for h in history] if history else [])
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get fear greed history'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get fear greed history'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get fear greed history'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get fear greed history', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get fear greed history', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch sentiment history')
def _get_market_latest(self) -> Dict:
        """Get latest market data including indices, breadth, and sentiment."""
        try:
            cur.execute("""
                SELECT date, market_trend, market_stage, advance_decline_ratio,
                       new_highs_count, new_lows_count, vix_level, put_call_ratio,
                       distribution_days_4w, up_volume_percent, breadth_momentum_10d
                FROM market_health_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            market_row = cur.fetchone()

            cur.execute("""
                SELECT date, fear_greed_value, fear_greed_label
                FROM fear_greed_index
                ORDER BY date DESC
                LIMIT 1
            """)
            sentiment_row = cur.fetchone()

            cur.execute("""
                SELECT symbol, close
                FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                ORDER BY symbol
                LIMIT 10
            """)
            recent_prices = cur.fetchall()

            result = {}
            if market_row:
                result['market'] = dict(market_row)
            if sentiment_row:
                result['sentiment'] = dict(sentiment_row)
            if recent_prices:
                result['prices'] = [dict(p) for p in recent_prices]

            return json_response(200, result if result else {})
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get market latest'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get market latest'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get market latest'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get market latest', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get market latest', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch market latest')
