"""Handler for /api/market/technicals.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    execute_with_timeout,
    json_response,
    raise_api_error,
    raise_db_error,
    safe_json_serialize,
)

from ._shared import _rollback_savepoint

logger = logging.getLogger(__name__)


def _handle_technicals(cur: cursor) -> Any:
    """Handle /api/market/technicals endpoint."""
    try:
        cur.execute("SET LOCAL statement_timeout = '3000ms'")
        rows = execute_with_timeout(
            cur,
            """
            SELECT date, advance_decline_ratio, new_highs_count, new_lows_count,
                       up_volume_percent, breadth_momentum_10d,
                       vix_level, put_call_ratio, market_trend, market_stage
            FROM market_health_daily
            ORDER BY date DESC
            LIMIT 1
        """,
            timeout_sec=3,
        )
    except psycopg2.errors.QueryCanceled as e:
        logger.error(f"[MARKET_TECHNICALS] Query timeout: {type(e).__name__}: {e}")
        raise_api_error(504, "timeout", "Market technicals data query exceeded timeout")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        logger.error(f"[MARKET_TECHNICALS] Database error: {type(e).__name__}: {e}")
        raise_db_error(e, "market technicals query")

    if not rows:
        raise RuntimeError("No market technicals data available")
    base = safe_json_serialize(dict(rows[0]))

    # Compute today's advancing/declining counts from price_daily.
    # OPTIMIZATION: Use date-based index for faster filtering
    try:
        cur.execute("SAVEPOINT technicals_breadth")
        cur.execute("SET LOCAL statement_timeout = '3000ms'")
        breadth_query = """
            WITH latest AS (
                SELECT date AS d FROM price_daily
                WHERE close IS NOT NULL AND symbol NOT LIKE '^%'
                  AND symbol NOT IN (SELECT symbol FROM etf_symbols)
                ORDER BY date DESC LIMIT 1
            ),
            prev_day AS (
                SELECT date AS d FROM price_daily
                WHERE date < (SELECT d FROM latest)
                      AND close IS NOT NULL AND symbol NOT LIKE '^%'
                      AND symbol NOT IN (SELECT symbol FROM etf_symbols)
                ORDER BY date DESC LIMIT 1
            )
            SELECT
                COUNT(*) FILTER (WHERE t.close > y.close) AS advancing,
                COUNT(*) FILTER (WHERE t.close < y.close) AS declining,
                COUNT(*) FILTER (WHERE t.close = y.close) AS unchanged,
                COUNT(t.symbol) AS total_stocks
            FROM price_daily t
            JOIN price_daily y ON t.symbol = y.symbol
            WHERE t.date = (SELECT d FROM latest)
              AND y.date = (SELECT d FROM prev_day)
              AND t.close IS NOT NULL
              AND y.close IS NOT NULL
              AND t.symbol NOT IN (SELECT symbol FROM etf_symbols)
        """
        breadth_rows = execute_with_timeout(cur, breadth_query, timeout_sec=3)
        cur.execute("RELEASE SAVEPOINT technicals_breadth")
        if not breadth_rows:
            logger.critical("[TECHNICALS_BREADTH] No breadth data available - market health calculation incomplete")
            raise RuntimeError(
                "Critical market breadth data unavailable. "
                "Market breadth (advancing/declining counts) required for complete market health assessment. "
                "Cannot proceed with incomplete market data."
            )
        else:
            base["breadth"] = dict(breadth_rows[0])
    except psycopg2.errors.QueryCanceled as e:
        _rollback_savepoint(cur, "technicals_breadth")
        raise RuntimeError(f"Market technicals breadth calculation timed out: {e}") from e
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        _rollback_savepoint(cur, "technicals_breadth")
        raise RuntimeError(f"Market technicals breadth query failed: {e}") from e

    # Build 30-day A/D line history (formerly labeled mcclellan_oscillator).
    # NOTE: the old McClellan-oscillator factor (which stored a "value" key) was
    # removed in the 12-factor exposure redesign; _ad_line() now stores its 20-day
    # net advance/decline change under "ad_change_20d" instead. This query still
    # read the old "value" key, so it silently returned zero rows on every call -
    # the chart never had any data to render.
    # 2026-08-23 pillar redesign moved ad_line again, from a top-level factors key to
    # factors.pillar_confirm.components.participation.ad_line - same failure mode as the
    # note above (silent zero-rows, not an error) would have recurred here if left
    # pointing at the old path.
    try:
        cur.execute("SET LOCAL statement_timeout = '3000ms'")
        cur.execute("""
            SELECT date,
                   (factors->'pillar_confirm'->'components'->'participation'->'ad_line'->>'ad_change_20d')::float
                       AS advance_decline_line
            FROM market_exposure_daily
            WHERE date >= CURRENT_DATE - INTERVAL '35 days'
                  AND factors IS NOT NULL
                  AND factors->'pillar_confirm'->'components'->'participation'->'ad_line' IS NOT NULL
                  AND (factors->'pillar_confirm'->'components'->'participation'->'ad_line'->>'ad_change_20d')
                      IS NOT NULL
            ORDER BY date DESC
            LIMIT 30
        """)
        adrows = cur.fetchall()
        base["mcclellan_oscillator"] = [safe_json_serialize(dict(r)) for r in adrows]
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        psycopg2.errors.QueryCanceled,
    ) as e:
        logger.error(f"[MCCLELLAN] Database error - McClellan oscillator unavailable: {type(e).__name__}: {e}")
        return error_response(
            503,
            "mcclellan_unavailable",
            f"McClellan oscillator calculation failed: {type(e).__name__}",
        )

    freshness = check_data_freshness(cur, "market_health_daily", "date", warning_days=1)
    return json_response(200, base, data_freshness=freshness)
