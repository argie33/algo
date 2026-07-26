"""Route: sectors"""

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
    list_response,
    safe_days,
    safe_json_serialize,
    safe_limit,
    safe_page,
)

from algo.infrastructure.config.sql_intervals import get_interval_sql
from shared_contracts.response_validator import ResponseValidator
from utils.db.sql_split_guard import split_guard_sql

logger = logging.getLogger(__name__)


def handle(  # noqa: C901
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/sectors and /api/sectors/* endpoints - return full ranking data."""
    try:
        if path == "/api/sectors/trends-batch" or path.startswith("/api/sectors/trends-batch?"):
            sectors_str = extract_param(params, "sectors")
            days = safe_days(extract_param(params, "days"), max_val=365, default=90)

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
                        JOIN company_profile cp ON pd.symbol = cp.symbol
                        WHERE cp.sector IN ({placeholders})
                          AND pd.date >= CURRENT_DATE - (%s || ' days')::interval
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
                if error_msg:
                    return error_response(500, "response_validation_error", error_msg)
                else:
                    logger.error("[CRITICAL] Sector ranking validation failed but error_msg is None. Bug.")
                    return error_response(
                        500,
                        "response_validation_error",
                        "Sector ranking validation failed (internal error: no message)",
                    )
            return json_response(200, result)

        # Extract sector name if provided: /api/sectors/Technology
        parts = path.split("/")
        sector_name = parts[3] if len(parts) > 3 else None

        if sector_name and sector_name not in ("performance", "trends-batch"):
            if path.endswith(("/trend", "/trend/")):
                days = safe_days(extract_param(params, "days"), max_val=365, default=90)
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
                            JOIN company_profile cp ON pd.symbol = cp.symbol
                            WHERE cp.sector = %s AND pd.date >= CURRENT_DATE - (%s || ' days')::interval
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
                            -- CRITICAL: Return NULL for moving averages instead of 0 when data is missing
                            -- This prevents meaningless momentum scores from missing MA data
                            CASE WHEN ma_10 IS NOT NULL AND ma_20 IS NOT NULL
                              THEN ROUND((ma_10 - ma_20) / NULLIF(ma_20, 0) * 100, 2)
                              ELSE NULL
                            END AS "momentumScore",
                            'momentum' AS momentum,
                            ROUND(ma_10, 2) AS ma_10,
                            ROUND(ma_20, 2) AS ma_20,
                            (ma_10 IS NULL OR ma_20 IS NULL) AS _is_fallback
                        FROM sector_with_ma
                        WHERE ma_10 IS NOT NULL AND ma_20 IS NOT NULL
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
                days = safe_days(extract_param(params, "days"), max_val=365, default=90)
                cur.execute("SET LOCAL statement_timeout = '5000ms'")
                # Computed from price_daily grouped by company_profile.sector (GICS), same fix as
                # the /trend branch above and the main /api/sectors listing below - sector_performance
                # rows are keyed by fine-grained SEC SIC-description names (e.g. "Adhesives & Sealants"),
                # not the broad GICS categories ("Utilities", "Technology", ...) this route's
                # `sector_name` argument uses, so `WHERE sector = %s` here never matched a real GICS
                # name and always returned an empty series.
                cur.execute(
                    """
                        WITH sector_daily_avg AS (
                            SELECT pd.date, AVG(pd.close) AS avg_close
                            FROM price_daily pd
                            JOIN company_profile cp ON pd.symbol = cp.symbol
                            WHERE cp.sector = %s
                              AND pd.date >= CURRENT_DATE - ((%s::int + 1) || ' days')::interval
                            GROUP BY pd.date
                        ),
                        sector_returns AS (
                            SELECT date,
                                   ROUND(((avg_close - LAG(avg_close) OVER (ORDER BY date))
                                          / NULLIF(LAG(avg_close) OVER (ORDER BY date), 0) * 100)::numeric, 4)
                                       AS return_pct
                            FROM sector_daily_avg
                        )
                        SELECT date, %s AS sector, return_pct
                        FROM sector_returns
                        WHERE date >= CURRENT_DATE - (%s || ' days')::interval
                          AND return_pct IS NOT NULL
                        ORDER BY date DESC
                    """,
                    (sector_name, days, sector_name, days),
                )
                rows = cur.fetchall()
                freshness = check_data_freshness(cur, "price_daily", "date", warning_days=1)
                return list_response(
                    [safe_json_serialize(dict(r)) for r in rows],
                    data_freshness=freshness,
                )
        elif path in ("/api/sectors", "/api/sectors/performance"):
            limit = safe_limit(extract_param(params, "limit"), max_val=50000, default=50000)
            page = safe_page(extract_param(params, "page"), default=1)
            offset = (page - 1) * limit

            # Set timeout for complex sector ranking query with multiple CTEs and joins
            cur.execute("SET LOCAL statement_timeout = '24000ms'")
            interval_1d = get_interval_sql("1d")
            cur.execute(
                f"""
                    WITH sr_exists AS (
                        SELECT EXISTS(SELECT 1 FROM sector_ranking LIMIT 1) AS has_data
                    ),
                    -- Computed directly from price_daily grouped by company_profile.sector (GICS),
                    -- NOT from sector_performance.return_pct: sector_performance's loader writes
                    -- fine-grained SEC SIC-description sector names (e.g. "Adhesives & Sealants"),
                    -- a deliberate fix for company_profile.sector being mostly "Unknown" - see
                    -- loaders/load_sector_industry_daily.py's own comment on why sector_ranking
                    -- avoids that same switch. But this endpoint's sector_scores CTE below groups
                    -- by cp.sector (the broad GICS-style categories like "Utilities", "Technology"),
                    -- so joining it against SIC-taxonomy sector_performance rows only ever matched
                    -- by coincidence (confirmed live 2026-07-20: only "Unknown" and "Real Estate"
                    -- matched out of 13 sectors) - every other sector fell back to the LAST row that
                    -- ever matched under the old GICS-writing loader (frozen since 2026-07-10), so
                    -- latest/prior always resolved to the same stale snapshot and perf_1d/5d/20d
                    -- rounded to ~0.00 for nearly every sector on every run since the loader switch.
                    sector_perf AS (
                        -- The split-ratio guards below exclude a stock's return for a window from the
                        -- sector average if its two closes look like a clean stock split (e.g. a 2-for-1
                        -- reads as a fake single-stock loss of half its value) - see
                        -- utils/db/sql_split_guard.py. price_daily stores raw/unadjusted prices, so
                        -- without this a single recently-split stock can silently drag an entire
                        -- sector's reported performance far off its real value.
                        -- CAUTION: no SQL comment in this psycopg2-parameterized query string may
                        -- contain the percent-sign character - psycopg2 scans the whole query text,
                        -- including comments, for placeholder markers, and one stray percent sign
                        -- anywhere throws IndexError at execute() time (see git history on this line).
                        SELECT cp.sector AS sector,
                               ROUND((AVG(CASE WHEN p1.close IS NOT NULL AND p1.close != 0
                                    AND {split_guard_sql("p1.close", "pnow.close")}
                                    THEN (pnow.close - p1.close) / p1.close * 100 END))::numeric, 2) AS perf_1d,
                               ROUND((AVG(CASE WHEN p5.close IS NOT NULL AND p5.close != 0
                                    AND {split_guard_sql("p5.close", "pnow.close")}
                                    THEN (pnow.close - p5.close) / p5.close * 100 END))::numeric, 2) AS perf_5d,
                               ROUND((AVG(CASE WHEN p20.close IS NOT NULL AND p20.close != 0
                                    AND {split_guard_sql("p20.close", "pnow.close")}
                                    THEN (pnow.close - p20.close) / p20.close * 100 END))::numeric, 2) AS perf_20d
                        FROM company_profile cp
                        JOIN LATERAL (
                            SELECT close FROM price_daily
                            WHERE symbol = cp.symbol ORDER BY date DESC LIMIT 1
                        ) pnow ON TRUE
                        LEFT JOIN LATERAL (
                            SELECT close FROM price_daily
                            WHERE symbol = cp.symbol AND date <= CURRENT_DATE - {interval_1d}
                            ORDER BY date DESC LIMIT 1
                        ) p1 ON TRUE
                        LEFT JOIN LATERAL (
                            SELECT close FROM price_daily
                            WHERE symbol = cp.symbol AND date <= CURRENT_DATE - INTERVAL '5 days'
                            ORDER BY date DESC LIMIT 1
                        ) p5 ON TRUE
                        LEFT JOIN LATERAL (
                            SELECT close FROM price_daily
                            WHERE symbol = cp.symbol AND date <= CURRENT_DATE - INTERVAL '20 days'
                            ORDER BY date DESC LIMIT 1
                        ) p20 ON TRUE
                        WHERE cp.sector IS NOT NULL
                        GROUP BY cp.sector
                    ),
                    sector_scores AS (
                        SELECT
                            cp.sector as sector_name,
                            COUNT(DISTINCT cp.symbol) as stock_count,
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
                        LEFT JOIN stock_scores ss ON cp.symbol = ss.symbol
                        LEFT JOIN sector_perf sp ON sp.sector = cp.sector
                        WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) != '' AND cp.sector != 'Unknown'
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
                        JOIN company_profile cp ON vm.symbol = cp.symbol
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

            # CRITICAL: Verify data is available (not using fallback zeros)
            if not sectors_data:
                logger.error(
                    "[SECTORS_API] No sector performance data available - sector_performance table may be empty"
                )
                return error_response(
                    503,
                    "sector_data_unavailable",
                    "Sector performance data not available. Sector ranking pipeline may not have completed.",
                )
            cur.execute("""SELECT COUNT(DISTINCT sector) as cnt FROM company_profile WHERE sector IS NOT NULL""")
            count_row = cur.fetchone()
            if count_row is None:
                return error_response(503, "data_unavailable", "Sector count query failed - database unavailable")
            count_dict = safe_json_serialize(dict(count_row))
            total = count_dict.get("cnt")
            if total is None or total <= 0:
                return error_response(503, "no_sectors_available", "No sector data available in database")

            sectors_list: list[dict[str, Any]] = []
            for row in sectors_data:
                s = safe_json_serialize(dict(row))
                # CRITICAL: Check if this sector is using fallback data (missing perf from sector_performance)
                # Skip check for "Unknown" sector - it's an edge case with no market data
                is_fallback = s.get("_is_fallback")
                sector_name = s.get("sector_name")
                if is_fallback and sector_name and sector_name != "Unknown":
                    logger.error(f"[SECTORS_API] Sector performance data missing for {sector_name} - using fallback")
                    return error_response(
                        503,
                        "sector_perf_fallback",
                        f"Sector performance data incomplete for {sector_name}",
                    )

                # FAIL-FAST: Extract float fields upfront, check None before float() conversion
                from utils.validation import DatabaseResultValidator

                composite = DatabaseResultValidator.safe_get_float(s, "composite_score", default=None)
                perf1d = DatabaseResultValidator.safe_get_float(s, "perf_1d", default=None)
                perf5d = DatabaseResultValidator.safe_get_float(s, "perf_5d", default=None)
                perf20d = DatabaseResultValidator.safe_get_float(s, "perf_20d", default=None)
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

                # FAIL-FAST: Extract all required fields upfront with safe validation
                rank = DatabaseResultValidator.safe_get_int(s, "current_rank")
                rank_1w = DatabaseResultValidator.safe_get_int(s, "rank_1w_ago", default=None)
                rank_4w = DatabaseResultValidator.safe_get_int(s, "rank_4w_ago", default=None)
                rank_12w = DatabaseResultValidator.safe_get_int(s, "rank_12w_ago", default=None)
                stock_count = DatabaseResultValidator.safe_get_int(s, "stock_count", default=None)
                momentum_score = DatabaseResultValidator.safe_get_float(s, "momentum_score", default=None)
                value_score = DatabaseResultValidator.safe_get_float(s, "value_score", default=None)
                quality_score = DatabaseResultValidator.safe_get_float(s, "quality_score", default=None)
                growth_score = DatabaseResultValidator.safe_get_float(s, "growth_score", default=None)
                stability_score = DatabaseResultValidator.safe_get_float(s, "stability_score", default=None)
                trailing_pe = DatabaseResultValidator.safe_get_float(s, "avg_trailing_pe", default=None)
                pb_ratio = DatabaseResultValidator.safe_get_float(s, "avg_pb_ratio", default=None)
                pe_percentile = DatabaseResultValidator.safe_get_float(s, "pe_percentile", default=None)
                sector_name = DatabaseResultValidator.safe_get_str(s, "sector_name", default=None)

                sectors_list.append(
                    {
                        "sector_name": sector_name,
                        "current_rank": rank,
                        "rank_1w_ago": rank_1w,
                        "rank_4w_ago": rank_4w,
                        "rank_12w_ago": rank_12w,
                        "stock_count": stock_count,
                        "composite_score": composite,
                        "momentum_score": momentum_score,
                        "value_score": value_score,
                        "quality_score": quality_score,
                        "growth_score": growth_score,
                        "stability_score": stability_score,
                        "current_momentum": momentum_label,
                        "current_trend": trend_label,
                        "performance_1d": perf1d,
                        "performance_5d": perf5d,
                        "performance_20d": perf20d,
                        "pe": {
                            "trailing": trailing_pe,
                            "pb_ratio": pb_ratio,
                            "percentile": pe_percentile,
                        },
                    }
                )

            freshness = check_data_freshness(cur, "sector_ranking", "date", warning_days=1)
            offset = (page - 1) * limit
            sector_result = {
                "items": sectors_list,
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
            days = safe_days(extract_param(params, "days"), max_val=365, default=90)
            if not sector_name:
                return error_response(400, "bad_request", "Sector name required")
            cur.execute("SET LOCAL statement_timeout = '10000ms'")
            interval_1d_trend = get_interval_sql("1d")
            cur.execute(
                f"""
                    SELECT date, sector, return_pct, relative_strength
                    FROM sector_performance
                    WHERE sector = %s AND date >= CURRENT_DATE - (%s * {interval_1d_trend})
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
