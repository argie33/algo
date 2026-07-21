"""Route: algo"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    list_response,
    raise_api_error,
    safe_dict_convert,
    safe_json_serialize,
    success_response,
    validate_api_response,
)

from algo.infrastructure.config.sql_intervals import get_interval_sql
from shared_contracts.response_validator import ResponseValidator

logger = logging.getLogger(__name__)


@db_route_handler("get algo evaluate")  # type: ignore[untyped-decorator]
@validate_api_response("sig_eval")  # type: ignore[untyped-decorator]
def _get_algo_evaluate(cur: cursor) -> Any:
    """Get comprehensive signal evaluation with candidate analysis and constraints.

    SWING SCORE REMOVAL: This endpoint has been retired. The swing_trader_scores
    table no longer exists and has been retired in favor of composite_score from
    stock_scores table. Returns 503 to indicate endpoint is no longer available.
    """
    raise_api_error(
        503,
        "deprecated_data_source",
        "Signal evaluation endpoint has been retired. "
        "The swing_trader_scores table is no longer maintained. "
        "Use stock_scores table with composite_score column instead.",
    )


@db_route_handler("get sector breadth")  # type: ignore[untyped-decorator]
@validate_api_response("srank")  # type: ignore[untyped-decorator]
def _get_sector_breadth(cur: cursor) -> Any:
    """Get sector breadth indicators: % of stocks above 50-day and 200-day moving averages.

    Uses pre-computed sma_50/sma_200 from technical_data_daily (populated daily by vectorized loader).
    """
    try:
        # SAVEPOINT isolation: a timeout here must not abort the outer transaction
        # and break subsequent API requests in the same Lambda.
        cur.execute("SAVEPOINT sector_breadth_check")
        interval_7d = get_interval_sql("7d")
        cur.execute(f"""
                WITH latest_tech AS (
                    SELECT DISTINCT ON (td.symbol)
                        td.symbol, td.sma_50, td.sma_200
                    FROM technical_data_daily td
                    WHERE td.date >= CURRENT_DATE - {interval_7d}
                    ORDER BY td.symbol, td.date DESC
                ),
                latest_price AS (
                    SELECT DISTINCT ON (pd.symbol)
                        pd.symbol, pd.close
                    FROM price_daily pd
                    WHERE pd.date >= CURRENT_DATE - {interval_7d}
                      AND pd.symbol NOT LIKE '^%'
                    ORDER BY pd.symbol, pd.date DESC
                ),
                distinct_symbols AS (
                    SELECT DISTINCT ON (lt.symbol)
                        lt.symbol, lp.close, lt.sma_50, lt.sma_200, cp.sector
                    FROM latest_tech lt
                    JOIN latest_price lp ON lt.symbol = lp.symbol
                    JOIN company_profile cp ON lt.symbol = cp.ticker
                    WHERE cp.sector IS NOT NULL
                    ORDER BY lt.symbol
                ),
                sector_breadth AS (
                    SELECT
                        sector,
                        COUNT(symbol) AS total_symbol_count,
                        COUNT(symbol) FILTER (WHERE sma_50 IS NOT NULL AND close IS NOT NULL) AS symbols_with_50d,
                        COUNT(symbol) FILTER (WHERE sma_200 IS NOT NULL AND close IS NOT NULL) AS symbols_with_200d,
                        COUNT(symbol) FILTER (WHERE close IS NOT NULL AND sma_50 IS NOT NULL AND close > sma_50) * 100.0 /
                            NULLIF(COUNT(symbol) FILTER (WHERE sma_50 IS NOT NULL AND close IS NOT NULL), 0) AS pct_above_50d,
                        COUNT(symbol) FILTER (WHERE close IS NOT NULL AND sma_200 IS NOT NULL AND close > sma_200) * 100.0 /
                            NULLIF(COUNT(symbol) FILTER (WHERE sma_200 IS NOT NULL AND close IS NOT NULL), 0) AS pct_above_200d
                    FROM distinct_symbols
                    GROUP BY sector
                )
                SELECT
                    sector,
                    -- CRITICAL: Return NULL instead of 0 - _is_fallback marker indicates missing data
                    ROUND(pct_above_50d::NUMERIC, 2) AS pct_above_50d,
                    ROUND(pct_above_200d::NUMERIC, 2) AS pct_above_200d,
                    (pct_above_50d IS NULL OR pct_above_200d IS NULL) AS _is_fallback,
                    -- Symbol coverage: track what percentage of sector symbols have valid price/technical data
                    ROUND(100.0 * symbols_with_50d / total_symbol_count::NUMERIC, 1) AS symbol_coverage_50d_pct,
                    ROUND(100.0 * symbols_with_200d / total_symbol_count::NUMERIC, 1) AS symbol_coverage_200d_pct
                FROM sector_breadth
                WHERE pct_above_50d IS NOT NULL OR pct_above_200d IS NOT NULL
                ORDER BY pct_above_50d DESC NULLS LAST
            """)
        breadth = cur.fetchall()
        cur.execute("RELEASE SAVEPOINT sector_breadth_check")

        # CRITICAL: Validate all required fields are present in every row (Issue #8 fix)
        # Missing fields indicate upstream data quality issues that should be surfaced
        required_fields = {"sector", "pct_above_50d", "pct_above_200d", "_is_fallback", "symbol_coverage_50d_pct", "symbol_coverage_200d_pct"}
        breadth_data = []
        for row in breadth:
            row_dict = safe_dict_convert(row)
            row_json = safe_json_serialize(row_dict)

            # Check for missing required fields
            missing_fields = required_fields - {k for k in row_dict.keys() if k in required_fields}
            if missing_fields:
                logger.error(
                    f"[SECTOR_BREADTH] Row missing required fields: {missing_fields}. "
                    f"Available fields: {list(row_dict.keys())}. "
                    f"Cannot return incomplete breadth data - caller needs all fields for display/calculations."
                )
                # FAIL-FAST: Don't silently skip incomplete rows; report the issue
                return error_response(
                    503,
                    "data_incomplete",
                    f"Sector breadth data incomplete - missing fields: {', '.join(missing_fields)}. "
                    f"Check technical_data_daily and price_daily loaders."
                )

            breadth_data.append(row_json)

        return list_response(breadth_data)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT sector_breadth_check")
            cur.execute("RELEASE SAVEPOINT sector_breadth_check")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as sp_err:
            logger.debug(f"Failed to rollback sector_breadth_check savepoint: {sp_err}")
        code, error_type, message = handle_db_error(e, "get sector breadth")
        return error_response(code, error_type, message)


@db_route_handler("get sector position warnings")  # type: ignore[untyped-decorator]
@validate_api_response("pos")  # type: ignore[untyped-decorator]
def _get_sector_position_warnings(cur: cursor) -> Any:
    """Get sector position concentration warnings (FIX: missing endpoint for dashboard fallback).

    Returns list of sectors with position counts and concentration warnings.
    """
    try:
        cur.execute("""
                SELECT cp.sector, COUNT(DISTINCT ap.symbol) as position_count
                FROM algo_positions ap
                LEFT JOIN company_profile cp ON ap.symbol = cp.ticker
                WHERE ap.status = 'open' AND ap.quantity > 0
                GROUP BY cp.sector
                ORDER BY position_count DESC
            """)
        sector_counts = [
            (
                safe_dict_convert(row).get("sector"),
                safe_dict_convert(row).get("position_count"),
            )
            for row in cur.fetchall()
        ]

        cur.execute(
            "SELECT value FROM algo_config WHERE key = %s LIMIT 1",
            ("max_positions_per_sector",),
        )
        max_per_sector_row = cur.fetchone()
        max_per_sector = 3
        if max_per_sector_row:
            max_per_sector_row = safe_dict_convert(max_per_sector_row)
            if max_per_sector_row.get("value"):
                max_per_sector = int(max_per_sector_row["value"])

        warnings = []
        at_cap = []
        for sector, count in sector_counts:
            if not sector or count is None:
                continue
            if count >= max_per_sector:
                at_cap.append(
                    {
                        "sector": sector,
                        "position_count": count,
                        "max": max_per_sector,
                        "status": "AT_CAP",
                    }
                )
            elif count >= max_per_sector - 1:
                warnings.append(
                    {
                        "sector": sector,
                        "position_count": count,
                        "max": max_per_sector,
                        "status": "NEAR_CAP",
                    }
                )

        return success_response({"warnings": warnings, "at_cap": at_cap})

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "get sector position warnings")
        return error_response(code, error_type, message)


@db_route_handler("get sector rotation")  # type: ignore[untyped-decorator]
@validate_api_response("sec_rot")  # type: ignore[untyped-decorator]
def _get_sector_rotation(cur: cursor, days: int = 180) -> Any:
    # Reads the real signal algo/signals/sector_rotation.py already computes and persists to
    # sector_rotation_signal (rank-improvement/momentum from sector_ranking - the GICS taxonomy
    # company_profile.sector uses), rather than maintaining a second, ad-hoc implementation here.
    # The prior version of this query recomputed its own defensive-vs-cyclical comparison from
    # sector_performance.relative_strength - which is hardcoded to the literal 1.0 for every row
    # by loaders/load_sector_industry_daily.py (never a real relative-strength calculation), so
    # every sector's "strength" was identical by construction. It also joined against a hardcoded
    # GICS sector name list while sector_performance is keyed by SIC-description names for any
    # date after 2026-07-10 (same taxonomy switch documented in routes/sectors.py's fix) - so
    # "Real Estate" (a name that happens to exist in both taxonomies) was the only sector that
    # ever matched, explaining the live symptom of a real defensive_lead_score alongside an
    # always-NULL cyclical_weak_score/spread on every recent date.
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    cur.execute(
        """
            SELECT
                date,
                ROUND((details::jsonb->>'defensive_lead_score')::numeric, 2) AS defensive_lead_score,
                ROUND((details::jsonb->>'cyclical_weak_score')::numeric, 2) AS cyclical_weak_score,
                ROUND((details::jsonb->>'spread_4w')::numeric, 2) AS spread,
                signal,
                (details::jsonb->>'weeks_persistent')::int AS weeks_persistent,
                (
                    details::jsonb->>'defensive_lead_score' IS NULL
                    OR details::jsonb->>'cyclical_weak_score' IS NULL
                ) AS _is_fallback
            FROM sector_rotation_signal
            WHERE sector = 'market_rotation' AND date >= %s
            ORDER BY date DESC
        """,
        (cutoff_date,),
    )
    rotation = cur.fetchall()
    response = list_response([safe_json_serialize(safe_dict_convert(r)) for r in rotation])

    # Validate sector rotation response against contract schema
    is_valid, error_msg = ResponseValidator.validate_endpoint_response("sec_rot", response["data"])
    if not is_valid:
        logger.error(f"Sector rotation response validation failed: {error_msg}")
        return error_response(500, "response_validation_error", error_msg)

    return response


@db_route_handler("get sector stage2")  # type: ignore[untyped-decorator]
@validate_api_response("srank")  # type: ignore[untyped-decorator]
def _get_sector_stage2(cur: cursor) -> Any:
    try:
        cur.execute("""
                WITH latest_date AS (
                    SELECT date FROM trend_template_data ORDER BY date DESC LIMIT 1
                ),
                distinct_trends AS (
                    SELECT DISTINCT ON (t.symbol)
                        t.symbol, t.weinstein_stage, cp.sector
                    FROM trend_template_data t
                    JOIN company_profile cp ON t.symbol = cp.ticker
                    WHERE t.date = (SELECT date FROM latest_date)
                      AND cp.sector IS NOT NULL
                    ORDER BY t.symbol
                ),
                stage2_counts AS (
                    SELECT
                        sector,
                        COUNT(CASE WHEN weinstein_stage = 2 THEN 1 END) AS stage_2,
                        COUNT(symbol) AS total
                    FROM distinct_trends
                    GROUP BY sector
                )
                SELECT
                    sector,
                    stage_2,
                    total,
                    ROUND((stage_2::FLOAT / NULLIF(total, 0) * 100)::NUMERIC, 2) AS pct_stage_2
                FROM stage2_counts
                ORDER BY pct_stage_2 DESC
            """)
        rows = cur.fetchall()
        return list_response([safe_json_serialize(safe_dict_convert(r)) for r in rows])
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "get sector stage2")
        return error_response(code, error_type, message)
