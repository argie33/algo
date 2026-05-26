"""Route: market"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, handle_db_error

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/market/* endpoints."""
        try:
            if path in ['/api/market', '/api/market/status'] or path.startswith('/api/market?'):
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
            elif path == '/api/market/indices':
                return _get_markets(cur)
            elif path == '/api/market/breadth':
                cur.execute("""
                    WITH daily AS (
                        SELECT symbol, date, close,
                               LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS prev_close
                        FROM price_daily
                        WHERE date >= CURRENT_DATE - INTERVAL '31 days'
                          AND symbol NOT LIKE '^%%'
                    )
                    SELECT date,
                        COUNT(*) AS total,
                        SUM(CASE WHEN close > prev_close THEN 1 ELSE 0 END) AS advances
                    FROM daily
                    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                      AND prev_close IS NOT NULL
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
                base = dict(row) if row else {}
                # Compute today's advancing/declining counts from price_daily.
                # Compare close to previous day's close (traditional A/D breadth),
                # not close to open (intraday direction, which is a different measure).
                try:
                    cur.execute("""
                        WITH latest AS (SELECT MAX(date) AS d FROM price_daily),
                             prev_day AS (
                                 SELECT MAX(date) AS d FROM price_daily
                                 WHERE date < (SELECT d FROM latest)
                             ),
                             today AS (
                                 SELECT symbol, close FROM price_daily
                                 WHERE date = (SELECT d FROM latest)
                                   AND symbol NOT LIKE '^%%'
                             ),
                             yesterday AS (
                                 SELECT symbol, close FROM price_daily
                                 WHERE date = (SELECT d FROM prev_day)
                                   AND symbol NOT LIKE '^%%'
                             )
                        SELECT
                            COUNT(*) FILTER (WHERE t.close > y.close) AS advancing,
                            COUNT(*) FILTER (WHERE t.close < y.close) AS declining,
                            COUNT(*) FILTER (WHERE t.close = y.close) AS unchanged,
                            COUNT(t.symbol) AS total_stocks
                        FROM today t
                        JOIN yesterday y ON t.symbol = y.symbol
                    """)
                    brow = cur.fetchone()
                    base['breadth'] = dict(brow) if brow else {}
                except Exception:
                    base['breadth'] = {}
                # Build 30-day McClellan Oscillator history from market_exposure_daily.
                # The factors JSONB column stores the true McClellan value (19-EMA minus
                # 39-EMA of net advances) computed by algo_market_exposure._mcclellan().
                try:
                    cur.execute("""
                        SELECT date,
                               (factors->'mcclellan'->>'value')::float AS advance_decline_line
                        FROM market_exposure_daily
                        WHERE date >= CURRENT_DATE - INTERVAL '35 days'
                          AND factors IS NOT NULL
                          AND factors->'mcclellan' IS NOT NULL
                          AND (factors->'mcclellan'->>'value') IS NOT NULL
                        ORDER BY date DESC
                        LIMIT 30
                    """)
                    adrows = cur.fetchall()
                    base['mcclellan_oscillator'] = [dict(r) for r in adrows]
                except Exception:
                    base['mcclellan_oscillator'] = []
                return json_response(200, base)
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
                    LIMIT 40
                """)
                movers = cur.fetchall()
                items = [dict(m) for m in movers] if movers else []
                gainers = sorted([m for m in items if (m.get('pct_change') or 0) >= 0],
                                 key=lambda x: -(x.get('pct_change') or 0))[:10]
                losers = sorted([m for m in items if (m.get('pct_change') or 0) < 0],
                                key=lambda x: (x.get('pct_change') or 0))[:10]
                return json_response(200, {'gainers': gainers, 'losers': losers})
            elif path == '/api/market/distribution-days':
                INDEX_NAMES = {'^GSPC': 'S&P 500', '^IXIC': 'Nasdaq Composite', '^NYA': 'NYSE Composite', '^DJI': 'Dow Jones'}
                try:
                    cur.execute("""
                        WITH sessions AS (
                            SELECT symbol, date,
                                   close,
                                   LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS prev_close,
                                   volume,
                                   AVG(volume) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 50 PRECEDING AND 1 PRECEDING) AS avg_vol,
                                   (CURRENT_DATE - date)::INTEGER AS days_ago
                            FROM price_daily
                            WHERE symbol IN ('^GSPC', '^IXIC', '^NYA', '^DJI')
                              AND date >= CURRENT_DATE - INTERVAL '65 days'
                        )
                        SELECT symbol, date, days_ago,
                               ROUND(((close - prev_close) / NULLIF(prev_close, 0) * 100)::NUMERIC, 2) AS change_pct,
                               ROUND((volume::NUMERIC / NULLIF(avg_vol, 0))::NUMERIC, 2) AS volume_ratio
                        FROM sessions
                        WHERE prev_close IS NOT NULL
                          AND close < prev_close * 0.998
                          AND (avg_vol IS NULL OR volume > avg_vol * 1.01)
                          AND date >= CURRENT_DATE - INTERVAL '35 days'
                        ORDER BY symbol, date DESC
                    """)
                    rows = cur.fetchall()
                    by_sym = {}
                    for row in rows:
                        r = dict(row)
                        sym = r['symbol']
                        if sym not in by_sym:
                            by_sym[sym] = []
                        by_sym[sym].append({
                            'date': str(r['date']),
                            'change_pct': float(r['change_pct']) if r['change_pct'] is not None else None,
                            'volume_ratio': float(r['volume_ratio']) if r['volume_ratio'] is not None else None,
                            'days_ago': r['days_ago'],
                        })
                    result = {}
                    for sym, days in by_sym.items():
                        count = len(days)
                        signal = ('DANGER' if count >= 5 else
                                  'CAUTION' if count >= 3 else
                                  'WATCH' if count >= 1 else 'NORMAL')
                        result[sym] = {'name': INDEX_NAMES.get(sym, sym), 'count': count, 'signal': signal, 'days': days}
                    return json_response(200, result)
                except Exception as e:
                    return handle_db_error(e, logger, 'get distribution days')
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
                # AAII investor sentiment
                try:
                    cur.execute("""
                        SELECT date, bullish, neutral, bearish
                        FROM aaii_sentiment
                        WHERE date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                        ORDER BY date DESC
                    """, (range_days,))
                    aaii_rows = [dict(r) for r in cur.fetchall()]
                except Exception:
                    aaii_rows = []
                # NAAIM manager exposure
                try:
                    cur.execute("""
                        SELECT date, naaim_number_mean, bullish, bearish
                        FROM naaim
                        ORDER BY date DESC
                        LIMIT 4
                    """)
                    naaim_rows = cur.fetchall()
                    naaim_current = float(dict(naaim_rows[0])['naaim_number_mean']) if naaim_rows else None
                except Exception:
                    naaim_current = None
                # Fear & Greed
                try:
                    cur.execute("""
                        SELECT date, fear_greed_value as value, fear_greed_label as label
                        FROM fear_greed_index
                        WHERE date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                        ORDER BY date DESC
                    """, (range_days,))
                    fg_rows = [dict(r) for r in cur.fetchall()]
                    fg_current = fg_rows[0] if fg_rows else None
                except Exception:
                    fg_rows = []
                    fg_current = None
                return json_response(200, {
                    'aaii': aaii_rows,
                    'naaim': {'exposure': naaim_current, 'current': naaim_current},
                    'fearGreed': {
                        'value': fg_current.get('value') if fg_current else None,
                        'label': fg_current.get('label') if fg_current else None,
                        'history': fg_rows,
                    },
                })
            elif path == '/api/market/fear-greed':
                range_days = _parse_range_param(params) if params else 30
                return _get_fear_greed_history(cur, range_days)
            elif path == '/api/market/naaim':
                cur.execute("""
                    SELECT date, naaim_number_mean, bullish, bearish
                    FROM naaim
                    ORDER BY date DESC
                    LIMIT 52
                """)
                rows = cur.fetchall()
                if rows:
                    current = dict(rows[0]).get('naaim_number_mean')
                    history = [{'date': str(dict(r)['date']), 'naaim_number_mean': dict(r)['naaim_number_mean']} for r in rows]
                    return json_response(200, {'current': current, 'history': history})
                else:
                    return json_response(200, {'current': None, 'history': []})
            elif path == '/api/market/latest':
                return _get_market_latest(cur)
            elif path == '/api/market/cap-distribution':
                return json_response(501, {'status': 'not_implemented', 'message': 'Market cap distribution requires data aggregation'})
            elif path == '/api/market/correlation':
                return json_response(501, {'status': 'not_implemented', 'message': 'Correlation matrix requires additional computation'})
            return error_response(404, 'not_found', f'No market handler for {path}')
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'handle market')
def _get_fear_greed_history(cur, days: int = 30) -> Dict:
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
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'get fear greed history')
def _get_market_latest(cur) -> Dict:
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
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'get market latest')

