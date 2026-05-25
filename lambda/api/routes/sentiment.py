"""Route: sentiment"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, safe_page, handle_db_error

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/sentiment/* endpoints."""
        try:
            if path == '/api/sentiment/summary':
                cur.execute("""
                    SELECT fg.fear_greed_value, fg.fear_greed_label, fg.date,
                           mh.put_call_ratio, mh.vix_level
                    FROM fear_greed_index fg
                    LEFT JOIN market_health_daily mh ON mh.date = fg.date
                    ORDER BY fg.date DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                fg_value = float(row['fear_greed_value']) if row and row['fear_greed_value'] else None
                fg_label = row['fear_greed_label'] if row else None

                aaii_row = None
                try:
                    cur.execute("""
                        SELECT bullish, neutral, bearish, date
                        FROM aaii_sentiment
                        ORDER BY date DESC
                        LIMIT 1
                    """)
                    aaii_row = cur.fetchone()
                except Exception:
                    pass

                naaim_row = None
                try:
                    cur.execute("""
                        SELECT naaim_number_mean, date
                        FROM naaim
                        ORDER BY date DESC
                        LIMIT 1
                    """)
                    naaim_row = cur.fetchone()
                except Exception:
                    pass

                analyst_row = None
                try:
                    cur.execute("""
                        SELECT SUM(analyst_count) AS analyst_count,
                               SUM(bullish_count) AS bullish_count,
                               SUM(bearish_count) AS bearish_count,
                               MAX(date) AS date
                        FROM analyst_sentiment_analysis
                        WHERE date = (SELECT MAX(date) FROM analyst_sentiment_analysis)
                    """)
                    analyst_row = cur.fetchone()
                except Exception:
                    pass

                return json_response(200, {
                    'fear_greed': {'value': fg_value, 'label': fg_label} if fg_value is not None else None,
                    'aaii': dict(aaii_row) if aaii_row else None,
                    'naaim': dict(naaim_row) if naaim_row else None,
                    'analyst': dict(analyst_row) if analyst_row and analyst_row['analyst_count'] else None,
                    'put_call_ratio': float(row['put_call_ratio']) if row and row['put_call_ratio'] else None,
                    'vix_level': float(row['vix_level']) if row and row['vix_level'] else None,
                    'date': str(row['date']) if row else None,
                })
            elif path == '/api/sentiment/data' or path.startswith('/api/sentiment/data?'):
                limit_str = params.get('limit', [None])[0] if params else None
                limit = safe_limit(limit_str, max_val=50000, default=50000)
                page_str = params.get('page', [None])[0] if params else None
                page = safe_page(page_str, default=1)
                offset = (page - 1) * limit
                cur.execute("""
                    SELECT symbol, date, analyst_count, bullish_count, bearish_count, neutral_count,
                           target_price, current_price, upside_downside_percent
                    FROM analyst_sentiment_analysis
                    ORDER BY date DESC, symbol ASC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                sentiment = cur.fetchall()
                return list_response([dict(s) for s in sentiment] if sentiment else [])
            elif path == '/api/sentiment/divergence':
                cur.execute("""
                    SELECT asa.symbol, asa.date,
                           asa.bullish_count, asa.bearish_count, asa.analyst_count,
                           asa.upside_downside_percent,
                           ROUND(asa.bullish_count::numeric / NULLIF(asa.analyst_count, 0) * 100, 2) AS bull_percent,
                           ROUND(asa.bearish_count::numeric / NULLIF(asa.analyst_count, 0) * 100, 2) AS bear_percent,
                           ss.composite_score
                    FROM analyst_sentiment_analysis asa
                    LEFT JOIN stock_scores ss ON ss.symbol = asa.symbol
                    WHERE asa.date >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY asa.date DESC, asa.upside_downside_percent DESC NULLS LAST
                    LIMIT 2000
                """)
                rows = cur.fetchall()
                return list_response([dict(r) for r in rows] if rows else [])
            elif path.startswith('/api/sentiment/analyst/insights/'):
                symbol = path.split('/api/sentiment/analyst/insights/')[-1].upper()
                cur.execute("""
                    SELECT date, analyst_count, bullish_count, bearish_count, neutral_count,
                           target_price, current_price, upside_downside_percent
                    FROM analyst_sentiment_analysis
                    WHERE symbol = %s
                    ORDER BY date DESC
                    LIMIT 12
                """, (symbol,))
                rows = cur.fetchall()
                return list_response([dict(r) for r in rows] if rows else [])
            elif path.startswith('/api/sentiment/social/insights/'):
                return json_response(501, {'status': 'not_implemented', 'message': 'Social sentiment requires external API integration (not yet configured)'})
            elif path == '/api/sentiment/vix':
                return _get_vix_data(cur)
            elif path == '/api/sentiment' or path.startswith('/api/sentiment?'):
                # Default: return same shape as /api/sentiment/summary
                cur.execute("""
                    SELECT fg.fear_greed_value, fg.fear_greed_label, fg.date,
                           mh.put_call_ratio, mh.vix_level
                    FROM fear_greed_index fg
                    LEFT JOIN market_health_daily mh ON mh.date = fg.date
                    ORDER BY fg.date DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                if row:
                    return json_response(200, {
                        'fear_greed': {'value': float(row['fear_greed_value']), 'label': row['fear_greed_label']} if row['fear_greed_value'] else None,
                        'put_call_ratio': float(row['put_call_ratio']) if row['put_call_ratio'] else None,
                        'vix_level': float(row['vix_level']) if row['vix_level'] else None,
                        'date': str(row['date']),
                    })
                return json_response(200, {})
            return error_response(404, 'not_found', f'No sentiment handler for {path}')
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'handle sentiment')


def _get_vix_data(cur) -> Dict:
        """Get latest VIX data and historical trend."""
        try:
            cur.execute("""
                SELECT date, vix_level, put_call_ratio, market_trend, market_stage
                FROM market_health_daily
                WHERE vix_level IS NOT NULL
                ORDER BY date DESC
                LIMIT 60
            """)
            rows = cur.fetchall()

            if not rows:
                return json_response(200, {'data': [], 'latest': None})

            latest = dict(rows[0]) if rows else None
            history = [dict(r) for r in rows]

            return json_response(200, {
                'latest': latest,
                'history': history,
                'signal': 'fear' if latest and latest.get('vix_level', 0) > 25 else 'neutral' if latest and latest.get('vix_level', 0) > 15 else 'greed'
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'get vix data')
