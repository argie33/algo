#!/usr/bin/env python3
"""Check why get_active_symbols only returns 5,256 instead of 10,506."""
import psycopg2
import os
from utils.loaders.helpers import get_active_symbols

# Check via function
active_via_func = list(get_active_symbols())
print(f"get_active_symbols() returns: {len(active_via_func)} symbols")

# Check via database
conn = psycopg2.connect(
    host=os.environ['DB_HOST'],
    port=os.environ['DB_PORT'],
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'],
    database=os.environ['DB_NAME']
)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
count_active = cur.fetchone()[0]
print(f"stock_symbols WHERE active=true: {count_active}")

cur.execute("SELECT COUNT(*) FROM stock_symbols")
count_total = cur.fetchone()[0]
print(f"stock_symbols total: {count_total}")

# Check inactive breakdown
cur.execute("""
    SELECT active, COUNT(*) as count
    FROM stock_symbols
    GROUP BY active
""")

print("\nBreakdown:")
for active, count in cur.fetchall():
    print(f"  active={active}: {count:,}")

conn.close()

print("\n[ISSUE] get_active_symbols() is filtering out symbols that should be loaded")
