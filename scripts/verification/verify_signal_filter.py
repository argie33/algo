#!/usr/bin/env python3
"""Verify the signal filtering issue"""
from utils.db.context import DatabaseContext

with DatabaseContext('read') as cur:
    # Check distinct values in signal column
    cur.execute("""
        SELECT DISTINCT signal FROM buy_sell_daily
        ORDER BY signal
    """)
    signal_vals = cur.fetchall()
    print("Distinct 'signal' column values:")
    for v in signal_vals:
        print(f"  {v}")

    # Check distinct values in signal_type column
    cur.execute("""
        SELECT DISTINCT signal_type FROM buy_sell_daily
        ORDER BY signal_type
    """)
    signal_type_vals = cur.fetchall()
    print("\nDistinct 'signal_type' column values:")
    for v in signal_type_vals:
        print(f"  {v}")

    # Check if Phase 7's filter would work
    cur.execute("""
        SELECT COUNT(*) as count
        FROM buy_sell_daily
        WHERE signal_type = 'BUY'
    """)
    count_signal_type_buy = cur.fetchone()
    print(f"\nCount WHERE signal_type = 'BUY': {count_signal_type_buy}")

    # Check if fixing to 'signal' column works
    cur.execute("""
        SELECT COUNT(*) as count
        FROM buy_sell_daily
        WHERE signal = 'BUY'
    """)
    count_signal_buy = cur.fetchone()
    print(f"Count WHERE signal = 'BUY': {count_signal_buy}")

    # Recent data - what's in the last few days?
    cur.execute("""
        SELECT DISTINCT date, signal, signal_type, COUNT(*) as cnt
        FROM buy_sell_daily
        WHERE date >= '2026-07-01'
        GROUP BY date, signal, signal_type
        ORDER BY date DESC, signal DESC
    """)
    recent = cur.fetchall()
    print("\nRecent buy_sell_daily (from July 1 onwards):")
    for r in recent:
        print(f"  {r}")
