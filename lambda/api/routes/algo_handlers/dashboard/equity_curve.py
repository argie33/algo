"""Algo dashboard handler: /api/algo/equity-curve.

Split 2026-09-05 out of the original 2160-line algo_handlers/dashboard.py (see
positions.py's module docstring for the full split rationale). This module holds only
`_get_equity_curve`. Pure move, no logic changed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    error_response,
    handle_db_error,
    list_response,
    safe_dict_convert,
    safe_json_serialize,
)

logger = logging.getLogger(__name__)


@db_route_handler("fetch equity curve")
def _get_equity_curve(cur: cursor, days: int = 180) -> Any:
    try:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
        # drawdown_pct is computed from adjusted_equity (cash-flow-adjusted, migration
        # 1134), not raw total_portfolio_value, so a capital deposit/withdrawal doesn't
        # show up as a fake drawdown spike here while the circuit breaker/risk dashboard
        # agree on the real trading-performance figure. total_portfolio_value itself is
        # still returned as-is (real dollar equity curve).
        cur.execute(
            """
                WITH snapshots AS (
                    SELECT snapshot_date, total_portfolio_value, total_cash,
                           unrealized_pnl_total, position_count, daily_return_pct, adjusted_equity,
                           MAX(adjusted_equity) OVER (
                               ORDER BY snapshot_date ASC
                               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                           ) AS adjusted_running_peak
                    FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= %s AND total_portfolio_value > 0 AND adjusted_equity IS NOT NULL
                )
                SELECT snapshot_date, total_portfolio_value, total_cash,
                       unrealized_pnl_total, position_count, daily_return_pct,
                       ROUND(
                           (adjusted_equity - adjusted_running_peak) / NULLIF(adjusted_running_peak, 0) * 100,
                           4
                       ) AS drawdown_pct
                FROM snapshots
                ORDER BY snapshot_date DESC
                LIMIT 1000
            """,
            (cutoff_date,),
        )
        curve = cur.fetchall()
        freshness = check_data_freshness(cur, "algo_portfolio_snapshots", "snapshot_date", warning_days=1)
        return list_response(
            [safe_json_serialize(safe_dict_convert(c)) for c in reversed(curve) if c is not None],
            data_freshness=freshness,
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch equity curve")
        return error_response(code, error_type, message)
