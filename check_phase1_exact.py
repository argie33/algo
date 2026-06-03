#!/usr/bin/env python3
import psycopg2
import os
from datetime import date

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'), port=5432, user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME')
)
cur = conn.cursor()

# Exactly as Phase 1 does it
print("Checking with exact Phase 1 queries:")

try:
    cur.execute("SELECT date FROM price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 1")
    row = cur.fetchone()
    spy_date = row[0] if row else None
    print(f"price_daily SPY: {spy_date}")
except Exception as e:
    print(f"price_daily SPY: ERROR - {e}")

try:
    cur.execute("SELECT date FROM market_health_daily ORDER BY date DESC LIMIT 1")
    row = cur.fetchone()
    mh_date = row[0] if row else None
    print(f"market_health_daily: {mh_date}")
except Exception as e:
    print(f"market_health_daily: ERROR - {e}")

try:
    cur.execute("SELECT date FROM trend_template_data WHERE symbol='SPY' ORDER BY date DESC LIMIT 1")
    row = cur.fetchone()
    tt_date = row[0] if row else None
    print(f"trend_template_data SPY: {tt_date}")
except Exception as e:
    print(f"trend_template_data SPY: ERROR - {e}")

# Check expected date
expected_date = date(2026, 6, 2)
print(f"\nExpected date: {expected_date}")
print(f"Stale items:")
for name, d in [("SPY price", spy_date), ("Market health", mh_date), ("Trend template", tt_date)]:
    if d is None:
        print(f"  {name}: MISSING")
    elif d < expected_date:
        age = (date(2026, 6, 3) - d).days
        print(f"  {name}: {d} ({age}d old)")
    else:
        print(f"  {name}: OK")

cur.close()
conn.close()
