"""Route: industries"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    execute_with_timeout,
    extract_param,
    handle_db_error,
    json_response,
    safe_days,
    safe_json_serialize,
    safe_limit,
    safe_page,
)

from shared_contracts.response_validator import ResponseValidator

logger = logging.getLogger(__name__)


def _sf(v: Any) -> float | dict[str, Any]:
    """Safe float conversion with explicit data unavailability markers.

    Returns:
        float: converted value if successful
        dict: {"data_unavailable": True, "reason": "<reason>"} if conversion fails or value is None
    """
    if v is None:
        return {"data_unavailable": True, "reason": "value_is_none"}
    try:
        return float(v)
    except (TypeError, ValueError) as e:
        logger.debug(f"Failed to convert industry value to float: {v!r} - {e}")
        return {"data_unavailable": True, "reason": "conversion_failed"}


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/industries, /api/industries/{name}, /api/industries/{name}/trend."""
    try:
        parts = [p for p in path.split("/") if p]
        # parts[0]='api', parts[1]='industries', parts[2]=industry_name (optional), parts[3]='trend' (optional)
        industry_name = parts[2] if len(parts) > 2 else None
        sub_path = parts[3] if len(parts) > 3 else None

        # /api/industries/{name}/trend  →  daily price series for one industry
        if industry_name and sub_path == "trend":
            return _industry_trend(cur, industry_name, params)

        # /api/industries/{name}  →  detail for one industry
        if industry_name and industry_name != "trends-batch":
            return _industry_detail(cur, industry_name)

        # /api/industries  →  full ranked list
        return _industry_list(cur, params)

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Industries query failed - {type(e).__name__}: {e}",
            extra={"operation": "get industries"},
        )
        code, error_type, message = handle_db_error(e, "get industries")
        return error_response(code, error_type, message)


