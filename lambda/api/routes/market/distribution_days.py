"""Handler for /api/market/distribution-days.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import json_response, raise_db_error

from ._shared import _rollback_savepoint

logger = logging.getLogger(__name__)


def _handle_distribution_days(cur: cursor) -> Any:
    """Handle /api/market/distribution-days endpoint."""
    dist_index_names = {
        "^GSPC": "S&P 500",
        "^IXIC": "Nasdaq Composite",
        "^NYA": "NYSE Composite",
        "^DJI": "Dow Jones",
        "^RUT": "Russell 2000",
    }
    try:
        cur.execute("SAVEPOINT dist_days")
        cur.execute("SET LOCAL statement_timeout = '15s'")  # Complex window function query
        cur.execute("""
            WITH recent_sessions AS (
                SELECT symbol, date, close, volume,
                       LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS prev_close
                FROM price_daily
                WHERE symbol IN ('^GSPC', '^IXIC', '^NYA', '^DJI')
                      AND date >= CURRENT_DATE - INTERVAL '35 days'
            ),
            volume_window AS (
                SELECT symbol, date, close, volume, prev_close,
                       AVG(volume) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 50 PRECEDING AND 1 PRECEDING) AS avg_vol
                FROM recent_sessions
            )
            SELECT symbol, date, (CURRENT_DATE - date)::INTEGER AS days_ago,
                       ROUND(((close - prev_close) / NULLIF(prev_close, 0) * 100)::NUMERIC, 2) AS change_pct,
                       ROUND((volume::NUMERIC / NULLIF(avg_vol, 0))::NUMERIC, 2) AS volume_ratio
            FROM volume_window
            WHERE prev_close IS NOT NULL
                  AND close < prev_close * 0.998
                  AND (avg_vol IS NULL OR volume > avg_vol * 1.01)
            ORDER BY symbol, date DESC
        """)
        rows = cur.fetchall()
        by_sym: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            r = dict(row)
            sym = r["symbol"]
            if sym not in by_sym:
                by_sym[sym] = []
            by_sym[sym].append(
                {
                    "date": str(r["date"]),
                    "change_pct": (float(r["change_pct"]) if r["change_pct"] is not None else None),
                    "volume_ratio": (float(r["volume_ratio"]) if r["volume_ratio"] is not None else None),
                    "days_ago": r["days_ago"],
                }
            )
        result = {}
        for sym, days in by_sym.items():
            count = len(days)
            signal = "DANGER" if count >= 5 else ("CAUTION" if count >= 3 else "WATCH" if count >= 1 else "NORMAL")
            result[sym] = {
                "name": dist_index_names.get(sym, sym),
                "count": count,
                "signal": signal,
                "days": days,
            }
        cur.execute("RELEASE SAVEPOINT dist_days")
        return json_response(200, result)
    except (
        psycopg2.errors.QueryCanceled,
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        _rollback_savepoint(cur, "dist_days")
        logger.error(f"[DIST_DAYS] Error: {type(e).__name__}: {e}")
        raise_db_error(e, "distribution days query")
        raise  # unreachable - raise_db_error is NoReturn
