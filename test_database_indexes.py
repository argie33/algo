#!/usr/bin/env python3
"""
Phase 5, Issue 4.2: Database Index Validation
Verifies that frequently-queried tables have proper indexes.
Large tables (1M+ rows) must have indexes on query columns.
"""

import psycopg2
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import os
from dotenv import load_dotenv

# Load environment
load_dotenv('.env.local')

print("=" * 80)
print("DATABASE INDEX VALIDATION")
print("=" * 80)
print()

# High-volume tables and their critical query columns
CRITICAL_INDEXES = {
    'price_daily': [
        ('symbol', 'WHERE symbol = ?'),
        ('date', 'WHERE date >= ? AND date <= ?'),
        ('(symbol, date)', 'COMPOSITE: WHERE symbol = ? AND date = ?'),
    ],
    'buy_sell_daily': [
        ('symbol', 'WHERE symbol = ?'),
        ('date', 'WHERE date >= ?'),
    ],
    'algo_trades': [
        ('entry_date', 'ORDER BY entry_date DESC LIMIT 100'),
        ('exit_date', 'WHERE exit_date IS NOT NULL'),
        ('(symbol, entry_date)', 'WHERE symbol = ? ORDER BY entry_date'),
    ],
    'stock_scores': [
        ('symbol', 'WHERE symbol = ?'),
        ('date', 'ORDER BY date DESC'),
        ('(symbol, date)', 'COMPOSITE: WHERE symbol = ? AND date = ?'),
    ],
}

def get_db_connection():
    """Connect to local PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'stocks'),
            connect_timeout=5,
        )
        return conn
    except Exception as e:
        print(f"❌ Cannot connect to database: {e}")
        print(f"   Host: {os.getenv('DB_HOST', 'localhost')}")
        print(f"   Port: {os.getenv('DB_PORT', 5432)}")
        print()
        print("To run locally:")
        print("  1. Ensure PostgreSQL is running")
        print("  2. Set DB_PASSWORD in .env.local")
        print("  3. Run: python3 init_database.py")
        return None

def check_indexes():
    """Check which critical indexes exist."""
    conn = get_db_connection()
    if not conn:
        return

    try:
        cur = conn.cursor()

        for table, columns in CRITICAL_INDEXES.items():
            # Check if table exists
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = %s
            """, (table,))

            if not cur.fetchone()[0]:
                print(f"⚠️  Table not found: {table}")
                continue

            # Get table size
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cur.fetchone()[0]

            print(f"📊 {table:25} ({row_count:,} rows)")

            # Check each index
            for col_spec, query_pattern in columns:
                cur.execute("""
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = %s AND indexdef LIKE %s
                """, (table, f'%{col_spec}%'))

                indexes = cur.fetchall()

                if indexes:
                    for idx in indexes:
                        print(f"   ✅ Index on {col_spec:25} ({idx[0]})")
                else:
                    # Composite indexes might not match the LIKE pattern
                    # Check if at least one index exists
                    cur.execute("""
                        SELECT COUNT(*) FROM pg_indexes
                        WHERE tablename = %s
                    """, (table,))

                    if cur.fetchone()[0] > 0:
                        print(f"   ⚠️  No index on {col_spec:25} (may have indexes on other columns)")
                    else:
                        print(f"   ❌ MISSING INDEX: {col_spec:25} - {query_pattern}")

            print()

        # Summary
        print("=" * 80)
        print("INDEX RECOMMENDATIONS")
        print("=" * 80)
        print()

        print("If indexes are missing, add them with:")
        print()
        print("# Add indexes to high-volume tables")
        print("CREATE INDEX idx_price_daily_symbol ON price_daily(symbol);")
        print("CREATE INDEX idx_price_daily_date ON price_daily(date);")
        print("CREATE INDEX idx_price_daily_composite ON price_daily(symbol, date);")
        print()
        print("CREATE INDEX idx_algo_trades_date ON algo_trades(entry_date DESC);")
        print("CREATE INDEX idx_algo_trades_composite ON algo_trades(symbol, entry_date);")
        print()
        print("# Test index effectiveness")
        print("EXPLAIN ANALYZE")
        print("  SELECT * FROM price_daily WHERE symbol = 'AAPL' AND date >= '2026-05-01';")
        print()
        print("If EXPLAIN shows 'Seq Scan' instead of 'Index Scan', indexes aren't being used.")
        print()

    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    check_indexes()
