"""Route: market"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, handle_db_error, check_data_freshness, execute_with_timeout, decimal_to_float_recursive

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
        """Handle /api/market/* endpoints."""
        try:
            if path in ['/api/market', '/api/market/status'] or path.startswith('/api/market?'):
                cur.execute("SET LOCAL statement_timeout = '5000ms'")
                cur.execute("""
                    SELECT date, market_trend, market_stage, advance_decline_ratio,
                           new_highs_count, new_lows_count, vix_level, put_call_ratio,
                           distribution_days_4w
                    FROM market_health_daily
                    ORDER BY date DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                result = dict(row) if row else {}

                # Add freshness check
                freshness = check_data_freshness(cur, 'market_health_daily', 'date', warning_days=1)
                result['data_freshness'] = freshness

                return json_response(200, result)
            elif path == '/api/market/indices':
                return _get_markets(cur)
            elif path == '/api/market/breadth':
                # Compute A/D per day using a self-join on consecutive trading dates.
                # Self-join is faster than LAG window over 35 days × 9000 symbols.
                # Uses retry logic with exponential backoff to handle transient timeouts
                # when DB is under heavy write load from loaders.
                breadth = []
                freshness = {}

                breadth_query = """
                    WITH trading_dates AS (
                        SELECT DISTINCT date
                        FROM price_daily
                        WHERE date >= CURRENT_DATE - INTERVAL '25 days'
                        ORDER BY date DESC LIMIT 12
                    ),
                    date_pairs AS (
                        SELECT d1.date AS d, MAX(d2.date) AS prev_d
                        FROM trading_dates d1
                        JOIN trading_dates d2 ON d2.date < d1.date
                        GROUP BY d1.date
                    )
                    SELECT
                        dp.d AS date,
                        COUNT(*) FILTER (WHERE t.close > y.close) AS advances,
                        COUNT(*) FILTER (WHERE t.close < y.close) AS declines,
                        COUNT(*) FILTER (WHERE t.close = y.close) AS unchanged,
                        COUNT(t.symbol) AS total
                    FROM date_pairs dp
                    JOIN price_daily t ON t.date = dp.d AND t.symbol NOT LIKE '^%%'
                    JOIN price_daily y ON y.date = dp.prev_d AND y.symbol = t.symbol
                    GROUP BY dp.d
                    ORDER BY dp.d DESC
                    LIMIT 10
                """

                # Execute with retry: start at 8s, retry at 12s if timeout
                try:
                    breadth = execute_with_timeout(cur, breadth_query, timeout_sec=8, max_attempts=2, backoff_multiplier=1.5)
                except psycopg2.errors.QueryCanceled as e:
                    logger.error(f'Breadth query timeout: {e}')
                    return error_response(504, 'timeout', 'Market breadth data query exceeded timeout')
                except Exception as e:
                    logger.error(f'Breadth query failed: {e}')
                    return error_response(503, 'service_unavailable', 'Failed to fetch market breadth data')

                if breadth:
                    # Only fetch freshness if query succeeded
                    try:
                        freshness = check_data_freshness(cur, 'price_daily', 'date', warning_days=1)
                    except Exception:
                        freshness = {}

                return list_response([dict(b) for b in breadth], data_freshness=freshness)
            elif path == '/api/market/technicals':
                try:
                    rows = execute_with_timeout(cur, """
                        SELECT date, advance_decline_ratio, new_highs_count, new_lows_count,
                               up_volume_percent, distribution_days_4w, breadth_momentum_10d,
                               vix_level, put_call_ratio, market_trend, market_stage
                        FROM market_health_daily
                        ORDER BY date DESC
                        LIMIT 1
                    """, timeout_sec=5)
                except psycopg2.errors.QueryCanceled as e:
                    logger.error(f'Technicals query timeout: {e}')
                    return error_response(504, 'timeout', 'Market technicals data query exceeded timeout')
                except Exception as e:
                    logger.error(f'Technicals query failed: {e}')
                    return error_response(503, 'service_unavailable', 'Failed to fetch market technicals data')

                base = dict(rows[0]) if rows else {}
                # Ensure breadth and mcclellan_oscillator are always present
                if 'breadth' not in base:
                    base['breadth'] = {}
                if 'mcclellan_oscillator' not in base:
                    base['mcclellan_oscillator'] = []

                # Compute today's advancing/declining counts from price_daily.
                # SAVEPOINT isolation: a timeout here must not abort the outer transaction.
                try:
                    cur.execute("SAVEPOINT technicals_breadth")
                    breadth_query = """
                        WITH latest AS (
                                 SELECT date AS d FROM price_daily ORDER BY date DESC LIMIT 1
                             ),
                             prev_day AS (
                                 SELECT date AS d FROM price_daily
                                 WHERE date < (SELECT d FROM latest)
                                 ORDER BY date DESC LIMIT 1
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
                    """
                    breadth_rows = execute_with_timeout(cur, breadth_query, timeout_sec=5)
                    cur.execute("RELEASE SAVEPOINT technicals_breadth")
                    base['breadth'] = dict(breadth_rows[0]) if breadth_rows else {}
                except Exception as e:
                    logger.warning(f"Technicals breadth query failed ({type(e).__name__}) — skipping. DB may be under write load.")
                    try:
                        cur.execute("ROLLBACK TO SAVEPOINT technicals_breadth")
                        cur.execute("RELEASE SAVEPOINT technicals_breadth")
                    except Exception: pass
                    base['breadth'] = {}
                # Build 30-day McClellan Oscillator history from market_exposure_daily.
                # The factors JSONB column stores the true McClellan value (19-EMA minus
                # 39-EMA of net advances) computed by algo_market_exposure._mcclellan().
                try:
                    cur.execute("SET LOCAL statement_timeout = '5000ms'")
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
                except Exception as e:
                    logger.warning(f"Exception: {e}")
                    base['mcclellan_oscillator'] = []
                freshness = check_data_freshness(cur, 'market_health_daily', 'date', warning_days=1)
                base['data_freshness'] = freshness
                return json_response(200, base)
            elif path == '/api/market/top-movers':
                movers = []
                gainers = []
                losers = []
                try:
                    cur.execute("SAVEPOINT top_movers")
                    cur.execute("SET LOCAL statement_timeout = '8s'")
                    cur.execute("""
                        WITH latest_d AS (
                            SELECT date AS d FROM price_daily ORDER BY date DESC LIMIT 1
                        ),
                        today AS (
                            SELECT symbol, close
                            FROM price_daily
                            WHERE date = (SELECT d FROM latest_d)
                        ),
                        yesterday AS (
                            SELECT symbol, close
                            FROM price_daily
                            WHERE date = (
                                SELECT date FROM price_daily WHERE date < (SELECT d FROM latest_d)
                                ORDER BY date DESC LIMIT 1
                            )
                        )
                        SELECT t.symbol, ss.security_name,
                               ROUND(((t.close - y.close) / NULLIF(y.close, 0) * 100)::numeric, 2) as pct_change
                        FROM today t
                        JOIN yesterday y ON t.symbol = y.symbol
                        JOIN stock_symbols ss ON t.symbol = ss.symbol
                        WHERE y.close > 0
                          AND t.symbol NOT LIKE '^%%'
                          AND COALESCE(ss.etf, 'N') != 'Y'
                        ORDER BY ABS(t.close - y.close) / y.close DESC
                        LIMIT 40
                    """)
                    movers = cur.fetchall()
                    cur.execute("RELEASE SAVEPOINT top_movers")
                except Exception as e:
                    logger.warning(f"Top movers query failed ({type(e).__name__}) — returning empty. DB may be under write load.")
                    try:
                        cur.execute("ROLLBACK TO SAVEPOINT top_movers")
                        cur.execute("RELEASE SAVEPOINT top_movers")
                    except Exception: pass
                items = [decimal_to_float_recursive(dict(m)) for m in movers] if movers else []
                gainers = sorted([m for m in items if (m.get('pct_change') or 0) >= 0],
                                 key=lambda x: -(x.get('pct_change') or 0))[:10]
                losers = sorted([m for m in items if (m.get('pct_change') or 0) < 0],
                                key=lambda x: (x.get('pct_change') or 0))[:10]
                return json_response(200, {'gainers': gainers or [], 'losers': losers or [], 'items': items})
            elif path == '/api/market/distribution-days':
                DIST_INDEX_NAMES = {'^GSPC': 'S&P 500', '^IXIC': 'Nasdaq Composite', '^NYA': 'NYSE Composite', '^DJI': 'Dow Jones', '^RUT': 'Russell 2000'}
                try:
                    cur.execute("SAVEPOINT dist_days")
                    cur.execute("SET LOCAL statement_timeout = '8s'")
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
                        result[sym] = {'name': DIST_INDEX_NAMES.get(sym, sym), 'count': count, 'signal': signal, 'days': days}
                    cur.execute("RELEASE SAVEPOINT dist_days")
                    return json_response(200, result)
                except Exception as e:
                    logger.warning(f"Distribution days query failed ({type(e).__name__}) — returning empty. DB may be under write load.")
                    try:
                        cur.execute("ROLLBACK TO SAVEPOINT dist_days")
                        cur.execute("RELEASE SAVEPOINT dist_days")
                    except Exception: pass
                    return json_response(200, {})
            elif path == '/api/market/seasonality':
                # Seasonality tables are market-wide aggregates (SPY-based), no per-symbol filtering
                monthly_data = []
                best_month = None
                worst_month = None
                try:
                    cur.execute("""
                        SELECT month, month_name, avg_return, best_return, worst_return,
                               winning_years, losing_years, years_counted
                        FROM seasonality_monthly_stats
                        ORDER BY month
                    """)
                    monthly_rows = cur.fetchall()
                    for r in monthly_rows:
                        r_dict = dict(r)
                        monthly_data.append(r_dict)
                        if not best_month or r_dict.get('avg_return', 0) > best_month.get('avg_return', 0):
                            best_month = r_dict
                        if not worst_month or r_dict.get('avg_return', 0) < worst_month.get('avg_return', 0):
                            worst_month = r_dict
                except Exception as e:
                    logger.warning(f"Exception: {e}")
                    monthly_data = []

                dow_data = []
                best_dow = None
                worst_dow = None
                try:
                    cur.execute("""
                        SELECT day, day_num, avg_return, win_rate, days_counted
                        FROM seasonality_day_of_week
                        ORDER BY day_num
                    """)
                    dow_rows = cur.fetchall()
                    for r in dow_rows:
                        r_dict = dict(r)
                        dow_data.append(r_dict)
                        if not best_dow or r_dict.get('avg_return', 0) > best_dow.get('avg_return', 0):
                            best_dow = r_dict
                        if not worst_dow or r_dict.get('avg_return', 0) < worst_dow.get('avg_return', 0):
                            worst_dow = r_dict
                except Exception as e:
                    logger.warning(f"Exception: {e}")
                    dow_data = []

                return json_response(200, {
                    'monthly': monthly_data or [],
                    'day_of_week': dow_data or [],
                    'summary': {
                        'best_month': {
                            'name': best_month.get('month_name') if best_month else None,
                            'avg_return_pct': float(best_month.get('avg_return', 0) or 0) if best_month else None,
                            'win_rate_pct': round((float(best_month.get('winning_years', 0) or 0) / float(best_month.get('years_counted', 1) or 1) * 100), 1) if best_month else None
                        } if best_month else None,
                        'worst_month': {
                            'name': worst_month.get('month_name') if worst_month else None,
                            'avg_return_pct': float(worst_month.get('avg_return', 0) or 0) if worst_month else None,
                            'win_rate_pct': round((float(worst_month.get('winning_years', 0) or 0) / float(worst_month.get('years_counted', 1) or 1) * 100), 1) if worst_month else None
                        } if worst_month else None,
                        'best_day': {
                            'name': best_dow.get('day') if best_dow else None,
                            'avg_return_pct': float(best_dow.get('avg_return', 0) or 0) if best_dow else None,
                            'win_rate_pct': float(best_dow.get('win_rate', 0) or 0) if best_dow else None
                        } if best_dow else None,
                        'worst_day': {
                            'name': worst_dow.get('day') if worst_dow else None,
                            'avg_return_pct': float(worst_dow.get('avg_return', 0) or 0) if worst_dow else None,
                            'win_rate_pct': float(worst_dow.get('win_rate', 0) or 0) if worst_dow else None
                        } if worst_dow else None
                    },
                    'insights': {
                        'sell_in_may_effect': 'May returns' if monthly_data else None,
                        'monday_effect': 'Historically, Mondays trend lower' if dow_data else None
                    }
                })
            elif path == '/api/market/sentiment':
                range_days = _parse_range_param(params) if params else 30
                sentiment_data = {}

                # AAII investor sentiment
                try:
                    cur.execute("""
                        SELECT date, bullish, neutral, bearish
                        FROM aaii_sentiment
                        WHERE date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                        ORDER BY date ASC
                    """, (range_days,))
                    aaii_rows = [dict(r) for r in cur.fetchall()]
                    aaii_current = aaii_rows[-1] if aaii_rows else None

                    # Compute trend: is bullish rising or falling?
                    aaii_trend = 'neutral'
                    if len(aaii_rows) >= 2:
                        prev = float(aaii_rows[-2].get('bullish', 0) or 0)
                        curr = float(aaii_rows[-1].get('bullish', 0) or 0)
                        aaii_trend = 'rising' if curr > prev * 1.02 else 'falling' if curr < prev * 0.98 else 'neutral'

                    sentiment_data['aaii'] = {
                        'current': aaii_current,
                        'history': aaii_rows,
                        'trend': aaii_trend,
                        'data': aaii_rows,
                        'bullish_pct': float(aaii_current['bullish'] or 0) if aaii_current else None
                    }
                except Exception as e:
                    sentiment_data['aaii'] = {'current': None, 'history': [], 'data': [], 'trend': None, 'bullish_pct': None}

                # NAAIM manager exposure
                try:
                    cur.execute("""
                        SELECT date, naaim_number_mean, bullish, bearish
                        FROM naaim
                        WHERE date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                        ORDER BY date ASC
                        LIMIT 52
                    """, (range_days,))
                    naaim_rows = [dict(r) for r in cur.fetchall()]
                    naaim_current = naaim_rows[-1] if naaim_rows else None

                    # Compute trend
                    naaim_trend = 'neutral'
                    if len(naaim_rows) >= 2:
                        prev = float(naaim_rows[-2].get('naaim_number_mean', 0) or 0)
                        curr = float(naaim_rows[-1].get('naaim_number_mean', 0) or 0)
                        naaim_trend = 'rising' if curr > prev * 1.02 else 'falling' if curr < prev * 0.98 else 'neutral'

                    sentiment_data['naaim'] = {
                        'current': float(naaim_current['naaim_number_mean'] or 0) if naaim_current else None,
                        'history': naaim_rows,
                        'trend': naaim_trend,
                        'bullish_pct': float(naaim_current['bullish'] or 0) if naaim_current else None,
                        'bearish_pct': float(naaim_current['bearish'] or 0) if naaim_current else None
                    }
                except Exception as e:
                    logger.warning(f"Exception: {e}")
                    sentiment_data['naaim'] = {'current': None, 'history': [], 'trend': None, 'bullish_pct': None, 'bearish_pct': None}

                # Fear & Greed
                try:
                    cur.execute("""
                        SELECT date, fear_greed_value as value, fear_greed_label as label
                        FROM fear_greed_index
                        WHERE date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                        ORDER BY date ASC
                    """, (range_days,))
                    fg_rows = [dict(r) for r in cur.fetchall()]
                    fg_current = fg_rows[-1] if fg_rows else None

                    # Compute trend
                    fg_trend = 'neutral'
                    if len(fg_rows) >= 2:
                        prev = float(fg_rows[-2].get('value', 0) or 0)
                        curr = float(fg_rows[-1].get('value', 0) or 0)
                        fg_trend = 'rising_fear' if curr < prev * 0.98 else 'rising_greed' if curr > prev * 1.02 else 'neutral'

                    sentiment_data['fearGreed'] = {
                        'current': {
                            'value': float(fg_current['value'] or 0) if fg_current else None,
                            'label': fg_current.get('label') if fg_current else None
                        },
                        'history': fg_rows,
                        'trend': fg_trend,
                        'data': fg_rows
                    }
                except Exception as e:
                    logger.warning(f"Exception: {e}")
                    sentiment_data['fearGreed'] = {'current': {'value': None, 'label': None}, 'history': [], 'trend': None, 'data': []}

                return json_response(200, sentiment_data)
            elif path == '/api/market/fear-greed':
                range_days = _parse_range_param(params) if params else 30
                return _get_fear_greed_history(cur, range_days)
            elif path == '/api/market/naaim':
                try:
                    cur.execute("SET LOCAL statement_timeout = '5000ms'")
                    cur.execute("""
                        SELECT date, naaim_number_mean, bullish, bearish
                        FROM naaim
                        ORDER BY date ASC
                        LIMIT 52
                    """)
                    rows = cur.fetchall()
                    if not rows:
                        return json_response(200, {
                            'current': None,
                            'history': [],
                            'moving_averages': {},
                            'signals': {'extreme_bullish': False, 'extreme_bearish': False}
                        })

                    history = []
                    for r in rows:
                        r_dict = dict(r)
                        history.append({
                            'date': str(r_dict.get('date') or ''),
                            'value': float(r_dict.get('naaim_number_mean') or 0),
                            'bullish_pct': float(r_dict.get('bullish') or 0),
                            'bearish_pct': float(r_dict.get('bearish') or 0)
                        })

                    if history:
                        current = history[-1]
                        values = [h['value'] for h in history]

                        # Compute moving averages
                        ma_10 = sum(values[-10:]) / min(10, len(values)) if len(values) >= 10 else None
                        ma_20 = sum(values[-20:]) / min(20, len(values)) if len(values) >= 20 else None
                        ma_50 = sum(values[-50:]) / min(50, len(values)) if len(values) >= 50 else None

                        # Identify extremes (>80 = extreme bullish, <20 = extreme bearish)
                        curr_val = current['value'] or 0
                        signals = {
                            'extreme_bullish': curr_val > 80,
                            'extreme_bearish': curr_val < 20,
                            'overbought': curr_val > 70,
                            'oversold': curr_val < 30,
                            'above_50': curr_val > 50,
                            'below_50': curr_val <= 50
                        }

                        return json_response(200, {
                            'current': current['value'],
                            'bullish_pct': current['bullish_pct'],
                            'bearish_pct': current['bearish_pct'],
                            'history': history,
                            'moving_averages': {
                                'ma_10': round(ma_10, 2) if ma_10 else None,
                                'ma_20': round(ma_20, 2) if ma_20 else None,
                                'ma_50': round(ma_50, 2) if ma_50 else None
                            },
                            'signals': signals,
                            'interpretation': {
                                'meaning': 'Manager equity allocation %; 0=all cash, 100=fully invested',
                                'current_stance': 'bullish' if curr_val > 50 else 'bearish',
                                'extremity': 'extreme_bullish' if curr_val > 80 else 'extreme_bearish' if curr_val < 20 else 'normal'
                            }
                        })
                    else:
                        return json_response(200, {'current': None, 'history': [], 'signals': {}})
                except Exception as e:
                    logger.warning(f"NAAIM query failed ({type(e).__name__}): {e}")
                    return json_response(200, {'current': None, 'history': [], 'moving_averages': {}, 'signals': {'extreme_bullish': False, 'extreme_bearish': False}})
            elif path == '/api/market/latest':
                return _get_market_latest(cur)
            elif path == '/api/market/cap-distribution':
                return _get_cap_distribution(cur)
            elif path == '/api/market/correlation':
                return _get_correlation_matrix(cur)
            elif path == '/api/market/sectors':
                return _get_sector_overview(cur)
            return error_response(404, 'not_found', f'No market handler for {path}')
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            code, error_type, message = handle_db_error(e, 'handle market')
            return error_response(code, error_type, message)
def _get_fear_greed_history(cur, days: int = 30) -> Dict:
        """Get fear/greed index history with signals."""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            cur.execute("""
                SELECT date, fear_greed_value as value, fear_greed_label as label
                FROM fear_greed_index
                WHERE date >= %s
                ORDER BY date ASC
            """, (cutoff_date,))
            history_rows = cur.fetchall()

            if not history_rows:
                return json_response(200, {
                    'current': None,
                    'history': [],
                    'statistics': {'min': None, 'max': None, 'avg': None},
                    'signals': {'extreme_fear': False, 'extreme_greed': False}
                })

            history = [dict(h) for h in history_rows]

            if history:
                current = history[-1]
                values = [h['value'] for h in history]

                # Compute stats
                min_val = min(values)
                max_val = max(values)
                avg_val = sum(values) / len(values) if values else None
                curr_val = current['value'] or 0

                # Identify extremes and signals
                signals = {
                    'extreme_fear': curr_val < 25,
                    'extreme_greed': curr_val > 75,
                    'moderate_fear': 25 <= curr_val < 45,
                    'moderate_greed': 55 < curr_val <= 75,
                    'neutral': 45 <= curr_val <= 55
                }

                return json_response(200, {
                    'current': {
                        'value': float(curr_val),
                        'label': current.get('label'),
                        'date': str(current['date']) if current.get('date') else None
                    },
                    'history': [
                        {
                            'date': str(h['date']) if h.get('date') else None,
                            'value': float(h['value'] or 0),
                            'label': h.get('label')
                        }
                        for h in history
                    ],
                    'statistics': {
                        'min': float(min_val),
                        'max': float(max_val),
                        'avg': round(float(avg_val), 2) if avg_val else None,
                        'current': float(curr_val),
                        'range_days': days
                    },
                    'signals': signals,
                    'interpretation': {
                        'meaning': 'Market sentiment gauge; 0=Fear, 50=Neutral, 100=Greed',
                        'current_stance': 'fear' if curr_val < 50 else 'greed',
                        'extremity': 'extreme_fear' if curr_val < 25 else 'extreme_greed' if curr_val > 75 else 'normal'
                    }
                })
            else:
                return json_response(200, {
                    'current': None,
                    'history': [],
                    'statistics': {'min': None, 'max': None, 'avg': None},
                    'signals': {}
                })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            code, error_type, message = handle_db_error(e, 'get fear greed history')
            return error_response(code, error_type, message)
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
                WHERE date = (SELECT date FROM price_daily ORDER BY date DESC LIMIT 1)
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
            code, error_type, message = handle_db_error(e, 'get market latest')
            return error_response(code, error_type, message)

def _parse_range_param(params: Dict, default: int = 30) -> int:
    try:
        return int((params.get('range', [None])[0] or params.get('days', [default])[0]))
    except (ValueError, TypeError, IndexError):
        return default

def _get_correlation_matrix(cur) -> Dict:
        """Compute and return correlation matrix between key market indices."""
        try:
            symbols = ['^GSPC', '^IXIC', 'SPY', 'QQQ', 'IVV', 'TLT', 'GLD']

            cur.execute("SAVEPOINT correlation_matrix")
            cur.execute("SET LOCAL statement_timeout = '8s'")
            cur.execute("""
                SELECT symbol, date, close
                FROM price_daily
                WHERE symbol = ANY(%s)
                  AND date >= CURRENT_DATE - INTERVAL '252 days'
                ORDER BY symbol, date
            """, (symbols,))
            rows = cur.fetchall()
            cur.execute("RELEASE SAVEPOINT correlation_matrix")

            if not rows:
                return json_response(200, {
                    'correlations': [],
                    'statistics': {
                        'avg_correlation': None,
                        'max_correlation': {'value': None, 'pair': []},
                        'min_correlation': {'value': None, 'pair': []}
                    },
                    'analysis': {
                        'market_regime': 'insufficient_data',
                        'diversification_score': None,
                        'risk_assessment': {
                            'concentration_risk': 'unknown',
                            'diversification_benefit': 'unknown',
                            'portfolio_stability': 'unknown'
                        }
                    }
                })

            prices_by_symbol = {}
            for row in rows:
                sym = row['symbol']
                if sym not in prices_by_symbol:
                    prices_by_symbol[sym] = []
                prices_by_symbol[sym].append((row['date'], float(row['close']) if row['close'] else 0))

            for sym in prices_by_symbol:
                prices_by_symbol[sym] = [(d, p) for d, p in sorted(prices_by_symbol[sym])]

            returns_by_symbol = {}
            for sym, prices in prices_by_symbol.items():
                if len(prices) < 2:
                    continue
                returns = []
                for i in range(1, len(prices)):
                    prev_p = prices[i-1][1]
                    curr_p = prices[i][1]
                    if prev_p > 0:
                        ret = (curr_p - prev_p) / prev_p
                        returns.append(ret)
                returns_by_symbol[sym] = returns

            valid_symbols = [s for s in symbols if s in returns_by_symbol and len(returns_by_symbol[s]) >= 10]
            if len(valid_symbols) < 2:
                return json_response(200, {
                    'correlations': [],
                    'statistics': {
                        'avg_correlation': None,
                        'max_correlation': {'value': None, 'pair': []},
                        'min_correlation': {'value': None, 'pair': []}
                    },
                    'analysis': {
                        'market_regime': 'insufficient_data',
                        'diversification_score': None,
                        'risk_assessment': {
                            'concentration_risk': 'unknown',
                            'diversification_benefit': 'unknown',
                            'portfolio_stability': 'unknown'
                        }
                    }
                })

            def pearson_corr(x_ret, y_ret):
                if len(x_ret) < 2 or len(y_ret) < 2:
                    return None
                min_len = min(len(x_ret), len(y_ret))
                if min_len < 2:
                    return None
                x = x_ret[-min_len:]
                y = y_ret[-min_len:]
                mx = sum(x) / len(x)
                my = sum(y) / len(y)
                num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
                dx = sum((xi - mx) ** 2 for xi in x)
                dy = sum((yi - my) ** 2 for yi in y)
                denom = (dx * dy) ** 0.5
                if denom == 0:
                    return None
                return num / denom

            correlations_data = []
            all_corrs = []

            for sym1 in valid_symbols:
                row_corrs = []
                for sym2 in valid_symbols:
                    if sym1 == sym2:
                        corr_val = 1.0
                    else:
                        corr_val = pearson_corr(returns_by_symbol[sym1], returns_by_symbol[sym2])
                    row_corrs.append(corr_val)
                    if sym1 != sym2 and corr_val is not None:
                        all_corrs.append(corr_val)
                correlations_data.append({
                    'symbol': sym1,
                    'correlations': row_corrs
                })

            max_corr = max(all_corrs) if all_corrs else None
            min_corr = min(all_corrs) if all_corrs else None
            avg_corr = sum(all_corrs) / len(all_corrs) if all_corrs else None

            max_pair = None
            min_pair = None

            if max_corr is not None:
                for i, sym1 in enumerate(valid_symbols):
                    for j, sym2 in enumerate(valid_symbols):
                        if i < j and correlations_data[i]['correlations'][j] == max_corr:
                            max_pair = [sym1, sym2]
                            break

            if min_corr is not None:
                for i, sym1 in enumerate(valid_symbols):
                    for j, sym2 in enumerate(valid_symbols):
                        if i < j and correlations_data[i]['correlations'][j] == min_corr:
                            min_pair = [sym1, sym2]
                            break

            avg_corr_val = round(avg_corr, 2) if avg_corr else None

            market_regime = 'high_correlation' if avg_corr_val and avg_corr_val > 0.5 else 'moderate_correlation' if avg_corr_val and avg_corr_val > 0.2 else 'low_correlation'
            diversification_score = round(max(0, 1.0 - (avg_corr_val or 0)) * 100, 1) if avg_corr_val is not None else None

            concentration_risk = 'high' if avg_corr_val and avg_corr_val > 0.6 else 'moderate' if avg_corr_val and avg_corr_val > 0.3 else 'low'
            diversification_benefit = 'low' if avg_corr_val and avg_corr_val > 0.6 else 'moderate' if avg_corr_val and avg_corr_val > 0.3 else 'high'
            portfolio_stability = 'volatile' if avg_corr_val and avg_corr_val > 0.6 else 'moderate' if avg_corr_val and avg_corr_val > 0.3 else 'stable'

            freshness = check_data_freshness(cur, 'price_daily', 'date', warning_days=1)
            return json_response(200, {
                'correlations': correlations_data,
                'statistics': {
                    'avg_correlation': avg_corr_val,
                    'max_correlation': {
                        'value': round(max_corr, 2) if max_corr else None,
                        'pair': max_pair or []
                    },
                    'min_correlation': {
                        'value': round(min_corr, 2) if min_corr else None,
                        'pair': min_pair or []
                    }
                },
                'analysis': {
                    'market_regime': market_regime,
                    'diversification_score': diversification_score,
                    'risk_assessment': {
                        'concentration_risk': concentration_risk,
                        'diversification_benefit': diversification_benefit,
                        'portfolio_stability': portfolio_stability
                    }
                },
                'data_freshness': freshness
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.warning(f"Correlation matrix query failed ({type(e).__name__}) — returning empty. DB may be under write load.")
            try:
                cur.execute("ROLLBACK TO SAVEPOINT correlation_matrix")
                cur.execute("RELEASE SAVEPOINT correlation_matrix")
            except Exception: pass
            code, error_type, message = handle_db_error(e, 'get correlation matrix')
            return error_response(code, error_type, message)

def _get_cap_distribution(cur) -> Dict:
        """Get market cap distribution across market cap buckets and sectors."""
        try:
            cur.execute("""
                SELECT symbol, sector, market_cap, market_cap_category
                FROM stock_symbols
                WHERE market_cap IS NOT NULL
                  AND market_cap > 0
                  AND sector IS NOT NULL
                  AND COALESCE(etf, 'N') != 'Y'
                  AND symbol NOT IN (SELECT symbol FROM etf_symbols)
                ORDER BY market_cap DESC
            """)
            rows = cur.fetchall()

            if not rows:
                return json_response(200, {
                    'by_category': {},
                    'by_sector': {},
                    'summary': {
                        'total_stocks': 0,
                        'total_market_cap': 0,
                        'largest_cap': None,
                        'category_distribution': {}
                    }
                })

            stocks = [dict(r) for r in rows]
            total_cap = sum(s['market_cap'] for s in stocks if s['market_cap'])

            by_category = {}
            by_sector = {}

            for stock in stocks:
                cap = stock.get('market_cap', 0)
                category = stock.get('market_cap_category', 'unknown')
                sector = stock.get('sector', 'unknown')

                if category not in by_category:
                    by_category[category] = {'count': 0, 'total_cap': 0, 'stocks': []}
                by_category[category]['count'] += 1
                by_category[category]['total_cap'] += cap
                by_category[category]['stocks'].append(stock['symbol'])

                if sector not in by_sector:
                    by_sector[sector] = {'count': 0, 'total_cap': 0, 'pct_of_market': 0}
                by_sector[sector]['count'] += 1
                by_sector[sector]['total_cap'] += cap

            for sector in by_sector:
                if total_cap > 0:
                    by_sector[sector]['pct_of_market'] = round(
                        by_sector[sector]['total_cap'] / total_cap * 100, 2
                    )

            category_dist = {}
            for cat in by_category:
                if total_cap > 0:
                    pct = by_category[cat]['total_cap'] / total_cap * 100
                    category_dist[cat] = {
                        'count': by_category[cat]['count'],
                        'pct_of_market': round(pct, 2),
                        'total_cap': by_category[cat]['total_cap'],
                        'avg_cap': round(by_category[cat]['total_cap'] / by_category[cat]['count'], 0) if by_category[cat]['count'] > 0 else 0
                    }

            sector_dist = {}
            for sector in sorted(by_sector.keys(), key=lambda s: by_sector[s]['total_cap'], reverse=True):
                sector_dist[sector] = {
                    'count': by_sector[sector]['count'],
                    'total_cap': by_sector[sector]['total_cap'],
                    'pct_of_market': by_sector[sector]['pct_of_market'],
                    'avg_cap': round(by_sector[sector]['total_cap'] / by_sector[sector]['count'], 0) if by_sector[sector]['count'] > 0 else 0
                }

            freshness = check_data_freshness(cur, 'stock_symbols', 'updated_at', warning_days=7)
            return json_response(200, {
                'by_category': {
                    k: {
                        'count': v['count'],
                        'total_cap': v['total_cap'],
                        'pct_of_market': round(v['total_cap'] / total_cap * 100, 2) if total_cap > 0 else 0,
                        'avg_cap': round(v['total_cap'] / v['count'], 0) if v['count'] > 0 else 0
                    }
                    for k, v in by_category.items()
                },
                'by_sector': sector_dist,
                'summary': {
                    'total_stocks': len(stocks),
                    'total_market_cap': total_cap,
                    'largest_cap': max((s['market_cap'] for s in stocks), default=0),
                    'smallest_cap': min((s['market_cap'] for s in stocks if s['market_cap'] > 0), default=0),
                    'category_distribution': category_dist
                },
                'data_freshness': freshness
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            code, error_type, message = handle_db_error(e, 'get cap distribution')
            return error_response(code, error_type, message)

INDEX_SYMBOLS = ['^GSPC', '^IXIC', '^NYA', '^RUT']
INDEX_NAMES = {
    '^GSPC': 'S&P 500',
    '^IXIC': 'Nasdaq Composite',
    '^NYA': 'NYSE Composite',
    '^DJI': 'Dow Jones',
    '^RUT': 'Russell 2000'
}

def _get_markets(cur) -> Dict:
        try:
            cur.execute("""
                WITH latest_date AS (
                    SELECT date AS d FROM price_daily WHERE symbol = ANY(%s) ORDER BY date DESC LIMIT 1
                ),
                prev_date AS (
                    SELECT date AS d FROM price_daily
                    WHERE symbol = ANY(%s)
                      AND date < (SELECT d FROM latest_date)
                    ORDER BY date DESC LIMIT 1
                ),
                today AS (
                    SELECT symbol, date, close
                    FROM price_daily
                    WHERE symbol = ANY(%s)
                      AND date = (SELECT d FROM latest_date)
                ),
                yesterday AS (
                    SELECT symbol, close AS prev_close
                    FROM price_daily
                    WHERE symbol = ANY(%s)
                      AND date = (SELECT d FROM prev_date)
                )
                SELECT t.symbol, t.date, t.close,
                       COALESCE(y.prev_close, t.close) AS prev_close
                FROM today t
                LEFT JOIN yesterday y ON t.symbol = y.symbol
                ORDER BY t.symbol
            """, (INDEX_SYMBOLS, INDEX_SYMBOLS, INDEX_SYMBOLS, INDEX_SYMBOLS))
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

            indices = []
            for row in latest:
                price = float(row['close']) if row['close'] else 0
                prev_price = float(row['prev_close']) if row['prev_close'] else price
                change = price - prev_price if prev_price > 0 else 0
                change_pct = (change / prev_price * 100) if prev_price > 0 else 0

                indices.append({
                    'symbol': row['symbol'],
                    'name': INDEX_NAMES.get(row['symbol'], row['symbol']),
                    'date': str(row['date']),
                    'price': round(price, 2),
                    'change': round(change, 2),
                    'changePercent': round(change_pct, 2),
                    'pe': None
                })

            result = {
                'indices': indices,
                'history': history,
            }
            return json_response(200, result)
        except (psycopg2.errors.UndefinedTable, Exception) as e:
            code, error_type, message = handle_db_error(e, 'get market indices')
            return error_response(code, error_type, message)

def _get_sector_overview(cur) -> Dict:
    """Get latest sector performance overview from sectors table."""
    try:
        cur.execute("""
            SELECT sector_name, performance_ytd, performance_1y, pe_ratio,
                   dividend_yield, market_cap, stock_count, metric_date
            FROM sectors
            WHERE metric_date = (SELECT MAX(metric_date) FROM sectors)
            ORDER BY market_cap DESC NULLS LAST
        """)
        rows = cur.fetchall()
        if not rows:
            cur.execute("""
                SELECT DISTINCT sector, COUNT(*) as stock_count
                FROM company_profile WHERE sector IS NOT NULL AND sector != ''
                GROUP BY sector ORDER BY count DESC
            """)
            rows = cur.fetchall()
            return list_response(
                [{'sector_name': r['sector'], 'stock_count': r['stock_count']} for r in rows]
            )
        return list_response([dict(r) for r in rows])
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        return list_response([])
    except Exception as e:
        code, error_type, message = handle_db_error(e, 'get sector overview')
        return error_response(code, error_type, message)
