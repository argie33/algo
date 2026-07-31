#!/usr/bin/env python3
"""Check scores database state to diagnose 'no data' issue."""

import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("psycopg2 not installed")
    sys.exit(1)

# Get DB connection
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("DATABASE_URL not set")
    sys.exit(1)

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Check stock_scores table
    print("=== STOCK_SCORES TABLE ===")
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN data_unavailable = false OR data_unavailable IS NULL THEN 1 END) as available,
            COUNT(CASE WHEN data_unavailable = true THEN 1 END) as unavailable,
            COUNT(CASE WHEN composite_score > 0 THEN 1 END) as has_score,
            COUNT(CASE WHEN composite_score IS NULL THEN 1 END) as null_score,
            MIN(data_completeness) as min_completeness,
            AVG(data_completeness) as avg_completeness,
            MAX(data_completeness) as max_completeness
        FROM stock_scores
    """)
    result = cur.fetchone()
    for key, value in result.items():
        print(f"  {key}: {value}")

    # Check actual scores that would be returned
    print("\n=== WOULD BE RETURNED BY API ===")
    cur.execute("""
        SELECT COUNT(*) as count
        FROM stock_scores sc
        JOIN stock_symbols ss ON ss.symbol = sc.symbol
        WHERE sc.composite_score > 0
        AND ss.symbol NOT IN (SELECT symbol FROM etf_symbols)
        AND (sc.data_unavailable = false OR sc.data_unavailable IS NULL)
        LIMIT 1000
    """)
    result = cur.fetchone()
    print(f"  Scores would return: {result['count']}")

    # Check what's being filtered out
    print("\n=== FILTERED OUT (composite_score <= 0) ===")
    cur.execute("""
        SELECT COUNT(*) as count FROM stock_scores WHERE composite_score <= 0
    """)
    print(f"  Count: {cur.fetchone()['count']}")

    print("\n=== FILTERED OUT (data_unavailable = true) ===")
    cur.execute("""
        SELECT COUNT(*) as count FROM stock_scores WHERE data_unavailable = true
    """)
    print(f"  Count: {cur.fetchone()['count']}")

    print("\n=== FILTERED OUT (NULL composite_score) ===")
    cur.fetchall()  # Clear results
    cur.execute("""
        SELECT COUNT(*) as count FROM stock_scores WHERE composite_score IS NULL
    """)
    print(f"  Count: {cur.fetchone()['count']}")

    # Check a sample of scores
    print("\n=== SAMPLE SCORES ===")
    cur.execute("""
        SELECT symbol, composite_score, data_unavailable, data_completeness
        FROM stock_scores
        ORDER BY composite_score DESC NULLS LAST
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"  {row['symbol']}: score={row['composite_score']}, unavailable={row['data_unavailable']}, completeness={row['data_completeness']}")

    conn.close()
    print("\n✓ Database check complete")

except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
