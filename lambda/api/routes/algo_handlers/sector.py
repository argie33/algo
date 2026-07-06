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

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    list_response,
    raise_api_error,
    safe_dict_convert,
    safe_json_serialize,
    success_response,
    validate_api_response,
)

from shared_contracts.response_validator import ResponseValidator
from utils.validation import format_decimal_string

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
        cur.execute("""
                WITH latest_tech AS (
                    SELECT DISTINCT ON (td.symbol)
                        td.symbol, td.sma_50, td.sma_200
                    FROM technical_data_daily td
                    WHERE td.date >= CURRENT_DATE - INTERVAL '7 days'
                    ORDER BY td.symbol, td.date DESC
                ),
                latest_price AS (
                    SELECT DISTINCT ON (pd.symbol)
                        pd.symbol, pd.close
                    FROM price_daily pd
                    WHERE pd.date >= CURRENT_DATE - INTERVAL '7 days'
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
        return list_response([safe_json_serialize(safe_dict_convert(b)) for b in breadth])
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
        max_per_sector = int(max_per_sector_row["value"]) if max_per_sector_row and max_per_sector_row["value"] else 3

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
    """Get sector rotation data: defensive vs cyclical relative strength."""
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    cur.execute(
        """
            WITH defensive_sectors AS (
                SELECT 'Consumer Defensive' AS sector UNION ALL
                SELECT 'Utilities' UNION ALL
                SELECT 'Healthcare' UNION ALL
                SELECT 'Real Estate'
            ),
            cyclical_sectors AS (
                SELECT 'Consumer Cyclical' AS sector UNION ALL
                SELECT 'Industrials' UNION ALL
                SELECT 'Basic Materials' UNION ALL
                SELECT 'Technology'
            ),
            sector_perf AS (
                -- CRITICAL: Do NOT COALESCE to 0 - NULL values are valid and affect AVG calculations
                -- Missing data must be NULL, not silently 0
                SELECT
                    date,
                    sector,
                    return_pct,
                    relative_strength
                FROM sector_performance
                WHERE date >= %s AND return_pct IS NOT NULL AND relative_strength IS NOT NULL
            ),
            rotation_stats AS (
                SELECT
                    sp.date,
                    AVG(CASE WHEN d.sector IS NOT NULL THEN sp.return_pct ELSE NULL END) AS defensive_return,
                    AVG(CASE WHEN c.sector IS NOT NULL THEN sp.return_pct ELSE NULL END) AS cyclical_return,
                    AVG(CASE WHEN d.sector IS NOT NULL THEN sp.relative_strength ELSE NULL END) AS defensive_strength,
                    AVG(CASE WHEN c.sector IS NOT NULL THEN sp.relative_strength ELSE NULL END) AS cyclical_strength
                FROM sector_perf sp
                LEFT JOIN defensive_sectors d ON sp.sector = d.sector
                LEFT JOIN cyclical_sectors c ON sp.sector = c.sector
                WHERE d.sector IS NOT NULL OR c.sector IS NOT NULL
                GROUP BY sp.date
            ),
            rotation_with_signal AS (
                SELECT
                    date,
                    defensive_strength,
                    cyclical_strength,
                    CASE
                        WHEN defensive_strength > cyclical_strength THEN 'DEFENSIVE'
                        WHEN cyclical_strength > defensive_strength THEN 'CYCLICAL'
                        ELSE 'NEUTRAL'
                    END AS signal
                FROM rotation_stats
            ),
            signal_changes AS (
                SELECT
                    date,
                    defensive_strength,
                    cyclical_strength,
                    signal,
                    CASE WHEN signal != LAG(signal) OVER (ORDER BY date DESC) THEN 1 ELSE 0 END AS is_signal_change
                FROM rotation_with_signal
            ),
            signal_groups AS (
                SELECT
                    date,
                    defensive_strength,
                    cyclical_strength,
                    signal,
                    SUM(is_signal_change) OVER (ORDER BY date DESC) AS signal_group_id
                FROM signal_changes
            )
            SELECT
                date,
                ROUND(defensive_strength::NUMERIC, 2) AS defensive_lead_score,
                ROUND(cyclical_strength::NUMERIC, 2) AS cyclical_weak_score,
                ROUND((defensive_strength - cyclical_strength)::NUMERIC, 2) AS spread,
                signal,
                ROW_NUMBER() OVER (PARTITION BY signal_group_id ORDER BY date DESC) AS weeks_persistent,
                (defensive_strength IS NULL OR cyclical_strength IS NULL) AS _is_fallback
            FROM signal_groups
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
    """Get percentage of stocks in Stage 2 by sector."""
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