def _industry_list(cur: cursor, params: dict[str, Any]) -> Any:
    """Return all industries ranked by composite score with price-based performance.

    Refactored to use 4 staged queries instead of 7-CTE monolith:
    1. Base scores + ranking by composite score
    2. Price performance (1d, 5d, 20d)
    3. PE/PB ratios + percentile
    4. Historical ranks
    Then combine in Python with explicit error handling.
    """
    limit = safe_limit(extract_param(params, "limit"), max_val=50000, default=500)
    page = safe_page(extract_param(params, "page"), default=1)
    offset = (page - 1) * limit

    from utils.validation import DatabaseResultValidator

    def _extract_float(result: float | dict[str, Any]) -> float | None:
        return result if isinstance(result, float) else None

    # Try to fetch from industry_ranking table first (simpler fallback)
    try:
        cur.execute("""
            SELECT
                industry,
                current_rank,
                momentum_score,
                rank_1w_ago,
                rank_4w_ago,
                rank_12w_ago
            FROM industry_ranking
            WHERE date_recorded = (SELECT MAX(date_recorded) FROM industry_ranking)
            ORDER BY current_rank
            LIMIT %s OFFSET %s
        """, (limit, offset))

        industry_ranking_data = cur.fetchall()
        if industry_ranking_data:
            logger.info(f"[INDUSTRIES] Using simplified industry_ranking table data ({len(industry_ranking_data)} records)")

            industries = []
            for row in industry_ranking_data:
                industries.append({
                    "industry": row.get("industry", ""),
                    "sector": "",  # Not available in industry_ranking table
                    "current_rank": row.get("current_rank"),
                    "overall_rank": row.get("current_rank"),
                    "rank_1w_ago": row.get("rank_1w_ago"),
                    "rank_4w_ago": row.get("rank_4w_ago"),
                    "rank_12w_ago": row.get("rank_12w_ago"),
                    "stock_count": None,
                    "composite_score": row.get("momentum_score"),
                    "momentum_score": row.get("momentum_score"),
                    "value_score": None,
                    "quality_score": None,
                    "growth_score": None,
                    "stability_score": None,
                    "performance_1d": None,
                    "performance_5d": None,
                    "performance_20d": None,
                    "current_momentum": "Moderate",
                    "current_trend": "Sideways",
                    "pe": {"trailing": None, "percentile": None},
                })

            # Get total count
            cur.execute("SELECT COUNT(DISTINCT industry) FROM industry_ranking WHERE date_recorded = (SELECT MAX(date_recorded) FROM industry_ranking)")
            total_row = cur.fetchone()
            total = total_row["count"] if total_row else len(industries)

            freshness = check_data_freshness(cur, "industry_ranking", "date_recorded", warning_days=1)

            result = {
                "items": industries,
                "total": int(total),
                "page": page,
                "limit": limit,
                "data_freshness": freshness,
            }
            return json_response(200, result)
    except Exception as e:
        logger.warning(f"[INDUSTRIES] Fallback to industry_ranking table failed: {e}. Trying complex query.")

    # Stage 1: Get industry base scores + ranking (complex query for detailed data)
    base_scores = execute_with_timeout(
        cur,
        """
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
                AVG(ss.stability_score)             AS stability_score
            FROM company_profile cp
            LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
            WHERE cp.industry IS NOT NULL AND TRIM(cp.industry) != ''
            GROUP BY cp.industry, cp.sector
        )
        SELECT *,
            RANK() OVER (ORDER BY composite_score DESC NULLS LAST) AS current_rank
        FROM industry_scores
        ORDER BY composite_score DESC NULLS LAST, stock_count DESC
    """,
        timeout_sec=15,
    )

    # Stage 2: Get price performance by industry
    perf_data = execute_with_timeout(
        cur,
        """
        WITH latest_d AS (
            SELECT date AS d FROM price_daily ORDER BY date DESC LIMIT 1
        )
        SELECT
            cp.industry,
            ROUND(
                (AVG(CASE WHEN pd.date = (SELECT d FROM latest_d) THEN pd.close END) /
                 NULLIF(AVG(CASE WHEN pd.date BETWEEN (SELECT d FROM latest_d) - INTERVAL '3 days'
                                              AND (SELECT d FROM latest_d) - INTERVAL '1 day'
                                    THEN pd.close END), 0) - 1) * 100, 2
            ) AS perf_1d,
            ROUND(
                (AVG(CASE WHEN pd.date = (SELECT d FROM latest_d) THEN pd.close END) /
                 NULLIF(AVG(CASE WHEN pd.date BETWEEN (SELECT d FROM latest_d) - INTERVAL '8 days'
                                              AND (SELECT d FROM latest_d) - INTERVAL '5 days'
                                    THEN pd.close END), 0) - 1) * 100, 2
            ) AS perf_5d,
            ROUND(
                (AVG(CASE WHEN pd.date = (SELECT d FROM latest_d) THEN pd.close END) /
                 NULLIF(AVG(CASE WHEN pd.date BETWEEN (SELECT d FROM latest_d) - INTERVAL '25 days'
                                              AND (SELECT d FROM latest_d) - INTERVAL '18 days'
                                    THEN pd.close END), 0) - 1) * 100, 2
            ) AS perf_20d
        FROM price_daily pd
        JOIN company_profile cp ON pd.symbol = cp.ticker
        WHERE pd.date >= (SELECT d FROM latest_d) - INTERVAL '30 days'
          AND cp.industry IS NOT NULL
          AND pd.symbol NOT LIKE '^%'
        GROUP BY cp.industry
    """,
        timeout_sec=15,
    )

    # Stage 3: Get PE/PB ratios + percentile
    pe_data = execute_with_timeout(
        cur,
        """
        WITH industry_pe AS (
            SELECT
                cp.industry,
                AVG(vm.pe_ratio) FILTER (WHERE vm.pe_ratio > 0 AND vm.pe_ratio < 200)  AS avg_trailing_pe,
                AVG(vm.pb_ratio) FILTER (WHERE vm.pb_ratio > 0 AND vm.pb_ratio < 50)   AS avg_pb_ratio
            FROM value_metrics vm
            JOIN company_profile cp ON vm.symbol = cp.ticker
            WHERE cp.industry IS NOT NULL
            GROUP BY cp.industry
        )
        SELECT
            industry,
            avg_trailing_pe,
            avg_pb_ratio,
            PERCENT_RANK() OVER (ORDER BY avg_trailing_pe ASC NULLS LAST) * 100 AS pe_percentile
        FROM industry_pe
    """,
        timeout_sec=15,
    )

    # Stage 4: Get historical ranks
    rank_data = execute_with_timeout(
        cur,
        """
        SELECT industry, rank_1w_ago, rank_4w_ago, rank_12w_ago
        FROM industry_ranking
        WHERE date_recorded = (SELECT date_recorded FROM industry_ranking ORDER BY date_recorded DESC LIMIT 1)
    """,
        timeout_sec=10,
    )

    # Build lookup dictionaries for fast access
    perf_by_industry: dict[str, Any] = {}
    if perf_data:
        for row in perf_data:
            ind_name = row.get("industry")
            if ind_name:
                perf_by_industry[ind_name] = safe_json_serialize(row)

    pe_by_industry: dict[str, Any] = {}
    if pe_data:
        for row in pe_data:
            ind_name = row.get("industry")
            if ind_name:
                pe_by_industry[ind_name] = safe_json_serialize(row)

    rank_by_industry: dict[str, Any] = {}
    if rank_data:
        for row in rank_data:
            ind_name = row.get("industry")
            if ind_name:
                rank_by_industry[ind_name] = safe_json_serialize(row)

    # Count total unique industries
    total = len(base_scores) if base_scores else 0

    # Apply pagination + combine data in Python
    industries = []
    for idx, row in enumerate(base_scores):
        if idx < offset:
            continue
        if idx >= offset + limit:
            break

        ind = safe_json_serialize(row)
        industry_name = ind.get("industry")
        if not industry_name:
            continue

        composite_result = _sf(ind.get("composite_score"))
        composite = composite_result if isinstance(composite_result, float) else None

        # Fetch performance data for this industry
        perf_row = perf_by_industry.get(industry_name, {})
        perf_20d_result = _sf(perf_row.get("perf_20d"))
        perf_20d = perf_20d_result if isinstance(perf_20d_result, float) else None

        momentum_label = (
            "Strong"
            if composite is not None and composite >= 60
            else "Moderate"
            if composite is not None and composite >= 45
            else "Weak"
        )
        trend_label = (
            "Uptrend"
            if perf_20d is not None and perf_20d > 2
            else "Downtrend"
            if perf_20d is not None and perf_20d < -2
            else "Sideways"
        )

        current_rank = ind.get("current_rank")
        if current_rank is None:
            return error_response(
                503,
                "data_incomplete",
                f"Industry {industry_name} missing current_rank",
            )

        # Extract PE data
        pe_row = pe_by_industry.get(industry_name, {})
        # Extract rank data
        rank_row = rank_by_industry.get(industry_name, {})

        industry = DatabaseResultValidator.safe_get_str(ind, "industry", default="")
        sector = DatabaseResultValidator.safe_get_str(ind, "sector", default="")
        rank_1w = DatabaseResultValidator.safe_get_int(rank_row, "rank_1w_ago", default=0)
        rank_4w = DatabaseResultValidator.safe_get_int(rank_row, "rank_4w_ago", default=0)
        rank_12w = DatabaseResultValidator.safe_get_int(rank_row, "rank_12w_ago", default=0)
        stock_count = DatabaseResultValidator.safe_get_int(ind, "stock_count", default=0)

        industries.append(
            {
                "industry": industry,
                "sector": sector,
                "current_rank": int(current_rank),
                "overall_rank": int(current_rank),
                "rank_1w_ago": rank_1w if rank_1w else None,
                "rank_4w_ago": rank_4w if rank_4w else None,
                "rank_12w_ago": rank_12w if rank_12w else None,
                "stock_count": stock_count if stock_count else None,
                "composite_score": composite,
                "momentum_score": _extract_float(_sf(ind.get("momentum_score"))),
                "value_score": _extract_float(_sf(ind.get("value_score"))),
                "quality_score": _extract_float(_sf(ind.get("quality_score"))),
                "growth_score": _extract_float(_sf(ind.get("growth_score"))),
                "stability_score": _extract_float(_sf(ind.get("stability_score"))),
                "performance_1d": _extract_float(_sf(perf_row.get("perf_1d"))),
                "performance_5d": _extract_float(_sf(perf_row.get("perf_5d"))),
                "performance_20d": perf_20d,
                "current_momentum": momentum_label,
                "current_trend": trend_label,
                "pe": {
                    "trailing": _extract_float(_sf(pe_row.get("avg_trailing_pe"))),
                    "percentile": _extract_float(_sf(pe_row.get("pe_percentile"))),
                },
            }
        )

    freshness = check_data_freshness(cur, "industry_ranking", "date_recorded", warning_days=1)

    result = {
        "items": industries,
        "total": int(total) if total is not None else 0,
        "page": page,
        "limit": int(limit) if limit is not None else 500,
        "data_freshness": freshness,
    }

    is_valid, error_msg = ResponseValidator.validate_endpoint_response("industries/list", result)
    if not is_valid:
        logger.error(f"Industries list response validation failed: {error_msg}")
        return error_response(500, "response_validation_error", error_msg or "Industries list validation failed")

    return json_response(200, result)


