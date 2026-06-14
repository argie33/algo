#!/usr/bin/env python3
"""
Validate that FK constraints can be safely added to buy_sell_daily and technical_data_daily.

This script checks for orphaned records that would violate the new FKs:
- buy_sell_daily rows without corresponding price_daily records
- technical_data_daily rows without corresponding price_daily records

If any orphaned records are found, they are logged and the script fails.
Otherwise, it prints a success message.
"""

import sys
import logging
from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_orphaned_records():
    """Check for records that would violate the new FKs."""
    with DatabaseContext('read') as cur:
        # Check buy_sell_daily → price_daily
        cur.execute("""
            SELECT COUNT(*)
            FROM buy_sell_daily bsd
            LEFT JOIN price_daily pd ON bsd.symbol = pd.symbol AND bsd.date = pd.date
            WHERE pd.id IS NULL
        """)
        orphaned_buy_sell = cur.fetchone()[0]
        
        # Check technical_data_daily → price_daily
        cur.execute("""
            SELECT COUNT(*)
            FROM technical_data_daily tdd
            LEFT JOIN price_daily pd ON tdd.symbol = pd.symbol AND tdd.date = pd.date
            WHERE pd.id IS NULL
        """)
        orphaned_technical = cur.fetchone()[0]
    
    if orphaned_buy_sell > 0:
        logger.error(f"Found {orphaned_buy_sell} orphaned buy_sell_daily records")
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT DISTINCT bsd.symbol, bsd.date, COUNT(*) as count
                FROM buy_sell_daily bsd
                LEFT JOIN price_daily pd ON bsd.symbol = pd.symbol AND bsd.date = pd.date
                WHERE pd.id IS NULL
                GROUP BY bsd.symbol, bsd.date
                ORDER BY count DESC, bsd.date DESC
                LIMIT 10
            """)
            for symbol, date, count in cur.fetchall():
                logger.error(f"  {symbol} {date}: {count} records")
    
    if orphaned_technical > 0:
        logger.error(f"Found {orphaned_technical} orphaned technical_data_daily records")
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT DISTINCT tdd.symbol, tdd.date, COUNT(*) as count
                FROM technical_data_daily tdd
                LEFT JOIN price_daily pd ON tdd.symbol = pd.symbol AND tdd.date = pd.date
                WHERE pd.id IS NULL
                GROUP BY tdd.symbol, tdd.date
                ORDER BY count DESC, tdd.date DESC
                LIMIT 10
            """)
            for symbol, date, count in cur.fetchall():
                logger.error(f"  {symbol} {date}: {count} records")
    
    if orphaned_buy_sell == 0 and orphaned_technical == 0:
        logger.info("✓ No orphaned records found. FK constraints can be safely applied.")
        return True
    else:
        logger.error("✗ Orphaned records detected. Fix these before applying FK constraints.")
        return False

if __name__ == '__main__':
    success = check_orphaned_records()
    sys.exit(0 if success else 1)
