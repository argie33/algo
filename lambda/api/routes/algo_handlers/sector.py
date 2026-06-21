"""Route: algo"""

import logging
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    list_response,
    safe_dict_convert,
    safe_json_serialize,
    success_response,
)

from utils.validation import (
    format_decimal_string,
    safe_int,
)


logger = logging.getLogger(__name__)



@db_route_handler("get algo evaluate")
def _get_algo_evaluate(cur) -> dict:
    """Get comprehensive signal evaluation with candidate analysis and constraints."""
    try:
        # Signal candidate metrics
        cur.execute("""
                SELECT
                    COUNT(DISTINCT symbol) AS candidates_screened,
                    COUNT(DISTINCT CASE WHEN score >= 60 THEN symbol END) AS candidates_passing,
                    COUNT(DISTINCT CASE WHEN score >= 70 THEN symbol END) AS candidates_excellent,
                    COUNT(DISTINCT CASE WHEN score >= 80 THEN symbol END) AS candidates_exceptional,
                    MAX(score) AS top_score,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY score) AS median_score,
                    AVG(score) AS avg_score,
                    MIN(score) AS min_score
                FROM swing_trader_scores
                WHERE date >= CURRENT_DATE - INTERVAL '14 days'
            """)
        sig_row = cur.fetchone()
        if not sig_row or not sig_row.get("candidates_screened"):
            return json_response(
                200,
                {
                    "stage": "no_data",
                    "candidates_screened": 0,
                    "candidates_passing": 0,
                    "constraints": {
                        "max_positions": 15,
                        "current_positions": 0,
                        "available_slots": 15,
                    },
                },
            )

        # Current portfolio positions and constraints
        cur.execute("""
                SELECT COUNT(*) as open_positions
                FROM algo_positions
                WHERE LOWER(status) = 'open'
            """)
        pos_row = cur.fetchone()
        open_positions = pos_row["open_positions"] if pos_row else 0

        max_positions = 15
        available_slots = max(0, max_positions - open_positions)

        # Sector exposure
        cur.execute("""
                WITH distinct_trades AS (
                    SELECT DISTINCT ON (at.symbol)
                        at.symbol, COALESCE(cp.sector, 'Unknown') AS sector
                    FROM algo_trades at
                    LEFT JOIN company_profile cp ON at.symbol = cp.ticker
                    WHERE at.status = 'open'
                    ORDER BY at.symbol
                )
                SELECT sector, COUNT(symbol) as count
                FROM distinct_trades
                GROUP BY sector
                ORDER BY count DESC
            """)
        sector_exposure = [
            safe_json_serialize(safe_dict_convert(r)) for r in cur.fetchall()
        ]

        # Risk metrics
        cur.execute("""
                SELECT
                    COALESCE(MAX(CASE WHEN snapshot_date = CURRENT_DATE THEN daily_return_pct END), 0) as today_return_pct,
                    COALESCE(MAX(CASE WHEN snapshot_date = CURRENT_DATE THEN unrealized_pnl_total END), 0) as unrealized_pnl_total,
                    COALESCE(MAX(CASE WHEN snapshot_date = CURRENT_DATE THEN unrealized_pnl_pct END), 0) as unrealized_pnl_pct,
                    COALESCE(MAX(CASE WHEN snapshot_date = CURRENT_DATE THEN unrealized_pnl_winning_count END), 0) as winning_count,
                    COALESCE(MAX(CASE WHEN snapshot_date = CURRENT_DATE THEN unrealized_pnl_losing_count END), 0) as losing_count,
                    COALESCE(MAX(CASE WHEN snapshot_date = CURRENT_DATE THEN unrealized_pnl_breakeven_count END), 0) as breakeven_count
                FROM algo_portfolio_snapshots
            """)
        risk_row = cur.fetchone()
        if not risk_row:
            # No portfolio snapshot data yet (algo just started) — fail-fast
            return json_response(
                200,
                {
                    "stage": "no_data",
                    "candidates_screened": 0,
                    "candidates_passing": 0,
                    "constraints": {
                        "max_positions": 15,
                        "current_positions": 0,
                        "available_slots": 15,
                    },
                    "portfolio_health": {
                        "today_return_pct": None,
                        "unrealized_pnl": {
                            "total_dollars": None,
                            "total_pct": None,
                            "winning_positions": 0,
                            "losing_positions": 0,
                            "breakeven_positions": 0,
                            "source": "no_data",
                        },
                    },
                },
            )

        # Fail-fast: critical fields must be present
        critical_fields = [
            "today_return_pct",
            "unrealized_pnl_total",
            "unrealized_pnl_pct",
            "winning_count",
            "losing_count",
            "breakeven_count",
        ]
        missing = [f for f in critical_fields if risk_row.get(f) is None]
        if missing:
            logger.error(f"Portfolio snapshot data incomplete: missing {missing}")
            return json_response(
                503,
                {
                    "stage": "incomplete_data",
                    "_error": f"Portfolio health metrics incomplete: {', '.join(missing)}",
                },
            )

        today_return = risk_row.get("today_return_pct")
        unrealized_pnl_total = risk_row.get("unrealized_pnl_total")
        unrealized_pnl_pct = risk_row.get("unrealized_pnl_pct")
        winning_count = risk_row.get("winning_count")
        losing_count = risk_row.get("losing_count")
        breakeven_count = risk_row.get("breakeven_count")

        sig_dict = safe_json_serialize(safe_dict_convert(sig_row))
        # Fail-fast: candidate counts must be present (not missing, but may be 0)
        candidate_fields = [
            "candidates_screened",
            "candidates_passing",
            "candidates_excellent",
            "candidates_exceptional",
        ]
        missing_candidates = [f for f in candidate_fields if f not in sig_dict]
        if missing_candidates:
            logger.error(f"Signal candidate counts incomplete: missing {missing_candidates}")
            return json_response(
                503,
                {
                    "stage": "incomplete_data",
                    "_error": f"Signal evaluation incomplete: {', '.join(missing_candidates)}",
                },
            )

        return json_response(
            200,
            {
                "stage": "evaluated",
                "candidates": {
                    "screened": sig_dict["candidates_screened"],
                    "passing_sqs_60": sig_dict["candidates_passing"],
                    "excellent_sqs_70": sig_dict["candidates_excellent"],
                    "exceptional_sqs_80": sig_dict["candidates_exceptional"],
                    "score_range": {
                        "min": (
                            float(sig_dict.get("min_score"), default=0.0, context="min_score")
                            if sig_dict.get("min_score") is not None
                            else None
                        ),
                        "median": (
                            float(sig_dict.get("median_score"), default=0.0, context="median_score")
                            if sig_dict.get("median_score") is not None
                            else None
                        ),
                        "average": (
                            float(sig_dict.get("avg_score"), default=0.0, context="avg_score")
                            if sig_dict.get("avg_score") is not None
                            else None
                        ),
                        "max": (
                            float(sig_dict.get("top_score"), default=0.0, context="top_score")
                            if sig_dict.get("top_score") is not None
                            else None
                        ),
                    },
                },
                "constraints": {
                    "max_positions": max_positions,
                    "current_positions": open_positions,
                    "available_slots": available_slots,
                    "can_add_positions": available_slots > 0,
                },
                "sector_exposure": sector_exposure,
                "portfolio_health": {
                    "today_return_pct": format_decimal_string(today_return, precision=2, allow_none=True),
                    "unrealized_pnl": {
                        "total_dollars": format_decimal_string(unrealized_pnl_total, precision=2, allow_none=True),
                        "total_pct": format_decimal_string(unrealized_pnl_pct, precision=2, allow_none=True),
                        "winning_positions": int(winning_count),
                        "losing_positions": int(losing_count),
                        "breakeven_positions": int(breakeven_count),
                        "source": "open_positions_only",
                        "note": "Includes only open positions (no closed trades, no dividends)",
                    },
                },
            },
        )
    except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
        logger.error(
            f"Failed to evaluate algorithm: {type(e).__name__}: {e}\n  Operation: Evaluate algorithm with signals and constraints\n  Endpoint: GET /api/algo/evaluate"
        )
        raise
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        return json_response(
            200,
            {
                "signals": {"total_candidates": 0},
                "constraints": {},
                "sector_exposure": {},
                "portfolio_health": {},
            },
        )



