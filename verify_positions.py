#!/usr/bin/env python3
"""Verify positions data."""

from utils.db import DatabaseContext

with DatabaseContext("read") as cur:
    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
    count = cur.fetchone()[0]
    print(f"Positions in database: {count}")

    if count > 0:
        cur.execute("SELECT symbol FROM algo_positions WHERE status = 'open' ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]
        print(f"Symbols: {', '.join(symbols)}")