def _parse_range_param(params: Dict, default: int = 30) -> int:
    try:
        return int((params.get('range', [None])[0] or params.get('days', [default])[0]))
    except (ValueError, TypeError, IndexError):
        return default

INDEX_SYMBOLS = ['^GSPC', '^IXIC', '^NYA', '^RUT']

def _get_markets(cur) -> Dict:
        try:
            cur.execute("""
                SELECT symbol, date, open, high, low, close, volume
                FROM price_daily
                WHERE symbol = ANY(%s)
                  AND date = (SELECT MAX(date) FROM price_daily WHERE symbol = ANY(%s))
                ORDER BY symbol
            """, (INDEX_SYMBOLS, INDEX_SYMBOLS))
            latest = cur.fetchall()

            cur.execute("""
                SELECT symbol, date, close
                FROM price_daily
                WHERE symbol = ANY(%s)
                  AND date >= CURRENT_DATE - INTERVAL '90 days'
                ORDER BY symbol, date DESC
            """, (INDEX_SYMBOLS,))
            history_rows = cur.fetchall()

            history = {}
            for row in history_rows:
                sym = row['symbol']
                if sym not in history:
                    history[sym] = []
                history[sym].append({'date': str(row['date']), 'close': float(row['close']) if row['close'] else None})

            result = {
                'indices': [dict(r) for r in latest] if latest else [],
                'history': history,
            }
            return json_response(200, result)
        except (psycopg2.errors.UndefinedTable, Exception) as e:
            return handle_db_error(e, logger, 'get market indices')
