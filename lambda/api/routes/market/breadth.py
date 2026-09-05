"""Handler for /api/market/breadth.

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
    execute_with_timeout,
    list_response,
    raise_api_error,
    raise_db_error,
    safe_json_serialize,
)

logger = logging.getLogger(__name__)


def _handle_breadth(cur: cursor) -> Any:
    """Handle /api/market/breadth endpoint."""
    # Compute A/D per day using a self-join on consecutive trading dates.
    # Self-join is faster than LAG window over 35 days x 9000 symbols.
    # Uses retry logic with exponential backoff to handle transient timeouts
    # when DB is under heavy write load from loaders.
    breadth = []
    freshness = {}

    # MATERIALIZED CTEs force one evaluation each; explicit NOT LIKE on y lets
    # PostgreSQL use the idx_price_daily_date_symbol partial index for both joins.
    # ETF FILTERING: Market breadth measures stock market participation (advance/decline).
    # Exclude indices (^VIX, etc) and ETFs per GOVERNANCE: "financial data loaders exclude ETFs".
    # This applies to market health calculations too - must measure stock-only breadth.
    breadth_query = """
        WITH trading_dates AS MATERIALIZED (
            SELECT DISTINCT date
            FROM price_daily
            WHERE date >= CURRENT_DATE - INTERVAL '25 days'
            ORDER BY date DESC LIMIT 12
        ),
        date_pairs AS MATERIALIZED (
            SELECT d1.date AS d, MAX(d2.date) AS prev_d
            FROM trading_dates d1
            JOIN trading_dates d2 ON d2.date < d1.date
            GROUP BY d1.date
        )
        SELECT
            dp.d AS date,
            COUNT(*) FILTER (WHERE t.close > y.close) AS advances,
            COUNT(*) FILTER (WHERE t.close < y.close) AS declines,
            COUNT(*) FILTER (WHERE t.close = y.close) AS unchanged,
            COUNT(t.symbol) AS total
        FROM date_pairs dp
        JOIN price_daily t ON t.date = dp.d
            AND t.symbol NOT LIKE '^%' AND t.close IS NOT NULL
            AND t.symbol NOT IN (SELECT symbol FROM etf_symbols)
        JOIN price_daily y ON y.date = dp.prev_d AND y.symbol = t.symbol
            AND y.symbol NOT LIKE '^%' AND y.close IS NOT NULL
            AND y.symbol NOT IN (SELECT symbol FROM etf_symbols)
        GROUP BY dp.d
        ORDER BY dp.d DESC
        LIMIT 10
    """

    # 20s timeout - Lambda is 25s, APIGW is 29s; single attempt avoids double-hit.
    try:
        breadth = execute_with_timeout(cur, breadth_query, timeout_sec=20, max_attempts=1)
    except psycopg2.errors.QueryCanceled as e:
        logger.error(f"[MARKET_BREADTH] Query timeout: {type(e).__name__}: {e}")
        raise_api_error(504, "timeout", "Market breadth data query exceeded timeout")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        logger.error(f"[MARKET_BREADTH] Database error: {type(e).__name__}: {e}")
        raise_db_error(e, "market breadth query")

    if breadth:
        # CRITICAL: Validate breadth data completeness before returning
        # Breadth metrics drive market regime calculations - incomplete data is worse than missing data
        required_fields = ["date", "advances", "declines", "unchanged", "total"]
        for row in breadth:
            row_dict = dict(row)
            for field in required_fields:
                if field not in row_dict or row_dict[field] is None:
                    raise RuntimeError(
                        f"[MARKET_BREADTH] Breadth data incomplete: missing '{field}' field. "
                        f"Breadth metrics {required_fields} are required for market regime calculation. "
                        f"Incomplete breadth data would cause incorrect market exposure sizing. "
                        f"Check price_daily data quality and breadth query integrity."
                    )

        # Only fetch freshness if query succeeded
        try:
            freshness = check_data_freshness(cur, "price_daily", "date", warning_days=1)
        except (
            psycopg2.errors.UndefinedTable,
            psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError,
            psycopg2.DatabaseError,
        ) as e:
            raise RuntimeError(f"Market breadth freshness check failed - cannot verify data: {e}") from e

    return list_response(
        [safe_json_serialize(dict(b)) for b in breadth],
        data_freshness=freshness,
    )
