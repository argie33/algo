#!/usr/bin/env python3
"""Check database data loading status"""

import psycopg2
import os
import sys
import io
from dotenv import load_dotenv

# Fix Unicode encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv('.env.local')

db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'stocks'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'stocks')
}

try:
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    # Check table row counts
    tables = [
        'stock_symbols',
        'price_daily',
        'earnings_history',
        'earnings_estimates',
        'company_profile',
        'key_metrics',
        'economic_data',
        'quality_metrics',
        'growth_metrics',
        'momentum_metrics',
        'stability_metrics',
        'value_metrics',
        'positioning_metrics',
        'portfolio_holdings',
        'portfolio_performance',
        'trades',
    ]

    print("=" * 70)
    print("DATABASE DATA LOADING STATUS")
    print("=" * 70)

    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            status = "✓ OK" if count > 0 else "✗ EMPTY"
            print(f"{table:30} {count:10,} {status}")
        except Exception as e:
            print(f"{table:30} ERROR: {str(e)[:50]}")

    print("=" * 70)

    # Check for NULL values in key tables
    print("\nNULL VALUE CHECK (Earnings)")
    print("-" * 70)
    cur.execute("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN eps_actual IS NOT NULL THEN 1 END) as has_eps_actual,
               COUNT(CASE WHEN revenue_actual IS NOT NULL THEN 1 END) as has_revenue_actual
        FROM earnings_estimates
    """)
    result = cur.fetchone()
    print(f"Total records: {result[0]:,}")
    print(f"With EPS actual: {result[1]:,}")
    print(f"With revenue actual: {result[2]:,}")
    print(f"Empty records: {result[0] - max(result[1], result[2]):,}")

    conn.close()

except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
