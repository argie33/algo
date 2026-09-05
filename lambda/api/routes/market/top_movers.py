"""Handler for /api/market/top-movers.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import json_response, raise_api_error, safe_json_serialize

from utils.validation import safe_float

from ._shared import _rollback_savepoint

logger = logging.getLogger(__name__)


def _handle_top_movers(cur: cursor) -> Any:
    """Handle /api/market/top-movers endpoint."""
    movers = []
    gainers = []
    losers = []
    try:
        cur.execute("SAVEPOINT top_movers")
        cur.execute("SET LOCAL statement_timeout = '8s'")
        # OPTIMIZATION: Simplified query with better index usage
        # Pre-filter at lower level to avoid joining all symbols
        cur.execute("""
            WITH latest_d AS (
                SELECT date AS d FROM price_daily
                WHERE close IS NOT NULL
                ORDER BY date DESC LIMIT 1
            ),
            prev_d AS (
                SELECT date AS d FROM price_daily
                WHERE date < (SELECT d FROM latest_d)
                      AND close IS NOT NULL
                ORDER BY date DESC LIMIT 1
            ),
            today AS (
                SELECT symbol, close
                FROM price_daily
                WHERE date = (SELECT d FROM latest_d)
                      AND symbol NOT LIKE '^%'
                      AND close > 0
            ),
            yesterday AS (
                SELECT symbol, close
                FROM price_daily
                WHERE date = (SELECT d FROM prev_d)
                      AND symbol NOT LIKE '^%'
                      AND close > 0
            )
            SELECT t.symbol, COALESCE(ss.security_name, t.symbol) AS security_name,
                   ROUND(((t.close - y.close) / y.close * 100)::numeric, 2) as pct_change
            FROM today t
            INNER JOIN yesterday y ON t.symbol = y.symbol
            LEFT JOIN stock_symbols ss ON t.symbol = ss.symbol
            WHERE t.symbol NOT IN (SELECT symbol FROM etf_symbols)
            ORDER BY ABS((t.close - y.close) / y.close) DESC
            LIMIT 40
        """)
        movers = cur.fetchall()
        cur.execute("RELEASE SAVEPOINT top_movers")
    except psycopg2.errors.QueryCanceled as e:
        logger.warning(f"[TOP_MOVERS] Query timeout: {type(e).__name__}")
        _rollback_savepoint(cur, "top_movers")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        logger.warning(f"[TOP_MOVERS] Database error: {type(e).__name__}")
        _rollback_savepoint(cur, "top_movers")

    if not movers:
        raise_api_error(503, "no_data", "Top movers data not yet available")

    items = [safe_json_serialize(dict(m)) for m in movers]
    valid_items = []
    invalid_count = 0
    for m in items:
        pct_val = safe_float(m.get("pct_change"), default=None)
        if pct_val is not None:
            m["pct_change"] = pct_val
            valid_items.append(m)
        else:
            invalid_count += 1

    if not valid_items:
        raise_api_error(503, "no_data", "Top movers data validation failed - no valid price change data")

    # CRITICAL FIX: Fail-fast if too many items have missing data
    # Silent filtering masks data quality issues in finance app
    total_items = len(items) if items else 1  # Avoid division by zero
    invalid_rate = invalid_count / total_items if total_items > 0 else 0
    if invalid_rate > 0.05:  # > 5% invalid data is unacceptable
        raise_api_error(
            503,
            "data_quality",
            f"Top movers data quality degraded: {invalid_count}/{total_items} items ({invalid_rate * 100:.1f}%) "
            f"missing price change data. Fail-fast: cannot show incomplete market view.",
        )

    if invalid_count > 0:
        logger.warning(
            f"[TOP_MOVERS] Filtered {invalid_count} items with missing pct_change ({invalid_rate * 100:.1f}%); "
            f"showing {len(valid_items)} valid items"
        )

    gainers = sorted(
        [m for m in valid_items if m["pct_change"] >= 0],
        key=lambda x: -x["pct_change"],
    )[:10]
    losers = sorted(
        [m for m in valid_items if m["pct_change"] < 0],
        key=lambda x: x["pct_change"],
    )[:10]
    return json_response(200, {"gainers": gainers, "losers": losers, "items": valid_items})