def _industry_detail(cur: cursor, industry_name: str) -> Any:
    """Return detail for a single industry."""
    cur.execute(
        """
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
    """,
        (industry_name,),
    )
    row = cur.fetchone()
    if not row:
        return error_response(404, "not_found", f"Industry not found: {industry_name}")

    r = safe_json_serialize(row)
    freshness = check_data_freshness(cur, "stock_scores", "date", warning_days=1)

    def _extract_float(result: float | dict[str, Any]) -> float | None:
        return result if isinstance(result, float) else None

    result = {
        "industry_name": r.get("industry_name"),
        "stock_count": (int(r.get("stock_count")) if r.get("stock_count") is not None else None),
        "composite_score": _extract_float(_sf(r.get("composite_score"))),
        "momentum_score": _extract_float(_sf(r.get("momentum_score"))),
        "value_score": _extract_float(_sf(r.get("value_score"))),
        "quality_score": _extract_float(_sf(r.get("quality_score"))),
        "growth_score": _extract_float(_sf(r.get("growth_score"))),
        "stability_score": _extract_float(_sf(r.get("stability_score"))),
        "data_freshness": freshness,
    }

    is_valid, error_msg = ResponseValidator.validate_endpoint_response("industries/detail", result)
    if not is_valid:
        logger.error(f"Industries detail response validation failed: {error_msg}")
        return error_response(500, "response_validation_error", error_msg or "Industries detail validation failed")

    return json_response(200, result)


