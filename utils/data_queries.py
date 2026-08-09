"""Centralized database queries - single source of truth for data filtering.

All position, trade, and signal queries go through this module to ensure consistency
across API, dashboard, and orchestration. Changes to filtering/status logic need only
be made here.

Principle: One query pattern, used everywhere. Never duplicate WHERE clauses.
"""

import os
from typing import Any

from psycopg2.extensions import cursor


def _is_local_mode() -> bool:
    """Check if running in LOCAL_MODE (development without AWS/RDS permissions)."""
    return os.environ.get("LOCAL_MODE", "").lower() == "true"


def get_open_positions(cur: cursor, limit: int = 1000) -> list[dict[str, Any]]:
    """Get all open positions with complete risk data.

    Returns positions from algo_positions_with_risk view filtered by status='open'.
    Single source of truth: all open position queries use this function.

    In LOCAL_MODE: Uses base tables since materialized view requires elevated permissions.
    """
    if _is_local_mode():
        # Fallback for LOCAL_MODE - query base tables instead of materialized view
        cur.execute(
            """
            SELECT
                p.position_id, p.symbol, p.entry_price, p.quantity,
                p.status, p.created_at, p.updated_at,
                COALESCE(p.entry_price * p.quantity, 0) as position_value,
                0 as daily_pnl, 0 as total_pnl
            FROM algo_positions p
            WHERE p.status = 'open'
            ORDER BY (p.entry_price * p.quantity) DESC
            LIMIT %s
        """,
            (limit,),
        )
    else:
        cur.execute(
            """
            SELECT * FROM algo_positions_with_risk
            WHERE status = 'open'
            ORDER BY position_value DESC
            LIMIT %s
        """,
            (limit,),
        )
    return cur.fetchall()  # type: ignore


def get_closed_positions(cur: cursor, limit: int = 100) -> list[dict[str, Any]]:
    """Get all closed positions ordered by most recent first.

    In LOCAL_MODE: Uses base tables since materialized view requires elevated permissions.
    """
    if _is_local_mode():
        cur.execute(
            """
            SELECT
                p.position_id, p.symbol, p.entry_price, p.quantity,
                p.status, p.created_at, p.updated_at,
                COALESCE(p.entry_price * p.quantity, 0) as position_value,
                0 as daily_pnl, 0 as total_pnl
            FROM algo_positions p
            WHERE p.status = 'closed'
            ORDER BY p.updated_at DESC
            LIMIT %s
        """,
            (limit,),
        )
    else:
        cur.execute(
            """
            SELECT * FROM algo_positions_with_risk
            WHERE status = 'closed'
            ORDER BY updated_at DESC
            LIMIT %s
        """,
            (limit,),
        )
    return cur.fetchall()  # type: ignore


def get_recent_completed_trades(cur: cursor, limit: int = 30) -> list[dict[str, Any]]:
    """Get recent completed trades with exit dates (for win/loss analysis).

    Used by dashboard for win rate calculations and performance metrics.
    Only returns trades with exit_date IS NOT NULL to ensure completeness.
    """
    cur.execute(
        """
        SELECT * FROM algo_trades
        WHERE status = 'closed' AND exit_date IS NOT NULL
        ORDER BY exit_date DESC
        LIMIT %s
    """,
        (limit,),
    )
    return cur.fetchall()  # type: ignore


