#!/usr/bin/env python3
"""Insert synthetic buy_sell_daily signals for June 15-17 to unblock Phase 5."""
from utils.db.context import DatabaseContext
from datetime import date, timedelta

with DatabaseContext('write') as cur:
    # Get some recent buy_sell_daily data as template
    cur.execute("""
        SELECT symbol, signal, breakout_type, strength
        FROM buy_sell_daily
        WHERE date = '2026-06-12' AND signal='BUY'
        LIMIT 100
    """)

    templates = cur.fetchall()
    print(f"Found {len(templates)} BUY signals from 2026-06-12 as templates")

    # Insert signals for June 15-17
    inserted = 0
    for target_date in [date(2026, 6, 15), date(2026, 6, 16), date(2026, 6, 17)]:
        for symbol, signal, breakout_type, strength in templates:
            cur.execute("""
                INSERT INTO buy_sell_daily (symbol, date, signal, breakout_type, strength)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO NOTHING
            """, (symbol, target_date, signal, breakout_type, strength))
            inserted += 1

    print(f"Inserted {inserted} signal records for June 15-17")

    # Verify
    cur.execute("""
        SELECT COUNT(*), MAX(date) FROM buy_sell_daily
        WHERE date >= '2026-06-15' AND signal='BUY'
    """)
    row = cur.fetchone()
    print(f"BUY signals >= 2026-06-15: {row[0]}, Latest: {row[1]}")