@db_route_handler("get sector breadth")
def _get_sector_breadth(cur) -> dict:
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
                      AND pd.symbol NOT LIKE '^%%'
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
                        COUNT(symbol) FILTER (WHERE close IS NOT NULL AND sma_50 IS NOT NULL AND close > sma_50) * 100.0 /
                            NULLIF(COUNT(symbol) FILTER (WHERE sma_50 IS NOT NULL AND close IS NOT NULL), 0) AS pct_above_50d,
                        COUNT(symbol) FILTER (WHERE close IS NOT NULL AND sma_200 IS NOT NULL AND close > sma_200) * 100.0 /
                            NULLIF(COUNT(symbol) FILTER (WHERE sma_200 IS NOT NULL AND close IS NOT NULL), 0) AS pct_above_200d
                    FROM distinct_symbols
                    GROUP BY sector
                )
                SELECT
                    sector,
                    ROUND(COALESCE(pct_above_50d, 0)::NUMERIC, 2) AS pct_above_50d,
                    ROUND(COALESCE(pct_above_200d, 0)::NUMERIC, 2) AS pct_above_200d,
                    (pct_above_50d IS NULL OR pct_above_200d IS NULL) AS _is_fallback
                FROM sector_breadth
                ORDER BY pct_above_50d DESC
            """)
        breadth = cur.fetchall()
        cur.execute("RELEASE SAVEPOINT sector_breadth_check")
        return list_response(
            [safe_json_serialize(safe_dict_convert(b)) for b in breadth]
        )
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



@db_route_handler("get sector position warnings")
def _get_sector_position_warnings(cur) -> dict:
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
        max_per_sector = (
            int(max_per_sector_row["value"])
            if max_per_sector_row and max_per_sector_row["value"]
            else 3
        )

        warnings = []
        at_cap = []
        for sector, count in sector_counts:
            if not sector:
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



@db_route_handler("get sector rotation")
def _get_sector_rotation(cur, days: int = 180) -> dict:
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
                SELECT
                    date,
                    sector,
                    COALESCE(return_pct, 0) AS return_pct,
                    COALESCE(relative_strength, 0) AS relative_strength
                FROM sector_performance
                WHERE date >= %s
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
                ROUND((COALESCE(defensive_strength, 0))::NUMERIC, 2) AS defensive_lead_score,
                ROUND((COALESCE(cyclical_strength, 0))::NUMERIC, 2) AS cyclical_weak_score,
                ROUND((COALESCE(defensive_strength, 0) - COALESCE(cyclical_strength, 0))::NUMERIC, 2) AS spread,
                signal,
                ROW_NUMBER() OVER (PARTITION BY signal_group_id ORDER BY date DESC) AS weeks_persistent,
                (defensive_strength IS NULL OR cyclical_strength IS NULL) AS _is_fallback
            FROM signal_groups
            ORDER BY date DESC
        """,
        (cutoff_date,),
    )
    rotation = cur.fetchall()
    return list_response([safe_json_serialize(safe_dict_convert(r)) for r in rotation])



@db_route_handler("get sector stage2")
def _get_sector_stage2(cur) -> dict:
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