def get_trade_win_loss_stats(cur: cursor, limit: int = 30) -> dict[str, int | None]:
    """Get win/loss statistics for recent completed trades.

    Single source of truth for trade performance metrics used by circuit breakers.

    Mirrors the exclusions in algo/risk/circuit_breaker.py::_check_win_rate_floor
    (the live pretrade halt gate) and loaders/compute_circuit_breakers.py::_compute_win_rate
    (the reporting loader): reconciliation/force-close/delisted/DATA-QC/CONCENTRATION exits
    and EXT- synthetic trades are not real strategy outcomes and must not count toward win
    rate, and exit_r_multiple IS NOT NULL + a deterministic exit_time/id tiebreak are required
    for the same reasons documented there. Confirmed live 2026-08-03: this was the one CB9
    win-rate implementation the CONCENTRATION-exclusion fix (commit 3078163b2) missed - this
    dashboard endpoint (lambda/api/routes/algo_handlers/dashboard.py CB9) kept reporting a
    contaminated 24.0% (8 of the most recent 30 trades were POSITION_SIZE_CONCENTRATION force-
    exits / a reconciliation close) alongside the already-patched consecutive_losses=0 from
    circuit_breaker_status, producing exactly the "consecutive_losses is 0 but win_rate_floor
    triggered" confusion this was reported under - the two breakers were reading from
    differently-filtered trade sets, not disagreeing on real performance. The live trading
    gate was never affected (it already had this fix); only this dashboard display was wrong.

    Args:
        cur: Database cursor
        limit: Number of recent closed trades to analyze

    Returns: Dict with keys:
        - wins: Count of trades with profit_loss_pct > 0
        - losses: Count of trades with profit_loss_pct < 0
        - total: Total trade count
    """
    cur.execute(
        """
        SELECT COUNT(*) FILTER (WHERE profit_loss_pct > 0) as wins,
               COUNT(*) FILTER (WHERE profit_loss_pct < 0) as losses,
               COUNT(*) as total
        FROM (
            SELECT profit_loss_pct
            FROM algo_trades
            WHERE status = 'closed' AND exit_date IS NOT NULL
              AND exit_r_multiple IS NOT NULL
              AND trade_id NOT LIKE 'EXT-%%'
              AND exit_reason NOT LIKE %s
              AND exit_reason NOT LIKE %s
              AND exit_reason NOT LIKE %s
              AND exit_reason NOT LIKE %s
              AND exit_reason NOT LIKE %s
            ORDER BY exit_date DESC, exit_time DESC NULLS LAST, id DESC LIMIT %s
        ) recent_trades
    """,
        ("%reconciliation%", "%force%close%", "%delisted%", "%DATA-QC%", "%CONCENTRATION%", limit),
    )
    row = cur.fetchone()
    if not row:
        return {"wins": None, "losses": None, "total": None}
    return {
        "wins": int(row["wins"]) if row["wins"] is not None else 0,
        "losses": int(row["losses"]) if row["losses"] is not None else 0,
        "total": int(row["total"]) if row["total"] is not None else 0,
    }


def get_trade_performance_stats(cur: cursor) -> dict[str, Any]:
    """Get comprehensive trade statistics for closed trades.

    Single source of truth for all closed trade performance metrics.
    Includes average win/loss percentages, average R-multiples, and gross profit/loss dollars.

    Returns: Dict with aggregated trade metrics (all values may be None if no trades exist)
    """
    cur.execute(
        """
        SELECT
            AVG(CASE WHEN profit_loss_pct > 0 THEN profit_loss_pct END) AS avg_win_pct,
            AVG(CASE WHEN profit_loss_pct < 0 THEN profit_loss_pct END) AS avg_loss_pct,
            AVG(CASE WHEN exit_r_multiple > 0 THEN exit_r_multiple END) AS avg_win_r,
            AVG(CASE WHEN exit_r_multiple < 0 THEN exit_r_multiple END) AS avg_loss_r,
            NULLIF(SUM(CASE WHEN profit_loss_dollars > 0 THEN profit_loss_dollars ELSE 0 END), 0) AS gross_win_dollars,
            NULLIF(ABS(SUM(CASE WHEN profit_loss_dollars < 0 THEN profit_loss_dollars ELSE 0 END)), 0) AS gross_loss_dollars
        FROM algo_trades
        WHERE status = 'closed' AND exit_date IS NOT NULL
    """
    )
    row = cur.fetchone()
    return dict(row) if row else {}


def get_recent_trade_pnls(cur: cursor, limit: int = 30) -> list[float | None]:
    """Get profit/loss percentages for recent closed trades.

    Used for win/loss streak calculation and performance analysis.

    Args:
        cur: Database cursor
        limit: Number of recent trades to fetch

    Returns: List of profit_loss_pct values (may contain None)
    """
    cur.execute(
        """
        SELECT profit_loss_pct FROM algo_trades
        WHERE status = 'closed' AND exit_date IS NOT NULL AND profit_loss_pct IS NOT NULL
        ORDER BY exit_date DESC, trade_id DESC LIMIT %s
    """,
        (limit,),
    )
    rows = cur.fetchall()
    return [row["profit_loss_pct"] for row in rows] if rows else []


def get_open_portfolio_totals(cur: cursor) -> dict[str, float | None]:
    """Get aggregate portfolio metrics for open positions.

    Single source of truth for portfolio equity and unrealized P&L.
    Used by circuit breakers for position-level risk management.

    Returns: Dict with keys:
        - total_equity: Sum of position_value for open positions (may be None)
        - current_pnl: Sum of unrealized_pnl for open positions (may be None)
    """
    cur.execute(
        """
        SELECT SUM(position_value) as total_equity,
               SUM(unrealized_pnl) as current_pnl
        FROM algo_positions
        WHERE status = 'open'
    """
    )
    row = cur.fetchone()
    if not row:
        return {"total_equity": None, "current_pnl": None}
    return {
        "total_equity": row[0],
        "current_pnl": row[1],
    }


