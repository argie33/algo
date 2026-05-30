"""Route: economic"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, handle_db_error, check_data_freshness

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/economic and /api/economic/* endpoints."""
        try:
            if path == '/api/economic/VIX':
                cur.execute("""
                    SELECT date, vix_level as vix
                    FROM market_health_daily
                    WHERE vix_level IS NOT NULL
                    ORDER BY date DESC
                    LIMIT 100
                """)
                rows = cur.fetchall()
                freshness = check_data_freshness(cur, 'market_health_daily', 'date', warning_days=1)
                return list_response([dict(r) for r in rows] if rows else [], data_freshness=freshness)
            elif path == '/api/economic/leading-indicators':
                return _get_leading_indicators(cur)
            elif path == '/api/economic/indicators':
                return _get_leading_indicators(cur)
            elif path == '/api/economic/yield-curve-full':
                return _get_yield_curve_full(cur)
            elif path == '/api/economic/calendar':
                try:
                    start_date = params.get('start_date', [None])[0] if params else None
                    end_date = params.get('end_date', [None])[0] if params else None
                    query_params = []
                    date_filter = ""
                    if start_date:
                        date_filter += " AND event_date >= %s"
                        query_params.append(start_date)
                    if end_date:
                        date_filter += " AND event_date <= %s"
                        query_params.append(end_date)
                    cur.execute("""
                        SELECT event_date, event_name, country, importance,
                               category, event_time,
                               forecast_value AS forecast,
                               actual_value AS actual,
                               previous_value AS previous
                        FROM economic_calendar
                        WHERE 1=1
                    """ + date_filter + """
                        ORDER BY event_date ASC
                        LIMIT 200
                    """, query_params)
                    events = cur.fetchall()
                    freshness = check_data_freshness(cur, 'economic_calendar', 'event_date', warning_days=7)
                    return list_response([dict(e) for e in events] if events else [], data_freshness=freshness)
                except (psycopg2.errors.UndefinedColumn, psycopg2.errors.UndefinedTable):
                    return list_response([])
            elif path == '/api/economic':
                # Combine all economic data
                return _get_leading_indicators(cur)
            return error_response(404, 'not_found', f'No economic handler for {path}')
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'handle economic')
def _get_leading_indicators(cur) -> Dict:
        """Get leading economic indicators formatted for EconomicDashboard."""
        # Maps FRED series IDs to indicator names
        indicator_map = {
            'UNRATE': 'Unemployment Rate',
            'PAYEMS': 'Total Nonfarm Payroll',
            'ICSA': 'Initial Claims',
            'CIVPART': 'Labor Force Participation',
            'INDPRO': 'Industrial Production',
            'RSXFS': 'Retail Sales',
            'CPIAUCSL': 'CPI - All Urban Consumers',
            'FEDFUNDS': 'Federal Funds Rate',
            'M2SL': 'M2 Money Supply',
            'T10Y2Y': 'Yield Curve (10Y-2Y)',
            'GDPC1': 'GDP Growth',
            'UMCSENT': 'Consumer Sentiment',
            'HOUST': 'Housing Starts',
        }
        # Series that report absolute levels but should be shown as YoY % change
        yoy_pct_series = {'GDPC1', 'INDPRO', 'RSXFS', 'PAYEMS', 'HOUST'}

        try:
            cur.execute("""
                WITH latest AS (
                    SELECT series_id, date, value,
                           ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY date DESC) as rn
                    FROM economic_data
                )
                SELECT series_id, date, value
                FROM latest
                WHERE rn = 1
            """)
            latest_rows = {row['series_id']: (float(row['value']) if row['value'] else None, row['date'])
                          for row in cur.fetchall()}

            cur.execute("""
                SELECT series_id, date, value
                FROM economic_data
                WHERE date >= CURRENT_DATE - INTERVAL '24 months'
                ORDER BY series_id, date DESC
            """)
            all_history = cur.fetchall()

            # Group by series_id
            history_by_series = {}
            for row in all_history:
                sid = row['series_id']
                if sid not in history_by_series:
                    history_by_series[sid] = []
                history_by_series[sid].append({
                    'date': str(row['date']),
                    'value': float(row['value']) if row['value'] else None
                })

            # Build indicator objects
            indicators = []
            for series_id, name in indicator_map.items():
                if series_id not in latest_rows:
                    continue

                value, dt = latest_rows[series_id]
                history = sorted(history_by_series.get(series_id, []), key=lambda x: x['date'])

                # For level series, compute YoY % change so the frontend gets a meaningful rate
                display_value = value
                if series_id in yoy_pct_series and len(history) >= 12:
                    # history is sorted ascending; last = most recent, -13 ≈ 1 year ago
                    cur_h  = history[-1] if history else None
                    yr_ago = history[-13] if len(history) >= 13 else history[0]
                    if cur_h and yr_ago and yr_ago.get('value') and cur_h.get('value'):
                        prior = float(yr_ago['value'])
                        if prior != 0:
                            display_value = round((float(cur_h['value']) - prior) / abs(prior) * 100, 2)
                    # Replace history values with rolling YoY % change too
                    yoy_history = []
                    for idx in range(12, len(history)):
                        cur_v  = history[idx].get('value')
                        yr_v   = history[idx - 12].get('value')
                        if cur_v is not None and yr_v and float(yr_v) != 0:
                            yoy_history.append({
                                'date': history[idx]['date'],
                                'value': round((float(cur_v) - float(yr_v)) / abs(float(yr_v)) * 100, 2)
                            })
                    if yoy_history:
                        history = yoy_history

                # Calculate trend (up/down/flat) on the (possibly transformed) history
                if len(history) >= 2:
                    recent_avg = sum([h['value'] for h in history[-3:] if h['value'] is not None] or [0]) / max(1, len([h for h in history[-3:] if h['value'] is not None]))
                    older_avg  = sum([h['value'] for h in history[:3]  if h['value'] is not None] or [0]) / max(1, len([h for h in history[:3]  if h['value'] is not None]))
                    if older_avg and recent_avg:
                        trend = 'up' if recent_avg > older_avg * 1.01 else 'down' if recent_avg < older_avg * 0.99 else 'flat'
                    else:
                        trend = 'flat'
                else:
                    trend = 'flat'

                indicators.append({
                    'name': name,
                    'series_id': series_id,
                    'rawValue': display_value,
                    'date': str(dt),
                    'history': history,
                    'trend': trend
                })

            return json_response(200, {'indicators': indicators})

        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'get leading indicators')
