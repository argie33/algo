"""Diagnostic endpoint to detect position data sync issues.

Compares position counts across all data sources to catch divergence early.
"""

from typing import Any

from psycopg2.extensions import cursor
from routes.utils import db_route_handler, error_response, json_response


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle GET /api/diagnostics request.

    Every route module dispatched via api_router.route_request() must expose a
    module-level `handle(...)` entry point (see routes/data_coverage.py,
    routes/risk_dashboard.py, etc.) — route_request() calls `handler.handle(...)`
    directly on the imported module. This one was missing it, which raised
    `AttributeError: module 'routes.diagnostics' has no attribute 'handle'`
    on every request, surfacing as a 500 "Code bug accessing data fields".
    """
    if method != "GET":
        return error_response(405, "method_not_allowed", "Method not allowed. Only GET is supported.")
    return _check_data_sync_health(cur)


@db_route_handler("check data sync health")
def _check_data_sync_health(cur: cursor) -> Any:
    """Check if position data sources are synchronized.

    Returns status with comparison across:
    - algo_trades (our trading record)
    - algo_positions (Alpaca sync)
    - algo_positions_with_risk (cached view)
    """
    # Count open positions in algo_trades (what reconciliation uses)
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE status IN ('open', 'filled', 'active', 'partially_filled')
        AND exit_date IS NULL
    """)
    trade_count = cur.fetchone()[0]

    # Count open positions in algo_positions (Alpaca-synced)
    cur.execute("""
        SELECT COUNT(*) FROM algo_positions WHERE status = 'open'
    """)
    position_count = cur.fetchone()[0]

    # Count in materialized view (dashboard shows this)
    cur.execute("""
        SELECT COUNT(*) FROM algo_positions_with_risk WHERE status = 'open'
    """)
    view_count = cur.fetchone()[0]

    # Check for quantity mismatches (duplicate positions)
    cur.execute("""
        SELECT symbol, status, COUNT(*) as instances, SUM(quantity) as total_qty
        FROM algo_positions
        WHERE status = 'open'
        GROUP BY symbol, status
        HAVING COUNT(*) > 1
    """)
    duplicates = cur.fetchall()

    synced = (trade_count == position_count == view_count) and not duplicates

    return json_response(
        200,
        {
            "synced": synced,
            "positions": {
                "algo_trades": trade_count,
                "algo_positions": position_count,
                "view_cache": view_count,
            },
            "issues": {
                "duplicate_symbols": [
                    {
                        "symbol": d[0],
                        "status": d[1],
                        "instances": d[2],
                        "total_quantity": d[3],
                    }
                    for d in duplicates
                ]
                if duplicates
                else [],
                "view_stale": view_count != position_count,
                "source_mismatch": trade_count != position_count,
            },
            "action_if_mismatch": (
                "Run reconciliation to resync, then refresh materialized view: "
                "REFRESH MATERIALIZED VIEW algo_positions_with_risk"
            ),
        },
    )
