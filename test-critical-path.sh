#!/bin/bash
# CRITICAL PATH TEST SUITE
# Tests the core pipeline locally before AWS deployment
# Usage: bash test-critical-path.sh

set -e  # Exit on error

echo "=========================================="
echo "CRITICAL PATH TEST SUITE"
echo "=========================================="
echo ""

# Test 1.1: Data Pipeline
echo "TIER 1.1: DATA PIPELINE VALIDATION"
echo "=================================="
echo "Initializing database..."
python3 init_database.py

if [ $? -eq 0 ]; then
    echo "✓ Database initialized"
else
    echo "✗ Database initialization failed"
    exit 1
fi

echo ""
echo "Running all data loaders..."
python3 run-all-loaders.py

if [ $? -eq 0 ]; then
    echo "✓ All loaders completed"
else
    echo "✗ Loader pipeline failed"
    exit 1
fi

echo ""
echo "VERIFICATION CHECKS:"
echo "Checking database tables..."
python3 << 'EOF'
import psycopg2
import os
from credential_helper import get_db_password, get_db_config

try:
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cur = conn.cursor()

    # Check table counts
    tables_to_check = [
        ('stock_symbols', 1000),
        ('stock_scores', 1000),
        ('price_daily', 50000),
        ('technical_data', 50000),
        ('quality_metrics', 500),
        ('growth_metrics', 500),
        ('value_metrics', 500),
    ]

    print("\nTable Row Counts:")
    print("-" * 50)
    all_pass = True
    for table, min_count in tables_to_check:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        status = "✓" if count >= min_count else "✗"
        print(f"{status} {table:30} {count:>8} rows")
        if count < min_count:
            all_pass = False

    # Check data freshness
    print("\nData Freshness (Most Recent Dates):")
    print("-" * 50)
    cur.execute("SELECT MAX(date) FROM price_daily")
    latest_price = cur.fetchone()[0]
    print(f"Price data:     {latest_price}")

    cur.execute("SELECT MAX(updated_at) FROM stock_scores")
    latest_scores = cur.fetchone()[0]
    print(f"Stock scores:   {latest_scores}")

    cur.execute("SELECT MAX(date) FROM technical_data")
    latest_tech = cur.fetchone()[0]
    print(f"Technical data: {latest_tech}")

    conn.close()

    if all_pass:
        print("\n✓ All table counts pass minimum thresholds")
    else:
        print("\n✗ Some tables have insufficient data")
        exit(1)

except Exception as e:
    print(f"✗ Database check failed: {e}")
    exit(1)
EOF

echo ""
echo "=========================================="
echo "TIER 1.2: ORCHESTRATOR DRY-RUN"
echo "=========================================="
python3 algo_orchestrator.py --mode paper --dry-run

if [ $? -eq 0 ]; then
    echo "✓ Orchestrator dry-run completed all 7 phases"
else
    echo "✗ Orchestrator dry-run failed"
    exit 1
fi

echo ""
echo "=========================================="
echo "TIER 1.3: DATA CONSISTENCY"
echo "=========================================="
python3 << 'EOF'
import psycopg2
from credential_helper import get_db_config
from datetime import datetime, timedelta

config = get_db_config()
conn = psycopg2.connect(**config)
cur = conn.cursor()

print("Checking for orphaned/duplicate records...")
print("-" * 50)

# Check for duplicates
cur.execute("""
SELECT symbol, date, COUNT(*)
FROM price_daily
GROUP BY symbol, date
HAVING COUNT(*) > 1
LIMIT 10
""")
dups = cur.fetchall()
if dups:
    print(f"⚠ Found {len(dups)} duplicate price records (sample):")
    for sym, date, count in dups:
        print(f"  {sym} {date}: {count} copies")
else:
    print("✓ No duplicate price records found")

# Check for NULL values where not expected
cur.execute("""
SELECT COUNT(*) FROM stock_scores
WHERE composite_score IS NULL
""")
nulls = cur.fetchone()[0]
if nulls > 0:
    print(f"⚠ Found {nulls} NULL composite_scores")
else:
    print("✓ No NULL values in critical score columns")

print("-" * 50)
print("✓ Data consistency checks complete")

conn.close()
EOF

echo ""
echo "=========================================="
echo "✓ CRITICAL PATH TESTS COMPLETE"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Run frontend manual tests (open browser and test 30+ pages)"
echo "2. Run paper trading: python3 algo_orchestrator.py --mode paper"
echo "3. Monitor Alpaca account for 24-48 hours"
echo "4. Check CloudWatch logs"
echo ""
