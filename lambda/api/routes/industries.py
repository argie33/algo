from utils.database_context import DatabaseContext
"""Route: industries"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging
from .utils import error_response, success_response, list_response, json_response, safe_limit, safe_days, safe_page, handle_db_error, check_data_freshness

logger = logging.getLogger(__name__)

def _sf(v):
    """Safe float conversion — returns None for null/missing values."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    """Handle /api/industries, /api/industries/{name}, /api/industries/{name}/trend."""
    try:
        parts = [p for p in path.split('/') if p]
        # parts[0]='api', parts[1]='industries', parts[2]=industry_name (optional), parts[3]='trend' (optional)
        industry_name = parts[2] if len(parts) > 2 else None
        sub_path = parts[3] if len(parts) > 3 else None

        # /api/industries/{name}/trend  →  daily price series for one industry
        if industry_name and sub_path == 'trend':
            return _industry_trend(cur, industry_name, params)

        # /api/industries/{name}  →  detail for one industry
        if industry_name and industry_name != 'trends-batch':
            return _industry_detail(cur, industry_name)

        # /api/industries  →  full ranked list
        return _industry_list(cur, params)

    except Exception as e:
        logger.warning(f'Industries unavailable: {e}')
        return list_response([])

def _industry_list(cur, params):
    """Return all industries ranked by composite score with price-based performance."""
    mode = 'write' if method in ['POST', 'PATCH', 'DELETE', 'PUT'] else 'read'
    
    with DatabaseContext(mode) as cur:
        limit_str = params.get('limit', [None])[0] if params else None
        limit = safe_limit(limit_str, max_val=50000, default=500)
        page_str = params.get('page', [None])[0] if params else None
        page = safe_page(page_str, default=1)
        offset = (page - 1) * limit

        cur.execute("SET statement_timeout TO '20s'")
        cur.execute("""
            WITH industry_scores AS (
                SELECT
                    cp.industry,
                    cp.sector,
                    COUNT(DISTINCT cp.ticker)           AS stock_count,
                    AVG(ss.composite_score)             AS composite_score,
                    AVG(ss.momentum_score)              AS momentum_score,
                    AVG(ss.value_score)                 AS value_score,
                    AVG(ss.quality_score)               AS quality_score,
                    AVG(ss.growth_score)                AS growth_score,
                    AVG(ss.stability_score)             AS stability_score,
                    NULL::numeric AS perf_1d,
                    NULL::numeric AS perf_5d,
                    NULL::numeric AS perf_20d
                FROM company_profile cp
                LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
                WHERE cp.industry IS NOT NULL AND TRIM(cp.industry) != ''
                GROUP BY cp.industry, cp.sector
            ),
            ranked AS (
                SELECT *,
                    RANK() OVER (ORDER BY composite_score DESC NULLS LAST) AS current_rank
                FROM industry_scores
            ),
            industry_pe AS (
                SELECT
                    cp.industry,
                    AVG(vm.pe_ratio) FILTER (WHERE vm.pe_ratio > 0 AND vm.pe_ratio < 200)  AS avg_trailing_pe,
                    AVG(vm.pb_ratio) FILTER (WHERE vm.pb_ratio > 0 AND vm.pb_ratio < 50)   AS avg_pb_ratio
                FROM value_metrics vm
                JOIN company_profile cp ON vm.symbol = cp.ticker
                WHERE cp.industry IS NOT NULL
                GROUP BY cp.industry
            ),
            industry_pe_ranked AS (
                SELECT *,
                    PERCENT_RANK() OVER (ORDER BY avg_trailing_pe ASC NULLS LAST) * 100 AS pe_percentile
                FROM industry_pe
            ),
            latest_ranking AS (
                SELECT industry, rank_1w_ago, rank_4w_ago, rank_12w_ago
                FROM industry_ranking
                WHERE date_recorded = (SELECT MAX(date_recorded) FROM industry_ranking)
            )
            SELECT r.*, ipe.avg_trailing_pe, ipe.avg_pb_ratio, ipe.pe_percentile,
                   lr.rank_1w_ago, lr.rank_4w_ago, lr.rank_12w_ago
            FROM ranked r
            LEFT JOIN industry_pe_ranked ipe ON ipe.industry = r.industry
            LEFT JOIN latest_ranking lr ON lr.industry = r.industry
            ORDER BY r.current_rank, r.stock_count DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        industries_data = cur.fetchall()
        cur.execute("""
            SELECT COUNT(DISTINCT industry) AS cnt
            FROM company_profile
            WHERE industry IS NOT NULL AND TRIM(industry) != ''
        """)
        total = int((cur.fetchone() or {}).get('cnt', 0))

        industries = []
        for idx, row in enumerate(industries_data):
            ind = dict(row)
            composite = _sf(ind.get('composite_score'))
            perf_20d = _sf(ind.get('perf_20d'))

            momentum_label = (
                'Strong'   if composite is not None and composite >= 60 else
                'Moderate' if composite is not None and composite >= 45 else
                'Weak'
            )
            trend_label = (
                'Uptrend'   if perf_20d is not None and perf_20d > 2  else
                'Downtrend' if perf_20d is not None and perf_20d < -2 else
                'Sideways'
            )

            industries.append({
                'industry':           ind.get('industry'),
                'sector':             ind.get('sector'),
                'current_rank':       int(ind.get('current_rank') or idx + 1 + offset),
                'overall_rank':       int(ind.get('current_rank') or idx + 1 + offset),
                'rank_1w_ago':        int(ind.get('rank_1w_ago')) if ind.get('rank_1w_ago') is not None else None,
                'rank_4w_ago':        int(ind.get('rank_4w_ago')) if ind.get('rank_4w_ago') is not None else None,
                'rank_12w_ago':       int(ind.get('rank_12w_ago')) if ind.get('rank_12w_ago') is not None else None,
                'stock_count':        int(ind.get('stock_count') or 0),
                'composite_score':    composite,
                'momentum_score':     _sf(ind.get('momentum_score')),
                'value_score':        _sf(ind.get('value_score')),
                'quality_score':      _sf(ind.get('quality_score')),
                'growth_score':       _sf(ind.get('growth_score')),
                'stability_score':    _sf(ind.get('stability_score')),
                'performance_1d':     _sf(ind.get('perf_1d')),
                'performance_5d':     _sf(ind.get('perf_5d')),
                'performance_20d':    perf_20d,
                'current_momentum':   momentum_label,
                'current_trend':      trend_label,
                'pe': {
                    'trailing':   _sf(ind.get('avg_trailing_pe')),
                    'forward':    _sf(ind.get('avg_forward_pe')),
                    'percentile': _sf(ind.get('pe_percentile')),
                },
            })

        freshness = check_data_freshness(cur, 'industry_ranking', 'date_recorded', warning_days=1)
        return json_response(200, {
            'items': industries,
            'total': total,
            'page':  page,
            'limit': limit,
            'data_freshness': freshness,
        })

    def _industry_detail(cur, industry_name):
        """Return detail for a single industry."""
        cur.execute("""
            SELECT
                cp.industry AS industry_name,
                COUNT(DISTINCT cp.ticker) AS stock_count,
                AVG(ss.composite_score)  AS composite_score,
                AVG(ss.momentum_score)   AS momentum_score,
                AVG(ss.value_score)      AS value_score,
                AVG(ss.quality_score)    AS quality_score,
                AVG(ss.growth_score)     AS growth_score,
                AVG(ss.stability_score)  AS stability_score
            FROM company_profile cp
            LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
            WHERE LOWER(TRIM(cp.industry)) = LOWER(TRIM(%s))
            GROUP BY cp.industry
        """, (industry_name,))
        row = cur.fetchone()
        if not row:
            return error_response(404, 'not_found', f'Industry not found: {industry_name}')

        r = dict(row)
        return json_response(200, {
            'industry_name':   r.get('industry_name'),
            'stock_count':     int(r.get('stock_count') or 0),
            'composite_score': _sf(r.get('composite_score')),
            'momentum_score':  _sf(r.get('momentum_score')),
            'value_score':     _sf(r.get('value_score')),
            'quality_score':   _sf(r.get('quality_score')),
            'growth_score':    _sf(r.get('growth_score')),
            'stability_score': _sf(r.get('stability_score')),
        })

    def _industry_trend(cur, industry_name, params):
        """Return daily price series for an industry (from price_daily, indexed to 100)."""
        days_str = params.get('days', [None])[0] if params else None
        days = safe_days(days_str, max_val=365, default=90)

        cur.execute("""
            WITH prices AS (
                SELECT
                    DATE(pd.date)                        AS date,
                    AVG(CAST(pd.close AS FLOAT))         AS avg_price,
                    COUNT(DISTINCT pd.symbol)            AS stock_count
                FROM price_daily pd
                JOIN company_profile cp ON pd.symbol = cp.ticker
                WHERE LOWER(TRIM(cp.industry)) = LOWER(TRIM(%s))
                  AND pd.date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                  AND pd.close > 0
                GROUP BY DATE(pd.date)
                ORDER BY DATE(pd.date) ASC
            )
            SELECT date, avg_price, stock_count,
                ((avg_price / NULLIF(FIRST_VALUE(avg_price) OVER (ORDER BY date), 0)) - 1) * 100
                    AS daily_strength_score
            FROM prices
            ORDER BY date ASC
        """, (industry_name, days))

        rows = cur.fetchall()
        trend_data = [
            {
                'date':               str(r['date']),
                'avgPrice':           float(r['avg_price'] or 0),
                'stockCount':         int(r['stock_count'] or 0),
                'dailyStrengthScore': float(r['daily_strength_score'] or 0),
            }
            for r in rows
        ]

        return json_response(200, {'industry': industry_name, 'trendData': trend_data})
