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
import logging

logger = logging.getLogger(__name__)

# Load environment
load_dotenv('.env.local')

logger.info("=" * 80)
logger.info("DATABASE INDEX VALIDATION")
logger.info("=" * 80)
logger.info()

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
        logger.info(f"[FAIL] Cannot connect to database: {e}")
        logger.info(f"   Host: {os.getenv('DB_HOST', 'localhost')}")
        logger.info(f"   Port: {os.getenv('DB_PORT', 5432)}")
        logger.info()
        logger.info("To run locally:")
        logger.info("  1. Ensure PostgreSQL is running")
        logger.info("  2. Set DB_PASSWORD in .env.local")
        logger.info("  3. Run: python3 init_database.py")
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
                logger.info(f"[WARN]  Table not found: {table}")
                continue

            # Get table size
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cur.fetchone()[0]

            logger.info(f"[TABLE] {table:25} ({row_count:,} rows)")

            # Check each index
            for col_spec, query_pattern in columns:
                cur.execute("""
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = %s AND indexdef LIKE %s
                """, (table, f'%{col_spec}%'))

                indexes = cur.fetchall()

                if indexes:
                    for idx in indexes:
                        logger.info(f"   [OK] Index on {col_spec:25} ({idx[0]})")
                else:
                    # Composite indexes might not match the LIKE pattern
                    # Check if at least one index exists
                    cur.execute("""
                        SELECT COUNT(*) FROM pg_indexes
                        WHERE tablename = %s
                    """, (table,))

                    if cur.fetchone()[0] > 0:
                        logger.info(f"   [WARN]  No index on {col_spec:25} (may have indexes on other columns)")
                    else:
                        logger.info(f"   [FAIL] MISSING INDEX: {col_spec:25} - {query_pattern}")

            logger.info()

        # Summary
        logger.info("=" * 80)
        logger.info("INDEX RECOMMENDATIONS")
        logger.info("=" * 80)
        logger.info()

        logger.info("If indexes are missing, add them with:")
        logger.info()
        logger.info("# Add indexes to high-volume tables")
        logger.info("CREATE INDEX idx_price_daily_symbol ON price_daily(symbol);")
        logger.info("CREATE INDEX idx_price_daily_date ON price_daily(date);")
        logger.info("CREATE INDEX idx_price_daily_composite ON price_daily(symbol, date);")
        logger.info()
        logger.info("CREATE INDEX idx_algo_trades_date ON algo_trades(entry_date DESC);")
        logger.info("CREATE INDEX idx_algo_trades_composite ON algo_trades(symbol, entry_date);")
        logger.info()
        logger.info("# Test index effectiveness")
        logger.info("EXPLAIN ANALYZE")
        logger.info("  SELECT * FROM price_daily WHERE symbol = 'AAPL' AND date >= '2026-05-01';")
        logger.info()
        logger.info("If EXPLAIN shows 'Seq Scan' instead of 'Index Scan', indexes aren't being used.")
        logger.info()

    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    check_indexes()
