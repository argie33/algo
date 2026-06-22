"""Route: sectors"""

import logging
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from routes.utils import (
    check_data_freshness,
    error_response,
    handle_db_error,
    json_response,
    list_response,
    safe_days,
    safe_json_serialize,
    safe_limit,
    safe_page,
)

from shared_contracts.response_validator import ResponseValidator


logger = logging.getLogger(__name__)


def handle(
    cur,
    path: str,
    method: str,
    params: dict,
    body: dict | None = None,
    jwt_claims: dict | None = None,
) -> dict[str, Any]:
    """Handle /api/sectors and /api/sectors/* endpoints - return full ranking data."""
    try:
        if path == "/api/sectors/trends-batch" or path.startswith("/api/sectors/trends-batch?"):
            sectors_str = params.get("sectors", [None])[0] if params else None
            days_str = params.get("days", [None])[0] if params else None
            days = safe_days(days_str or "90", max_val=365)

            if not sectors_str:
                return error_response(400, "bad_request", "sectors parameter required (comma-separated)")

            sectors = [s.strip() for s in sectors_str.split(",") if s.strip()]
            result: dict[str, Any] = {s: [] for s in sectors}

            # Set timeout for batch trends query (12s for complex aggregations)
            cur.execute("SET LOCAL statement_timeout = '12000ms'")

            if sectors:
                placeholders = ",".join(["%s"] * len(sectors))
                cur.execute(
                    f"""
                        SELECT cp.sector, pd.date, AVG(pd.close) AS "avgPrice"
                        FROM price_daily pd
                        JOIN company_profile cp ON pd.symbol = cp.ticker
                        WHERE cp.sector IN ({placeholders})
                          AND pd.date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                        GROUP BY cp.sector, pd.date
                        ORDER BY cp.sector, pd.date ASC
                    """,
                    (*tuple(sectors), days),
                )
                for row in cur.fetchall():
                    r = safe_json_serialize(dict(row))
                    sector_key = r["sector"]
                    if sector_key in result:
                        result[sector_key].append({"date": r["date"], "avgPrice": r["avgPrice"]})

            freshness = check_data_freshness(cur, "price_daily", "date", warning_days=1)
            result["data_freshness"] = freshness
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("srank", result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return error_response(500, "response_validation_error", error_msg)
            return json_response(200, result)

        # Extract sector name if provided: /api/sectors/Technology
        parts = path.split("/")
        sector_name = parts[3] if len(parts) > 3 else None

        if sector_name and sector_name not in ("performance", "trends-batch"):
            if path.endswith(("/trend", "/trend/")):
                days_str = params.get("days", [None])[0] if params else None
                days = safe_days(days_str or "90", max_val=365)
                # Set timeout for trend query (10s for window function aggregations)
                cur.execute("SET LOCAL statement_timeout = '10000ms'")
                # All camelCase aliases double-quoted so psycopg2 preserves case
                cur.execute(
                    """
                        WITH sector_daily_avg AS (
                            SELECT
                                pd.date,
                                AVG(pd.close) AS "avgPrice"
                            FROM price_daily pd
                            JOIN company_profile cp ON pd.symbol = cp.ticker
                            WHERE cp.sector = %s AND pd.date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                            GROUP BY pd.date
                        ),
                        sector_with_ma AS (
                            SELECT
                                date,
                                "avgPrice",
                                AVG("avgPrice") OVER (ORDER BY date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS ma_10,
                                AVG("avgPrice") OVER (ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma_20
                            FROM sector_daily_avg
                        )
                        SELECT
                            date,
                            "avgPrice",
                            ROUND(("avgPrice" / NULLIF(ma_10, 0) - 1) * 100, 2) AS "dailyStrengthScore",
                            ROUND((PERCENT_RANK() OVER (ORDER BY "avgPrice") * 100)::numeric, 2) AS rank,
                            ROUND((COALESCE(ma_10, 0) - COALESCE(ma_20, 0)) / NULLIF(ma_20, 0) * 100, 2) AS "momentumScore",
                            'momentum' AS momentum,
                            ROUND(COALESCE(ma_10, 0), 2) AS ma_10,
                            ROUND(COALESCE(ma_20, 0), 2) AS ma_20,
                            (ma_10 IS NULL OR ma_20 IS NULL) AS _is_fallback
                        FROM sector_with_ma
                        ORDER BY date DESC
                    """,
                    (sector_name, days),
                )
                rows = cur.fetchall()
                trend_data = (
                    [safe_json_serialize(dict(r)) for r in rows if r and r.get("avgPrice") is not None] if rows else []
                )
                freshness = check_data_freshness(cur, "price_daily", "date", warning_days=1)
                trend_result = {"trendData": trend_data, "data_freshness": freshness}
                is_valid, error_msg = ResponseValidator.validate_endpoint_response("srank", trend_result)
                if not is_valid:
                    logger.error(f"Endpoint response validation failed: {error_msg}")
                    return error_response(500, "response_validation_error", error_msg)
                return json_response(200, trend_result)
            else:
                days_str = params.get("days", [None])[0] if params else None
                days = safe_days(days_str or "90", max_val=365)
                cur.execute("SET LOCAL statement_timeout = '5000ms'")
                cur.execute(
                    """
                        SELECT date, sector, return_pct
                        FROM sector_performance
                        WHERE sector = %s AND date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                        ORDER BY date DESC
                    """,
                    (sector_name, days),
                )
                rows = cur.fetchall()
                freshness = check_data_freshness(cur, "sector_performance", "date", warning_days=1)
                return list_response([safe_json_serialize(dict(r)) for r in rows], data_freshness=freshness)
        elif path in ("/api/sectors", "/api/sectors/performance"):
            limit_str = params.get("limit", [None])[0] if params else None
            limit = safe_limit(limit_str or "50000", max_val=50000)
            page_str = params.get("page", [None])[0] if params else None
            page = safe_page(page_str or "1")
            offset = (page - 1) * limit

            # Set timeout for complex sector ranking query with multiple CTEs and joins
            cur.execute("SET LOCAL statement_timeout = '24000ms'")
            cur.execute(
                """
                    WITH sp_exists AS (
                        SELECT EXISTS(SELECT 1 FROM sector_performance LIMIT 1) AS has_data
                    ),
                    sr_exists AS (
                        SELECT EXISTS(SELECT 1 FROM sector_ranking LIMIT 1) AS has_data
                    ),
                    sector_perf_latest AS (
                        SELECT DISTINCT ON (sector) sector, return_pct AS latest_ytd
                        FROM sector_performance
                        WHERE (SELECT has_data FROM sp_exists)
                        ORDER BY sector, date DESC
                    ),
                    sector_perf_1d_prior AS (
                        SELECT DISTINCT ON (sector) sector, return_pct AS prior_1d
                        FROM sector_performance
                        WHERE date <= CURRENT_DATE - INTERVAL '1 day'
                          AND (SELECT has_data FROM sp_exists)
                        ORDER BY sector, date DESC
                    ),
                    sector_perf_5d_prior AS (
                        SELECT DISTINCT ON (sector) sector, return_pct AS prior_5d
                        FROM sector_performance
                        WHERE date <= CURRENT_DATE - INTERVAL '5 days'
                          AND (SELECT has_data FROM sp_exists)
                        ORDER BY sector, date DESC
                    ),
                    sector_perf_prior AS (
                        SELECT DISTINCT ON (sector) sector, return_pct AS prior_ytd
                        FROM sector_performance
                        WHERE date <= CURRENT_DATE - INTERVAL '20 days'
                          AND (SELECT has_data FROM sp_exists)
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
                        UNION ALL
                        SELECT DISTINCT cp.sector, 0 AS perf_1d, 0 AS perf_5d, 0 AS perf_20d
                        FROM company_profile cp
                        WHERE NOT (SELECT has_data FROM sp_exists)
                          AND cp.sector IS NOT NULL
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
                            sp.perf_1d,
                            sp.perf_5d,
                            sp.perf_20d,
                            (sp.sector IS NULL) as _is_fallback
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
                        LEFT JOIN sector_perf sp ON sp.sector = cp.sector
                        WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) != ''
                        GROUP BY cp.sector, sp.perf_1d, sp.perf_5d, sp.perf_20d, sp.sector
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
                        SELECT DISTINCT ON (sector_name) sector_name, rank_1w_ago, rank_4w_ago, rank_12w_ago
                        FROM sector_ranking
                        WHERE (SELECT has_data FROM sr_exists)
                        ORDER BY sector_name, created_at DESC
                    )
                    SELECT r.*, spe.avg_trailing_pe, spe.avg_pb_ratio, spe.pe_percentile,
                           sr.rank_1w_ago, sr.rank_4w_ago, sr.rank_12w_ago
                    FROM ranked r
                    LEFT JOIN sector_pe_ranked spe ON spe.sector = r.sector_name
                    LEFT JOIN latest_sector_ranking sr ON sr.sector_name = r.sector_name
                    ORDER BY r.current_rank, r.stock_count DESC
                    LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )

            sectors_data = cur.fetchall()
            cur.execute("""SELECT COUNT(DISTINCT sector) as cnt FROM company_profile WHERE sector IS NOT NULL""")
            total = safe_json_serialize(dict(cur.fetchone())).get("cnt", 0)

            sectors = []
            for row in sectors_data:
                s = safe_json_serialize(dict(row))
                composite_val = s.get("composite_score")
                composite = float(composite_val)
                perf1d_val = s.get("perf_1d")
                perf1d = float(perf1d_val)
                perf5d_val = s.get("perf_5d")
                perf5d = float(perf5d_val)
                perf20d_val = s.get("perf_20d")
                perf20d = float(perf20d_val)
                if composite is not None:
                    if composite >= 60:
                        momentum_label = "Strong"
                    elif composite >= 45:
                        momentum_label = "Moderate"
                    else:
                        momentum_label = "Weak"
                else:
                    momentum_label = None

                if perf20d is not None:
                    if perf20d > 2:
                        trend_label = "Uptrend"
                    elif perf20d < -2:
                        trend_label = "Downtrend"
                    else:
                        trend_label = "Sideways"
                else:
                    trend_label = None

                rank_val = s.get("current_rank")
                stock_count_val = s.get("stock_count")
                momentum_score_val = s.get("momentum_score")
                value_score_val = s.get("value_score")
                quality_score_val = s.get("quality_score")
                growth_score_val = s.get("growth_score")
                stability_score_val = s.get("stability_score")
                trailing_pe_val = s.get("avg_trailing_pe")
                pb_ratio_val = s.get("avg_pb_ratio")
                pe_percentile_val = s.get("pe_percentile")

                sectors.append(
                    {
                        "sector_name": s.get("sector_name"),
                        "current_rank": int(rank_val),
                        "rank_1w_ago": (int(s["rank_1w_ago"]) if s.get("rank_1w_ago") is not None else None),
                        "rank_4w_ago": (int(s["rank_4w_ago"]) if s.get("rank_4w_ago") is not None else None),
                        "rank_12w_ago": (int(s["rank_12w_ago"]) if s.get("rank_12w_ago") is not None else None),
                        "stock_count": (int(stock_count_val) if stock_count_val is not None else None),
                        "composite_score": composite,
                        "momentum_score": (float(momentum_score_val) if momentum_score_val is not None else None),
                        "value_score": (float(value_score_val) if value_score_val is not None else None),
                        "quality_score": (float(quality_score_val) if quality_score_val is not None else None),
                        "growth_score": (float(growth_score_val) if growth_score_val is not None else None),
                        "stability_score": (float(stability_score_val) if stability_score_val is not None else None),
                        "current_momentum": momentum_label,
                        "current_trend": trend_label,
                        "performance_1d": perf1d,
                        "performance_5d": perf5d,
                        "performance_20d": perf20d,
                        "pe": {
                            "trailing": (float(trailing_pe_val) if trailing_pe_val is not None else None),
                            "pb_ratio": (float(pb_ratio_val) if pb_ratio_val is not None else None),
                            "percentile": (float(pe_percentile_val) if pe_percentile_val is not None else None),
                        },
                    }
                )

            freshness = check_data_freshness(cur, "sector_ranking", "date", warning_days=1)
            sector_result = {
                "items": sectors,
                "total": total,
                "page": page,
                "limit": limit,
                "data_freshness": freshness,
            }
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("srank", sector_result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return error_response(500, "response_validation_error", error_msg)
            return json_response(200, sector_result)
        elif "/trend" in path:
            parts = path.split("/")
            sector_name = parts[3] if len(parts) > 3 else None
            days_str = params.get("days", [None])[0] if params else None
            days = safe_days(days_str or "90", max_val=365)
            if not sector_name:
                return error_response(400, "bad_request", "Sector name required")
            cur.execute("SET LOCAL statement_timeout = '10000ms'")
            cur.execute(
                """
                    SELECT date, sector, return_pct, relative_strength
                    FROM sector_performance
                    WHERE sector = %s AND date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                    ORDER BY date DESC
                """,
                (sector_name, days),
            )
            rows = cur.fetchall()
            return list_response([safe_json_serialize(dict(r)) for r in rows])
        return error_response(404, "not_found", f"No sector handler for {path}")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle sectors")
        return error_response(code, error_type, message)
