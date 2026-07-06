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
    """Return all industries ranked by composite score from industry_ranking table.

    Uses precomputed industry_ranking table populated by EOD loader (depends on stock_scores).
    Table contains rankings, momentum scores, and historical rank changes.
    """
    try:
        limit = safe_limit(extract_param(params, "limit"), max_val=50000, default=500)
        page = safe_page(extract_param(params, "page"), default=1)
        offset = (page - 1) * limit

        # Validate offset is non-negative and reasonable
        if offset < 0:
            return error_response(400, "invalid_offset", "Offset must be non-negative")
        if limit < 1:
            return error_response(400, "invalid_limit", "Limit must be at least 1")

    except Exception as e:
        logger.error(f"[INDUSTRIES] Parameter validation failed: {type(e).__name__}: {e}")
        return error_response(400, "parameter_error", f"Invalid parameters: {str(e)[:100]}")

    from utils.validation import DatabaseResultValidator

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
    except Exception as e:
        logger.error(f"[INDUSTRIES] Database query failed: {type(e).__name__}: {e}")
        return error_response(
            503,
            "query_error",
            f"Failed to fetch industry rankings: {str(e)[:100]}",
        )

    if not industry_ranking_data:
        return error_response(
            503,
            "data_unavailable",
            "No industry ranking data available. Loader may not have run yet.",
        )

    logger.info(f"[INDUSTRIES] Loaded {len(industry_ranking_data)} industries from industry_ranking table")

    industries = []
    for row in industry_ranking_data:
        industry = DatabaseResultValidator.safe_get_str(row, "industry", default="")
        current_rank = DatabaseResultValidator.safe_get_int(row, "current_rank", default=0)
        momentum = DatabaseResultValidator.safe_get_float(row, "momentum_score", default=0.0)
        rank_1w = DatabaseResultValidator.safe_get_int(row, "rank_1w_ago", default=0)
        rank_4w = DatabaseResultValidator.safe_get_int(row, "rank_4w_ago", default=0)
        rank_12w = DatabaseResultValidator.safe_get_int(row, "rank_12w_ago", default=0)

        momentum_label = (
            "Strong" if momentum is not None and momentum >= 60
            else "Moderate" if momentum is not None and momentum >= 45
            else "Weak"
        )

        industries.append({
            "industry": industry,
            "sector": "",
            "current_rank": current_rank,
            "overall_rank": current_rank,
            "rank_1w_ago": rank_1w if rank_1w else None,
            "rank_4w_ago": rank_4w if rank_4w else None,
            "rank_12w_ago": rank_12w if rank_12w else None,
            "stock_count": None,
            "composite_score": momentum,
            "momentum_score": momentum,
            "value_score": None,
            "quality_score": None,
            "growth_score": None,
            "stability_score": None,
            "performance_1d": None,
            "performance_5d": None,
            "performance_20d": None,
            "current_momentum": momentum_label,
            "current_trend": "Sideways",
            "pe": {"trailing": None, "percentile": None},
        })

    cur.execute("SELECT COUNT(DISTINCT industry) FROM industry_ranking WHERE date_recorded = (SELECT MAX(date_recorded) FROM industry_ranking)")
    total_row = cur.fetchone()
    total = total_row["count"] if total_row else len(industries)

    try:
        freshness = check_data_freshness(cur, "industry_ranking", "date_recorded", warning_days=1)
    except Exception as e:
        logger.warning(f"[INDUSTRIES] Could not check data freshness: {e}. Using safe default.")
        freshness = {"data_age_days": None, "is_stale": False, "warning": None}

    result = {
        "items": industries,
        "total": int(total),
        "page": page,
        "limit": limit,
        "data_freshness": freshness,
    }

    # Validate response structure
    is_valid, error_msg = ResponseValidator.validate_endpoint_response("industries/list", result)
    if not is_valid:
        logger.error(f"Industries list response validation failed: {error_msg}")
        return error_response(500, "response_validation_error", error_msg or "Response validation failed")

    return json_response(200, result)


def _industry_detail(cur: cursor, industry_name: str) -> Any:
    """Return detail for a single industry."""
    if not industry_name or not isinstance(industry_name, str):
        return error_response(400, "invalid_industry_name", "Industry name is required and must be a string")

    try:
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
    except Exception as e:
        logger.error(f"[INDUSTRIES] Detail query failed for {industry_name}: {type(e).__name__}: {e}")
        return error_response(503, "query_error", f"Failed to fetch industry detail: {str(e)[:100]}")

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
        if error_msg:
            return error_response(500, "response_validation_error", error_msg)
        else:
            logger.error("[CRITICAL] Industries detail validation failed but error_msg is None. Bug.")
            return error_response(500, "response_validation_error", "Industries detail validation failed (internal error: no message)")

    return json_response(200, result)


def _industry_trend(cur: cursor, industry_name: str, params: dict[str, Any]) -> Any:
    """Return daily price series for an industry (from price_daily, indexed to 100)."""
    if not industry_name or not isinstance(industry_name, str):
        return error_response(400, "invalid_industry_name", "Industry name is required and must be a string")

    try:
        days = safe_days(extract_param(params, "days"), max_val=365, default=90)
        limit = safe_limit(extract_param(params, "limit"), max_val=252, default=90)
    except Exception as e:
        logger.error(f"[INDUSTRIES] Trend parameter validation failed: {type(e).__name__}: {e}")
        return error_response(400, "parameter_error", f"Invalid parameters: {str(e)[:100]}")

    try:
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
    except Exception as e:
        logger.error(f"[INDUSTRIES] Trend query failed for {industry_name}: {type(e).__name__}: {e}")
        return error_response(503, "query_error", f"Failed to fetch industry trend: {str(e)[:100]}")
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
        if error_msg:
            return error_response(500, "response_validation_error", error_msg)
        else:
            logger.error("[CRITICAL] Industries trend validation failed but error_msg is None. Bug.")
            return error_response(500, "response_validation_error", "Industries trend validation failed (internal error: no message)")

    return json_response(200, result)
