#!/usr/bin/env python3
"""Debug why price loader stops at 4800 symbols."""
import psycopg2
import os
from datetime import datetime, timedelta

conn = psycopg2.connect(
    host=os.environ['DB_HOST'],
    port=os.environ['DB_PORT'],
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'],
    database=os.environ['DB_NAME']
)
cur = conn.cursor()

print("=== Debugging Price Loader Failure ===\n")

# Get schema
cur.execute("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'data_loader_runs'
    ORDER BY ordinal_position
""")
cols = [row[0] for row in cur.fetchall()]
print("Columns in data_loader_runs:", cols[:10], "...\n")

# Find price loader runs from June 11-13
cur.execute("""
    SELECT
        loader_name,
        started_at,
        completed_at,
        records_loaded,
        records_updated,
        error_message,
        duration_seconds
    FROM data_loader_runs
    WHERE loader_name LIKE '%price%'
        AND started_at > NOW() - INTERVAL '3 days'
    ORDER BY started_at DESC
    LIMIT 10
""")

print("Price loader runs (last 3 days):\n")
rows = cur.fetchall()
for loader, started, completed, loaded, updated, error, duration in rows:
    if started:
        print(f"{started.strftime('%Y-%m-%d %H:%M:%S')} | {loader}")
        print(f"  Loaded: {loaded}, Updated: {updated}")
        if error:
            print(f"  Error: {error[:120]}")
        if duration:
            print(f"  Duration: {duration:.0f}s")
        print()

# Check if there's a pattern - do all runs stop at same point?
print("\n=== Checking for pattern ===")
cur.execute("""
    SELECT
        DATE(started_at) as run_date,
        COUNT(*) as run_count,
        AVG(records_loaded) as avg_loaded,
        MIN(records_loaded) as min_loaded,
        MAX(records_loaded) as max_loaded
    FROM data_loader_runs
    WHERE loader_name LIKE '%price%'
        AND started_at > NOW() - INTERVAL '7 days'
    GROUP BY DATE(started_at)
    ORDER BY run_date DESC
""")

for date, count, avg_loaded, min_loaded, max_loaded in cur.fetchall():
    print(f"{date}: {count} runs | Loaded: min={min_loaded}, avg={avg_loaded:.0f}, max={max_loaded}")

conn.close()