def _get_yield_curve_full(cur) -> Dict:
        """Get yield curve and credit spread data formatted for EconomicDashboard."""
        try:
            cur.execute("""
                WITH latest AS (
                    SELECT series_id, date, value,
                           ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY date DESC) as rn
                    FROM economic_data
                    WHERE series_id IN ('DGS3MO', 'DGS6MO', 'DGS1', 'DGS2', 'DGS3', 'DGS5', 'DGS7', 'DGS10', 'DGS20', 'DGS30', 'T10Y3M', 'T10Y2Y',
                                       'BAMLH0A0HYM2', 'BAMLC0A0CM', 'VIXCLS')
                )
                SELECT series_id, date, value
                FROM latest
                WHERE rn = 1
            """)
            latest_rows = cur.fetchall()

            cur.execute("""
                SELECT series_id, date, value
                FROM economic_data
                WHERE date >= CURRENT_DATE - INTERVAL '12 months'
                AND series_id IN ('T10Y2Y', 'BAMLH0A0HYM2', 'BAMLC0A0CM', 'VIXCLS')
                ORDER BY series_id, date
            """)
            history_rows = cur.fetchall()

            # Build response
            current_curve = {}
            spreads = {}
            is_inverted = False
            history = {}

            for row in latest_rows:
                sid = row['series_id']
                val = float(row['value']) if row['value'] else None

                # Build current yield curve
                if sid == 'DGS3MO':
                    current_curve['3M'] = val
                elif sid == 'DGS6MO':
                    current_curve['6M'] = val
                elif sid == 'DGS1':
                    current_curve['1Y'] = val
                elif sid == 'DGS2':
                    current_curve['2Y'] = val
                elif sid == 'DGS3':
                    current_curve['3Y'] = val
                elif sid == 'DGS5':
                    current_curve['5Y'] = val
                elif sid == 'DGS7':
                    current_curve['7Y'] = val
                elif sid == 'DGS10':
                    current_curve['10Y'] = val
                elif sid == 'DGS20':
                    current_curve['20Y'] = val
                elif sid == 'DGS30':
                    current_curve['30Y'] = val
                elif sid == 'T10Y3M':
                    spreads['T10Y3M'] = val
                elif sid == 'T10Y2Y':
                    spreads['T10Y2Y'] = val
                    is_inverted = (val < 0) if val else False

            # Add history for spreads
            history_by_series = {}
            for row in history_rows:
                sid = row['series_id']
                if sid not in history_by_series:
                    history_by_series[sid] = []
                history_by_series[sid].append({
                    'date': str(row['date']),
                    'value': float(row['value']) if row['value'] else None
                })

            for sid, hist in history_by_series.items():
                history[sid] = sorted(hist, key=lambda x: x['date'])

            # Build credit sub-object with the series names the frontend expects
            credit_history = {
                'BAMLH0A0HYM2': history.get('BAMLH0A0HYM2', []),
                'BAMLH0A0IG':   history.get('BAMLC0A0CM', []),  # BAMLC0A0CM is IG corporate OAS
                'VIXCLS':       history.get('VIXCLS', []),
            }
            credit_latest = {
                k: v[-1].get('value') if v else None
                for k, v in credit_history.items()
            }

            return json_response(200, {
                'currentCurve': current_curve,
                'spreads': spreads,
                'isInverted': is_inverted,
                'history': history,
                'credit': {
                    'history': credit_history,
                    'currentSpreads': credit_latest,
                },
            })

        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.error(f'Data unavailable: {e}', extra={'operation': 'get yield curve full'})
            return error_response(503, 'service_unavailable', 'Data unavailable')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get yield curve full'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get yield curve full', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get yield curve full', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch yield curve')
