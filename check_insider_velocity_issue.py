#!/usr/bin/env python3
"""Check why insider velocity loader isn't writing data."""

import psycopg2

conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()

print("=" * 60)
print("INSIDER VELOCITY LOADER STATUS")
print("=" * 60)

# Latest execution
cur.execute("""
    SELECT status, execution_start, execution_end, error_message
    FROM loader_execution_history
    WHERE loader_name = 'insider_transaction_velocity'
    ORDER BY execution_start DESC
    LIMIT 3
""")

print("\nLatest 3 execution attempts:")
for status, start, end, error in cur.fetchall():
    print(f"\n  {status} at {start}")
    if error and error.strip():
        error_short = error[:150] + "..." if len(error) > 150 else error
        print(f"    Error: {error_short}")

# Check the actual table
cur.execute("""
    SELECT COUNT(*) FROM insider_transaction_velocity
""")
count = cur.fetchone()[0]
print(f"\nRows in insider_transaction_velocity table: {count}")

# If there's data, show it
if count > 0:
    cur.execute("""
        SELECT symbol, measurement_date, data_unavailable, data_unavailable_reason
        FROM insider_transaction_velocity
        LIMIT 5
    """)
    print("\nSample data:")
    for symbol, date, unavail, reason in cur.fetchall():
        print(f"  {symbol} on {date}: unavailable={unavail}, reason={reason}")

# Check locks
cur.execute("""
    SELECT loader_name, locked_at, expires_at
    FROM loader_execution_locks
    WHERE loader_name = 'insider_transaction_velocity'
""")

locks = cur.fetchall()
if locks:
    print(f"\nActive locks: {len(locks)}")
    for name, locked_at, expires_at in locks:
        print(f"  Locked since {locked_at}, expires {expires_at}")
else:
    print("\nNo active locks")

conn.close()
