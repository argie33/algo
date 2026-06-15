#!/usr/bin/env python3
"""Check how much price history we have."""

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

print("=== Price Data Freshness Analysis ===\n")

# Check date range in price_daily
cur.execute("""
    SELECT
        MIN(date) as oldest_date,
        MAX(date) as newest_date,
        COUNT(DISTINCT date) as unique_dates,
        COUNT(DISTINCT symbol) as unique_symbols,
        COUNT(*) as total_records
    FROM price_daily
""")

oldest, newest, dates, symbols, total = cur.fetchone()
print("Price data range:")
print(f"  Oldest: {oldest}")
print(f"  Newest: {newest}")
print(f"  Span: {(newest - oldest).days} days")
print(f"  Unique trading dates: {dates}")
print(f"  Unique symbols: {symbols}")
print(f"  Total records: {total}")

if symbols and total:
    avg_per_symbol = total / symbols
    print(f"  Avg records per symbol: {avg_per_symbol:.0f}")

print("\nIf we need 1 year (252 trading days) × 10,506 symbols:")
print(f"  Expected records: {252 * 10506:,}")
print(f"  Actual records: {total:,}")
print(f"  Deficit: {max(0, 252 * 10506 - total):,}")

# Check the last load - when was the most recent batch?
cur.execute("""
    SELECT
        DATE(date),
        COUNT(DISTINCT symbol) as symbol_count
    FROM price_daily
    WHERE date >= CURRENT_DATE - INTERVAL '5 days'
    GROUP BY DATE(date)
    ORDER BY date DESC
""")

print("\n\nRecent price data by date:")
for date, count in cur.fetchall():
    print(f"  {date}: {count} symbols")

# Check if the loader is supposed to backfill
print("\n\nChecking loader configuration...")
cur.execute("""
    SELECT key, value FROM algo_config
    WHERE key LIKE '%loader%' OR key LIKE '%backfill%'
    ORDER BY key
""")

for key, val in cur.fetchall():
    print(f"  {key}: {val}")

conn.close()
