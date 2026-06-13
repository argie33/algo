#!/usr/bin/env python3
"""Diagnose why price loader is only loading 4800 symbols instead of 10500."""
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

print("=== Price Loader Diagnosis ===\n")

# Check loader execution history
cur.execute("""
    SELECT
        loader_name,
        status,
        symbols_processed,
        symbols_successful,
        symbols_failed,
        execution_started,
        execution_completed,
        error_message
    FROM loader_execution_history
    WHERE loader_name LIKE '%price%'
    ORDER BY execution_started DESC
    LIMIT 10
""")

print("Recent price loader executions:")
for loader, status, proc, success, failed, started, completed, error in cur.fetchall():
    duration = (completed - started).total_seconds() if completed else None
    print(f"\n  {started.strftime('%Y-%m-%d %H:%M:%S')} | {loader}")
    print(f"    Status: {status}")
    print(f"    Processed: {proc}, Success: {success}, Failed: {failed}")
    if error:
        print(f"    Error: {error[:100]}")
    if duration:
        print(f"    Duration: {duration:.0f}s")

# Check if there are any recent errors in the logs
print("\n\n=== Check loader_sla_status ===")
cur.execute("""
    SELECT
        loader_name,
        status,
        last_run,
        last_completion,
        expected_frequency_minutes,
        minutes_since_completion,
        alert_sent_at
    FROM loader_sla_status
    WHERE loader_name LIKE '%price%'
""")

for name, status, last_run, last_comp, freq, mins, alert in cur.fetchall():
    print(f"\n{name}:")
    print(f"  Status: {status}")
    print(f"  Last run: {last_run}")
    print(f"  Last completion: {last_comp}")
    print(f"  Minutes since completion: {mins}")

conn.close()

print("\n\n=== Summary ===")
print("If symbols_successful is ~4800 and then stops, likely causes:")
print("1. Rate limit hit - yfinance API returning 429")
print("2. Database connection timeout")
print("3. Thread pool exhaustion")
print("4. Memory exhaustion during batch processing")
print("5. Network timeout talking to yfinance")
