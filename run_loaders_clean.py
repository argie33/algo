#!/usr/bin/env python3
"""Clear locks and run loaders with new max_fail_rate settings."""

import psycopg2
import subprocess

conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()

# Clear recent locks
cur.execute("""
    DELETE FROM loader_execution_locks
    WHERE loader_name IN ('insider_transaction_velocity', 'sec_segment_info', 'dividend_data')
    AND locked_at > NOW() - INTERVAL '1 hour'
""")
conn.commit()
print(f"✓ Cleared {cur.rowcount} stuck locks\n")

# Run loaders with AAPL only
print("Running loaders with max_fail_rate adjustments...")
print("=" * 60)

loaders = [
    ("dividend_data", "load_dividend_data.py"),
    ("segment_info", "load_sec_segment_info.py"),
    ("insider_velocity", "load_insider_transaction_velocity.py"),
]

for name, script in loaders:
    print(f"\n▶ {name}...")
    result = subprocess.run(
        ["python", f"loaders/{script}", "--symbols", "AAPL", "--parallelism", "1"],
        capture_output=True,
        text=True,
        timeout=300
    )

    # Check for success marker
    if "[OK]" in result.stderr or "success" in result.stderr.lower():
        print(f"  ✓ Completed successfully")
    elif "FAILED" in result.stderr or result.returncode != 0:
        print(f"  ✗ Failed (return code {result.returncode})")
        # Show error
        for line in result.stderr.split('\n'):
            if 'ERROR' in line or 'FAILED' in line or 'threshold' in line:
                print(f"    {line[:100]}")
    else:
        print(f"  ? Unknown status")

# Check what was written
print("\n" + "=" * 60)
print("DATA WRITTEN TO DATABASE:")
print("=" * 60)

cur.execute("""
    SELECT
        'dividend_data' as table_name,
        COUNT(*) as total_rows,
        COUNT(DISTINCT symbol) as symbols,
        COUNT(CASE WHEN NOT data_unavailable THEN 1 END) as real_data_rows
    FROM dividend_data
    UNION ALL
    SELECT
        'sec_segment_info',
        COUNT(*),
        COUNT(DISTINCT symbol),
        COUNT(CASE WHEN NOT data_unavailable THEN 1 END)
    FROM sec_segment_info
    UNION ALL
    SELECT
        'insider_transaction_velocity',
        COUNT(*),
        COUNT(DISTINCT symbol),
        COUNT(CASE WHEN NOT data_unavailable THEN 1 END)
    FROM insider_transaction_velocity
    ORDER BY table_name
""")

for table_name, total, symbols, real_data in cur.fetchall():
    print(f"\n{table_name}:")
    print(f"  Total rows: {total}")
    print(f"  Unique symbols: {symbols}")
    print(f"  Real data rows: {real_data}")

conn.close()
