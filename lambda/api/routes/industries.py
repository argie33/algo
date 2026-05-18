"""Route: industries"""
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

def _handle_industries(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/industries and /api/industries/{name} - return ranking data."""
        try:
            # Extract industry name if provided: /api/industries/Software
            parts = path.split('/')
            industry_name = parts[3] if len(parts) > 3 else None

            if industry_name and industry_name != 'trend':
                # Return data for specific industry
                days_str = params.get('days', [None])[0] if params else None
                days = _safe_days(days_str, max_val=365, default=90)
                cur.execute("""
                    SELECT date, industry, return_pct
                    FROM industry_performance
                    WHERE industry = %s AND date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                    ORDER BY date DESC
                """, (industry_name, days))
                rows = cur.fetchall()
                return list_response([dict(r) for r in rows])
            else:
                limit_str = params.get('limit', [None])[0] if params else None
                limit = _safe_limit(limit_str, max_val=50000, default=50000)
                page_str = params.get('page', [None])[0] if params else None
                page = _safe_page(page_str, default=1)
                offset = (page - 1) * limit

                cur.execute("""
                    WITH industry_perf AS (
                        SELECT industry,
                               ROUND(SUM(CASE WHEN return_pct > 0 THEN return_pct ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as perf_20d
                        FROM industry_performance
                        WHERE date >= CURRENT_DATE - INTERVAL '20 days'
                        GROUP BY industry
                    ),
                    industry_scores AS (
                        SELECT
                            cp.industry,
                            cp.sector,
                            COUNT(DISTINCT cp.symbol) as stock_count,
                            AVG(ss.composite_score) as composite_score,
                            AVG(ss.momentum_score) as momentum_score,
                            AVG(ss.value_score) as value_score,
                            AVG(ss.quality_score) as quality_score,
                            AVG(ss.growth_score) as growth_score,
                            AVG(ss.stability_score) as stability_score,
                            COALESCE(ip.perf_20d, 0) as perf_20d
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.symbol = ss.symbol
                        LEFT JOIN industry_perf ip ON ip.industry = cp.industry
                        WHERE cp.industry IS NOT NULL AND TRIM(cp.industry) != ''
                        GROUP BY cp.industry, cp.sector, ip.perf_20d
                    ),
                    ranked AS (
                        SELECT *,
                            RANK() OVER (ORDER BY composite_score DESC NULLS LAST) as current_rank
                        FROM industry_scores
                    ),
                    industry_pe AS (
                        SELECT
                            cp.industry,
                            AVG(vm.pe_ratio) FILTER (WHERE vm.pe_ratio > 0 AND vm.pe_ratio < 200) AS avg_trailing_pe,
                            0::float AS avg_forward_pe
                        FROM value_metrics vm
                        JOIN company_profile cp ON vm.symbol = cp.ticker
                        WHERE cp.industry IS NOT NULL
                        GROUP BY cp.industry
                    ),
                    industry_pe_ranked AS (
                        SELECT *,
                            PERCENT_RANK() OVER (ORDER BY avg_trailing_pe ASC NULLS LAST) * 100 AS pe_percentile
                        FROM industry_pe
                    )
                    SELECT r.*, ipe.avg_trailing_pe, ipe.avg_forward_pe, ipe.pe_percentile
                    FROM ranked r
                    LEFT JOIN industry_pe_ranked ipe ON ipe.industry = r.industry
                    ORDER BY r.current_rank, r.stock_count DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))

                industries_data = cur.fetchall()
                cur.execute("""SELECT COUNT(DISTINCT industry) FROM company_profile WHERE industry IS NOT NULL""")
                total = cur.fetchone()[0]

                industries = []
                for row in industries_data:
                    ind = dict(row)
                    composite = float(ind.get('composite_score') or 0)
                    perf20d = float(ind.get('perf_20d') or 0)
                    momentum_label = 'Strong' if composite >= 60 else 'Moderate' if composite >= 45 else 'Weak'
                    trend_label = 'Uptrend' if perf20d > 2 else 'Downtrend' if perf20d < -2 else 'Sideways'

                    industries.append({
                        'industry': ind.get('industry'),
                        'sector': ind.get('sector'),
                        'current_rank': int(ind.get('current_rank') or 0),
                        'stock_count': int(ind.get('stock_count') or 0),
                        'composite_score': float(ind.get('composite_score') or 0),
                        'momentum_score': float(ind.get('momentum_score') or 0),
                        'value_score': float(ind.get('value_score') or 0),
                        'quality_score': float(ind.get('quality_score') or 0),
                        'growth_score': float(ind.get('growth_score') or 0),
                        'stability_score': float(ind.get('stability_score') or 0),
                        'current_momentum': momentum_label,
                        'current_trend': trend_label,
                        'pe': {
                            'trailing': float(ind.get('avg_trailing_pe') or 0),
                            'forward': float(ind.get('avg_forward_pe') or 0),
                            'percentile': float(ind.get('pe_percentile') or 0)
                        }
                    })

                return json_response(200, {
                    'data': industries,
                    'total': total,
                    'page': page,
                    'limit': limit,
                })
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'handle industries'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'handle industries'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'handle industries'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'handle industries', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'handle industries', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch industries')
