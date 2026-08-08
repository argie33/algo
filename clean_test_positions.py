#!/usr/bin/env python3
from utils.db import DatabaseContext

with DatabaseContext('write') as cur:
    # Delete trades FIRST (they reference positions)
    cur.execute("""
    DELETE FROM algo_trades
    WHERE status IN ('open', 'filled', 'partially_filled', 'paper_pending')
    AND DATE(created_at) = CURRENT_DATE
    """)
    deleted_trades = cur.rowcount

    # Then delete test positions
    cur.execute("DELETE FROM algo_positions WHERE status = 'open' AND days_since_entry = 0")
    deleted = cur.rowcount

    print(f"Deleted {deleted_trades} test trades")
    print(f"Deleted {deleted} open positions")
