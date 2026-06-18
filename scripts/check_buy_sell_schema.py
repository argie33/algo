#!/usr/bin/env python3
from utils.db.context import DatabaseContext


with DatabaseContext('read') as cur:
    # Get table structure
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'buy_sell_daily'
        ORDER BY ordinal_position
    """)
    print("buy_sell_daily columns:")
    for row in cur.fetchall():
        print(f"  {row[0]:20s} {row[1]}")

    # Get sample row
    cur.execute("SELECT * FROM buy_sell_daily WHERE date = '2026-06-12' LIMIT 1")
    cols = [desc[0] for desc in cur.description]
    row = cur.fetchone()
    print(f"\nSample row: {dict(zip(cols, row))}")