def _industry_trend(cur: cursor, industry_name: str, params: dict[str, Any]) -> Any:
    """Return daily price series for an industry (from price_daily, indexed to 100)."""
    days = safe_days(extract_param(params, "days"), max_val=365, default=90)
    limit = safe_limit(extract_param(params, "limit"), max_val=252, default=90)

    cur.execute(
        """
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
        LIMIT %s
    """,
        (industry_name, days, limit),
    )

    rows = cur.fetchall()
    from utils.validation import DatabaseResultValidator

    trend_data = []
    for r in rows:
        date_val = DatabaseResultValidator.safe_get_str(r, "date", default="")
        avg_price = DatabaseResultValidator.safe_get_float(r, "avg_price", default=0.0)
        stock_cnt = DatabaseResultValidator.safe_get_int(r, "stock_count", default=0)
        strength_score = DatabaseResultValidator.safe_get_float(r, "daily_strength_score", default=0.0)
        trend_data.append(
            {
                "date": date_val,
                "avgPrice": avg_price,
                "stockCount": stock_cnt,
                "dailyStrengthScore": strength_score,
            }
        )

    freshness = check_data_freshness(cur, "price_daily", "date", warning_days=1)
    result = {
        "industry": industry_name,
        "trendData": trend_data,
        "data_freshness": freshness,
    }

    is_valid, error_msg = ResponseValidator.validate_endpoint_response("industries/trend", result)
    if not is_valid:
        logger.error(f"Industries trend response validation failed: {error_msg}")
        return error_response(500, "response_validation_error", error_msg or "Industries trend validation failed")

    return json_response(200, result)
