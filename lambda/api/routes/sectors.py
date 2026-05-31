"""Route: sectors"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, safe_days, safe_page, handle_db_error, check_data_freshness

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/sectors and /api/sectors/* endpoints - return full ranking data."""
        try:
            if path == '/api/sectors/trends-batch' or path.startswith('/api/sectors/trends-batch?'):
                sectors_str = params.get('sectors', [None])[0] if params else None
                days_str = params.get('days', [None])[0] if params else None
                days = safe_days(days_str, max_val=365, default=90)

                if not sectors_str:
                    return error_response(400, 'bad_request', 'sectors parameter required (comma-separated)')

                sectors = [s.strip() for s in sectors_str.split(',')]
                result = {}

                for sector in sectors:
                    if not sector:
                        continue
                    cur.execute("""
                        SELECT date, AVG(close) AS avgPrice
                        FROM price_daily pd
                        JOIN company_profile cp ON pd.symbol = cp.ticker
                        WHERE cp.sector = %s AND pd.date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                        GROUP BY pd.date
                        ORDER BY pd.date ASC
                    """, (sector, days))
                    rows = cur.fetchall()
                    result[sector] = [dict(r) for r in rows] if rows else []

                return json_response(200, {'data': result})

            # Extract sector name if provided: /api/sectors/Technology
            parts = path.split('/')
            sector_name = parts[3] if len(parts) > 3 else None

            if sector_name and sector_name not in ('performance', 'trends-batch'):
                if path.endswith('/trend') or path.endswith('/trend/'):
                    days_str = params.get('days', [None])[0] if params else None
                    days = safe_days(days_str, max_val=365, default=90)
                    cur.execute("""
                        WITH sector_daily_avg AS (
                            SELECT
                                pd.date,
                                AVG(pd.close) AS avgPrice
                            FROM price_daily pd
                            JOIN company_profile cp ON pd.symbol = cp.ticker
                            WHERE cp.sector = %s AND pd.date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                            GROUP BY pd.date
                        ),
                        sector_with_ma AS (
                            SELECT
                                date,
                                avgPrice,
                                AVG(avgPrice) OVER (ORDER BY date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS ma_10,
                                AVG(avgPrice) OVER (ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma_20
                            FROM sector_daily_avg
                        )
                        SELECT
                            date,
                            avgPrice,
                            ROUND((avgPrice / NULLIF(ma_10, 0) - 1) * 100, 2) AS dailyStrengthScore,
                            ROUND((PERCENT_RANK() OVER (ORDER BY avgPrice) * 100)::numeric, 2) AS rank,
                            ROUND((COALESCE(ma_10, 0) - COALESCE(ma_20, 0)) / NULLIF(ma_20, 0) * 100, 2) AS momentumScore,
                            'momentum' AS momentum,
                            ROUND(COALESCE(ma_10, 0), 2) AS ma_10,
                            ROUND(COALESCE(ma_20, 0), 2) AS ma_20
                        FROM sector_with_ma
                        ORDER BY date DESC
                    """, (sector_name, days))
                    rows = cur.fetchall()
                    # Filter out any rows with NULL avgPrice (no data)
                    trend_data = [dict(r) for r in rows if r and r.get('avgPrice') is not None] if rows else []
                    return json_response(200, {'trendData': trend_data})
                else:
                    days_str = params.get('days', [None])[0] if params else None
                    days = safe_days(days_str, max_val=365, default=90)
                    cur.execute("""
                        SELECT date, sector, return_pct
                        FROM sector_performance
                        WHERE sector = %s AND date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                        ORDER BY date DESC
                    """, (sector_name, days))
                    rows = cur.fetchall()
                    return list_response([dict(r) for r in rows])
            elif path in ('/api/sectors', '/api/sectors/performance'):
                limit_str = params.get('limit', [None])[0] if params else None
                limit = safe_limit(limit_str, max_val=50000, default=50000)
                page_str = params.get('page', [None])[0] if params else None
                page = safe_page(page_str, default=1)
                offset = (page - 1) * limit

                cur.execute("""
                    WITH sector_perf_latest AS (
                        SELECT DISTINCT ON (sector) sector, return_pct AS latest_ytd
                        FROM sector_performance
                        ORDER BY sector, date DESC
                    ),
                    sector_perf_1d_prior AS (
                        SELECT DISTINCT ON (sector) sector, return_pct AS prior_1d
                        FROM sector_performance
                        WHERE date <= CURRENT_DATE - INTERVAL '1 day'
                        ORDER BY sector, date DESC
                    ),
                    sector_perf_5d_prior AS (
                        SELECT DISTINCT ON (sector) sector, return_pct AS prior_5d
                        FROM sector_performance
                        WHERE date <= CURRENT_DATE - INTERVAL '5 days'
                        ORDER BY sector, date DESC
                    ),
                    sector_perf_prior AS (
                        SELECT DISTINCT ON (sector) sector, return_pct AS prior_ytd
                        FROM sector_performance
                        WHERE date <= CURRENT_DATE - INTERVAL '20 days'
                        ORDER BY sector, date DESC
                    ),
                    sector_perf AS (
                        SELECT l.sector,
                               ROUND((l.latest_ytd - COALESCE(p1.prior_1d, l.latest_ytd))::numeric, 2) AS perf_1d,
                               ROUND((l.latest_ytd - COALESCE(p5.prior_5d, l.latest_ytd))::numeric, 2) AS perf_5d,
                               ROUND((l.latest_ytd - COALESCE(p.prior_ytd, l.latest_ytd))::numeric, 2) AS perf_20d
                        FROM sector_perf_latest l
                        LEFT JOIN sector_perf_1d_prior p1 ON p1.sector = l.sector
                        LEFT JOIN sector_perf_5d_prior p5 ON p5.sector = l.sector
                        LEFT JOIN sector_perf_prior p ON p.sector = l.sector
                    ),
                    sector_scores AS (
                        SELECT
                            cp.sector as sector_name,
                            COUNT(DISTINCT cp.ticker) as stock_count,
                            AVG(ss.composite_score) as composite_score,
                            AVG(ss.momentum_score) as momentum_score,
                            AVG(ss.value_score) as value_score,
                            AVG(ss.quality_score) as quality_score,
                            AVG(ss.growth_score) as growth_score,
                            AVG(ss.stability_score) as stability_score,
                            COALESCE(sp.perf_1d, 0) as perf_1d,
                            COALESCE(sp.perf_5d, 0) as perf_5d,
                            COALESCE(sp.perf_20d, 0) as perf_20d
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
                        LEFT JOIN sector_perf sp ON sp.sector = cp.sector
                        WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) != ''
                        GROUP BY cp.sector, sp.perf_1d, sp.perf_5d, sp.perf_20d
                    ),
                    ranked AS (
                        SELECT *,
                            RANK() OVER (ORDER BY composite_score DESC NULLS LAST) as current_rank
                        FROM sector_scores
                    ),
                    sector_pe AS (
                        SELECT
                            cp.sector,
                            AVG(vm.pe_ratio) FILTER (WHERE vm.pe_ratio > 0 AND vm.pe_ratio < 200) AS avg_trailing_pe,
                            AVG(vm.pb_ratio) FILTER (WHERE vm.pb_ratio > 0 AND vm.pb_ratio < 50)  AS avg_pb_ratio
                        FROM value_metrics vm
                        JOIN company_profile cp ON vm.symbol = cp.ticker
                        WHERE cp.sector IS NOT NULL
                        GROUP BY cp.sector
                    ),
                    sector_pe_ranked AS (
                        SELECT *,
                            PERCENT_RANK() OVER (ORDER BY avg_trailing_pe ASC NULLS LAST) * 100 AS pe_percentile
                        FROM sector_pe
                    ),
                    latest_sector_ranking AS (
                        SELECT sector_name, rank_1w_ago, rank_4w_ago, rank_12w_ago
                        FROM sector_ranking
                        WHERE date_recorded = (SELECT MAX(date_recorded) FROM sector_ranking)
                    )
                    SELECT r.*, spe.avg_trailing_pe, spe.avg_pb_ratio, spe.pe_percentile,
                           sr.rank_1w_ago, sr.rank_4w_ago, sr.rank_12w_ago
                    FROM ranked r
                    LEFT JOIN sector_pe_ranked spe ON spe.sector = r.sector_name
                    LEFT JOIN latest_sector_ranking sr ON sr.sector_name = r.sector_name
                    ORDER BY r.current_rank, r.stock_count DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))

                sectors_data = cur.fetchall()
                cur.execute("""SELECT COUNT(DISTINCT sector) as cnt FROM company_profile WHERE sector IS NOT NULL""")
                total = dict(cur.fetchone()).get('cnt', 0)

                sectors = []
                for row in sectors_data:
                    s = dict(row)
                    composite = float(s.get('composite_score') or 0)
                    perf1d = float(s.get('perf_1d') or 0) if s.get('perf_1d') is not None else None
                    perf5d = float(s.get('perf_5d') or 0) if s.get('perf_5d') is not None else None
                    perf20d = float(s.get('perf_20d') or 0)
                    momentum_label = 'Strong' if composite >= 60 else 'Moderate' if composite >= 45 else 'Weak'
                    trend_label = 'Uptrend' if perf20d > 2 else 'Downtrend' if perf20d < -2 else 'Sideways'

                    sectors.append({
                        'sector_name': s.get('sector_name'),
                        'current_rank': int(s.get('current_rank') or 0),
                        'rank_1w_ago': int(s['rank_1w_ago']) if s.get('rank_1w_ago') is not None else None,
                        'rank_4w_ago': int(s['rank_4w_ago']) if s.get('rank_4w_ago') is not None else None,
                        'rank_12w_ago': int(s['rank_12w_ago']) if s.get('rank_12w_ago') is not None else None,
                        'stock_count': int(s.get('stock_count') or 0),
                        'composite_score': float(s.get('composite_score') or 0),
                        'momentum_score': float(s.get('momentum_score') or 0),
                        'value_score': float(s.get('value_score') or 0),
                        'quality_score': float(s.get('quality_score') or 0),
                        'growth_score': float(s.get('growth_score') or 0),
                        'stability_score': float(s.get('stability_score') or 0),
                        'current_momentum': momentum_label,
                        'current_trend': trend_label,
                        'performance_1d': perf1d,
                        'performance_5d': perf5d,
                        'performance_20d': perf20d,
                        'pe': {
                            'trailing': float(s.get('avg_trailing_pe') or 0),
                            'pb_ratio': float(s.get('avg_pb_ratio') or 0),
                            'percentile': float(s.get('pe_percentile') or 0)
                        }
                    })

                freshness = check_data_freshness(cur, 'sector_ranking', 'date', warning_days=1)
                return json_response(200, {
                    'items': sectors,
                    'total': total,
                    'page': page,
                    'limit': limit,
                    'data_freshness': freshness,
                })
            elif '/trend' in path:
                parts = path.split('/')
                sector_name = parts[3] if len(parts) > 3 else None
                days_str = params.get('days', [None])[0] if params else None
                days = safe_days(days_str, max_val=365, default=90)
                if not sector_name:
                    return error_response(400, 'bad_request', 'Sector name required')
                cur.execute("""
                    SELECT date, sector, return_pct, relative_strength
                    FROM sector_performance
                    WHERE sector = %s AND date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                    ORDER BY date DESC
                """, (sector_name, days))
                rows = cur.fetchall()
                return list_response([dict(r) for r in rows])
            return error_response(404, 'not_found', f'No sector handler for {path}')
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'handle sectors')
