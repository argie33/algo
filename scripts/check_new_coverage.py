#!/usr/bin/env python3
"""Check current price coverage after loader run."""

import psycopg2
import os

conn = psycopg2.connect(
    host=os.environ["DB_HOST"],
    port=os.environ["DB_PORT"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    database=os.environ["DB_NAME"],
)
cur = conn.cursor()

# Check current coverage
cur.execute("""
    SELECT date, COUNT(DISTINCT symbol) as symbol_count
    FROM price_daily
    GROUP BY date
    ORDER BY date DESC
    LIMIT 5
""")

print("=== Current Price Coverage ===\n")
print("Top 5 most recent dates:")
for date_val, count in cur.fetchall():
    coverage = "????" if count < 8000 else "PASS" if count >= 8000 else "WARN"
    print(f"  {date_val}: {count:,} symbols [{coverage}]")

# Check how many active symbols should be loaded
cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
total_active = cur.fetchone()[0]
print(f"\nTotal active symbols in database: {total_active:,}")

# Get the latest date
cur.execute("SELECT MAX(date) FROM price_daily")
latest_date = cur.fetchone()[0]

if latest_date:
    cur.execute(
        """
        SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s
    """,
        (latest_date,),
    )
    latest_count = cur.fetchone()[0]
    print(f"Latest date {latest_date}: {latest_count:,} symbols")
    print(f"Coverage: {latest_count/total_active*100:.1f}%")
    print("Phase 1 requirement: 8,000 symbols")

    if latest_count >= 8000:
        print("\n[PASS] System will pass Phase 1 check!")
    else:
        print(f"\n[FAIL] System will FAIL Phase 1 check: {latest_count} < 8000")

conn.close()
