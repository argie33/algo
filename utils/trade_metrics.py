"""Calculate trade metrics: exit_r_multiple, duration, MFE/MAE, exit_time."""

from datetime import datetime, date
from decimal import Decimal
from typing import Any

from psycopg2.extensions import cursor


def calculate_exit_r_multiple(
    entry_price: Decimal | float,
    exit_price: Decimal | float,
    stop_loss_price: Decimal | float,
) -> Decimal | None:
    """Calculate R-multiple (risk-adjusted return).

    R = (exit_price - entry_price) / (entry_price - stop_loss_price)

    Returns None if stop_loss_price is invalid or would cause division by zero.
    """
    try:
        entry = Decimal(str(entry_price))
        exit_p = Decimal(str(exit_price))
        stop = Decimal(str(stop_loss_price))

        risk = entry - stop
        if risk <= 0:
            return None

        return (exit_p - entry) / risk
    except (TypeError, ValueError, ArithmeticError):
        return None


def calculate_trade_duration_days(
    entry_date: date | None,
    exit_date: date | None,
) -> int | None:
    """Calculate trade duration in days.

    Returns None if dates are missing or invalid.
    """
    if not entry_date or not exit_date:
        return None

    try:
        if isinstance(entry_date, str):
            entry_date = datetime.fromisoformat(entry_date).date()
        if isinstance(exit_date, str):
            exit_date = datetime.fromisoformat(exit_date).date()

        delta = exit_date - entry_date
        return delta.days
    except (TypeError, ValueError):
        return None


def calculate_mfe_pct(
    cur: cursor,
    symbol: str,
    entry_price: Decimal | float,
    entry_date: date | None,
    exit_date: date | None,
) -> Decimal | None:
    """Calculate Maximum Favorable Excursion % after entry.

    MFE % = (max_price - entry_price) / entry_price * 100
    Only considers prices from entry_date to exit_date.

    Returns None if data unavailable.
    """
    if not entry_date or not exit_date:
        return None

    try:
        cur.execute(
            """
            SELECT MAX(high) as max_price
            FROM price_daily
            WHERE symbol = %s
              AND date >= %s
              AND date <= %s
        """,
            (symbol, entry_date, exit_date),
        )
        row = cur.fetchone()
        if not row or row["max_price"] is None:
            return None

        max_price = Decimal(str(row["max_price"]))
        entry = Decimal(str(entry_price))

        if entry <= 0:
            return None

        return ((max_price - entry) / entry) * 100
    except Exception:
        return None


def calculate_mae_pct(
    cur: cursor,
    symbol: str,
    entry_price: Decimal | float,
    entry_date: date | None,
    exit_date: date | None,
) -> Decimal | None:
    """Calculate Maximum Adverse Excursion % after entry.

    MAE % = (min_price - entry_price) / entry_price * 100
    Only considers prices from entry_date to exit_date.

    Returns None if data unavailable.
    """
    if not entry_date or not exit_date:
        return None

    try:
        cur.execute(
            """
            SELECT MIN(low) as min_price
            FROM price_daily
            WHERE symbol = %s
              AND date >= %s
              AND date <= %s
        """,
            (symbol, entry_date, exit_date),
        )
        row = cur.fetchone()
        if not row or row["min_price"] is None:
            return None

        min_price = Decimal(str(row["min_price"]))
        entry = Decimal(str(entry_price))

        if entry <= 0:
            return None

        return ((min_price - entry) / entry) * 100
    except Exception:
        return None


def update_trade_metrics(cur: cursor, trade_id: str) -> dict[str, Any]:
    """Calculate and update all metrics for a trade.

    Fetches trade data, calculates all metrics, updates database, returns results.
    """
    # Fetch trade
    cur.execute(
        """
        SELECT trade_id, symbol, entry_price, entry_date, entry_time,
               exit_price, exit_date, exit_time, stop_loss_price, status
        FROM algo_trades
        WHERE trade_id = %s
    """,
        (trade_id,),
    )
    trade = cur.fetchone()
    if not trade:
        return {"error": f"Trade {trade_id} not found"}

    if trade["status"] != "closed" or not trade["exit_price"]:
        return {"error": f"Trade {trade_id} is not closed or has no exit_price"}

    # Calculate metrics
    exit_r = calculate_exit_r_multiple(
        trade["entry_price"], trade["exit_price"], trade["stop_loss_price"]
    )
    duration = calculate_trade_duration_days(trade["entry_date"], trade["exit_date"])
    mfe = calculate_mfe_pct(
        cur, trade["symbol"], trade["entry_price"], trade["entry_date"], trade["exit_date"]
    )
    mae = calculate_mae_pct(
        cur, trade["symbol"], trade["entry_price"], trade["entry_date"], trade["exit_date"]
    )

    # Use exit_time from trade, or derive from exit_date if missing
    exit_time = trade["exit_time"]
    if not exit_time and trade["exit_date"]:
        # Set to end of trading day (4 PM ET) if not specified
        exit_time = datetime.combine(trade["exit_date"], datetime.min.time()).replace(
            hour=16, minute=0
        )

    # Update database
    cur.execute(
        """
        UPDATE algo_trades
        SET exit_r_multiple = %s,
            trade_duration_days = %s,
            mfe_pct = %s,
            mae_pct = %s,
            exit_time = %s,
            updated_at = NOW()
        WHERE trade_id = %s
    """,
        (exit_r, duration, mfe, mae, exit_time, trade_id),
    )

    return {
        "trade_id": trade_id,
        "exit_r_multiple": float(exit_r) if exit_r else None,
        "trade_duration_days": duration,
        "mfe_pct": float(mfe) if mfe else None,
        "mae_pct": float(mae) if mae else None,
        "exit_time": str(exit_time) if exit_time else None,
    }


def backfill_all_trade_metrics(cur: cursor) -> dict[str, Any]:
    """Calculate metrics for all closed trades without exit_r_multiple.

    Returns summary of updates.
    """
    # Find trades that need metrics calculated
    cur.execute(
        """
        SELECT trade_id FROM algo_trades
        WHERE status = 'closed'
          AND exit_price IS NOT NULL
          AND exit_r_multiple IS NULL
        ORDER BY trade_id
    """
    )
    trades = cur.fetchall()

    if not trades:
        return {"message": "No trades need metric calculation"}

    results = []
    for trade in trades:
        result = update_trade_metrics(cur, trade["trade_id"])
        results.append(result)

    return {
        "total_updated": len(results),
        "results": results,
    }