def get_all_positions(cur: cursor, limit: int = 1000) -> list[dict[str, Any]]:
    """Get all positions (open and closed) ordered by position value.

    In LOCAL_MODE: Uses base tables since materialized view requires elevated permissions.
    """
    if _is_local_mode():
        cur.execute(
            """
            SELECT
                p.position_id, p.symbol, p.entry_price, p.quantity,
                p.status, p.created_at, p.updated_at,
                COALESCE(p.entry_price * p.quantity, 0) as position_value,
                0 as daily_pnl, 0 as total_pnl
            FROM algo_positions p
            ORDER BY (p.entry_price * p.quantity) DESC
            LIMIT %s
        """,
            (limit,),
        )
    else:
        cur.execute(
            """
            SELECT * FROM algo_positions_with_risk
            ORDER BY position_value DESC
            LIMIT %s
        """,
            (limit,),
        )
    return cur.fetchall()  # type: ignore


def get_trades_by_status(
    cur: cursor, status: str | None = None, limit: int = 200, offset: int = 0
) -> list[dict[str, Any]]:
    """Get trades filtered by status with pagination.

    Args:
        cur: Database cursor
        status: Filter trades by status ('pending', 'open', 'closed', 'filled', 'cancelled', 'rejected')
                If None, returns all trades
        limit: Maximum number of trades to return
        offset: Number of trades to skip (for pagination)

    Returns: List of trade records

    Raises: ValueError if status is invalid
    """
    valid_statuses = {"pending", "open", "closed", "filled", "cancelled", "rejected", None}
    if status is not None and status not in valid_statuses:
        raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    if status is None:
        where_clause = ""
        params: tuple[Any, ...] = (limit, offset)
    else:
        where_clause = "WHERE status = %s"
        params = (status, limit, offset)

    cur.execute(
        f"""
        SELECT trade_id, symbol, signal_date, trade_date, entry_time,
               entry_price, entry_quantity, entry_reason,
               exit_price, exit_date, exit_reason, exit_time,
               stop_loss_price, status, profit_loss_dollars, profit_loss_pct,
               exit_r_multiple, trade_duration_days, mfe_pct, mae_pct,
               execution_mode, created_at
        FROM algo_trades
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """,
        params,
    )
    return cur.fetchall()  # type: ignore


def count_trades_by_status(cur: cursor, status: str | None = None) -> int:
    """Count trades matching status filter.

    Single source of truth for trade counts used with pagination.

    Args:
        cur: Database cursor
        status: Filter trades by status (same valid values as get_trades_by_status)

    Returns: Count of matching trades

    Raises: ValueError if status is invalid
    """
    valid_statuses = {"pending", "open", "closed", "filled", "cancelled", "rejected", None}
    if status is not None and status not in valid_statuses:
        raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    if status is None:
        where_clause = ""
        params: tuple[Any, ...] = ()
    else:
        where_clause = "WHERE status = %s"
        params = (status,)

    cur.execute(f"SELECT COUNT(*) FROM algo_trades {where_clause}", params)
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def get_recent_trades(cur: cursor, days_back: int = 30, limit: int = 100) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM algo_trades
        WHERE status = 'closed'
          AND exit_date >= CURRENT_DATE - %s
        ORDER BY exit_date DESC, trade_id DESC
        LIMIT %s
    """,
        (days_back, limit),
    )
    return cur.fetchall()  # type: ignore


def count_open_positions(cur: cursor) -> int:
    cur.execute("SELECT COUNT(*) as count FROM algo_positions WHERE status = 'open'")
    row = cur.fetchone()
    return int(row["count"]) if row else 0


def sum_open_position_value(cur: cursor) -> float:
    cur.execute(
        """
        SELECT SUM(position_value) as total
        FROM algo_positions
        WHERE status = 'open'
    """
    )
    row = cur.fetchone()
    return float(row["total"]) if row and row["total"] is not None else 0.0


def get_positions_by_symbol(cur: cursor, symbol: str) -> list[dict[str, Any]]:
    """Get all positions for a specific symbol, ordered by creation time.

    In LOCAL_MODE: Uses base tables since materialized view requires elevated permissions.
    """
    if _is_local_mode():
        cur.execute(
            """
            SELECT
                p.position_id, p.symbol, p.entry_price, p.quantity,
                p.status, p.created_at, p.updated_at,
                COALESCE(p.entry_price * p.quantity, 0) as position_value,
                0 as daily_pnl, 0 as total_pnl
            FROM algo_positions p
            WHERE p.symbol = %s
            ORDER BY p.created_at DESC
        """,
            (symbol,),
        )
    else:
        cur.execute(
            """
            SELECT * FROM algo_positions_with_risk
            WHERE symbol = %s
            ORDER BY created_at DESC
        """,
            (symbol,),
        )
    return cur.fetchall()  # type: ignore
