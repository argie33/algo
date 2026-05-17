#!/usr/bin/env python3
"""
Migration: Convert symbol format from dots to hyphens (BRK.B -> BRK-B)

yfinance expects hyphens for multi-class shares. This script updates:
1. stock_symbols table
2. All price_* tables
3. All signal tables
4. All audit tables

Usage:
  python3 migrate_symbols_dots_to_hyphens.py [--dry-run]

Options:
  --dry-run   Show what would change without making changes
"""

from config.credential_helper import get_db_password, get_db_config
try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import sys
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": get_db_password(),
    "database": os.getenv("DB_NAME", "stocks"),
    }

# Tables with symbol column that need updating
TABLES_WITH_SYMBOLS = [
    "stock_symbols",
    "price_daily",
    "price_weekly",
    "price_monthly",
    "buysell_daily",
    "buysell_weekly",
    "buysell_monthly",
    "algo_trades",
    "algo_positions",
    "algo_audit_log",
]

SYMBOL_MAPPING = {
    'BRK.B': 'BRK-B',
    'LEN.B': 'LEN-B',
    'WSO.B': 'WSO-B',
}


def migrate(dry_run=False):
    """Migrate symbols from dots to hyphens."""
    logger.info("=" * 70)
    logger.info("SYMBOL FORMAT MIGRATION - Dots to Hyphens")
    logger.info("=" * 70)
    logger.info(f"\nDry-run: {dry_run}\n")

    try:
        conn = psycopg2.connect(**_get_db_config())
        cur = conn.cursor()

        total_updated = 0

        for old_symbol, new_symbol in SYMBOL_MAPPING.items():
            logger.info(f"\nMigrating {old_symbol} -> {new_symbol}")
            logger.info("-" * 70)

            for table in TABLES_WITH_SYMBOLS:
                # Check if table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = %s
                    )
                """, (table,))

                if not cur.fetchone()[0]:
                    logger.info(f"  SKIP: {table} (table does not exist)")
                    continue

                # Count rows to update
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE symbol = %s", (old_symbol,))
                count = cur.fetchone()[0]

                if count == 0:
                    logger.info(f"  OK: {table} (no rows)")
                    continue

                logger.info(f"  Updating {table}: {count} rows")

                if not dry_run:
                    # Update the symbol
                    cur.execute(f"UPDATE {table} SET symbol = %s WHERE symbol = %s",
                               (new_symbol, old_symbol))
                    affected = cur.rowcount
                    total_updated += affected

            logger.info(f"  Total for {old_symbol}: {count} rows")

        if dry_run:
            conn.rollback()
            logger.info("\n" + "=" * 70)
            logger.info("DRY-RUN COMPLETE - No changes made")
            logger.info("=" * 70)
        else:
            conn.commit()
            logger.info("\n" + "=" * 70)
            logger.info(f"MIGRATION COMPLETE - {total_updated} rows updated")
            logger.info("=" * 70)

        # Verify migration
        logger.info("\nVerifying migration...")
        cur.execute("SELECT symbol, COUNT(*) FROM stock_symbols WHERE symbol IN (%s, %s, %s) GROUP BY symbol",
                   ('BRK-B', 'LEN-B', 'WSO-B'))

        results = cur.fetchall()
        if results:
            logger.info("\nSymbols after migration:")
            for symbol, count in results:
                logger.info(f"  {symbol}: {count} entries")
        else:
            logger.info("\nNo migrated symbols found in stock_symbols")

        conn.close()

    except Exception as e:
        logger.info(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        logger.info("\n[DRY-RUN] Running in DRY-RUN mode - no changes will be made\n")

    success = migrate(dry_run=dry_run)

    if not dry_run and success:
        logger.info("\n[OK] Migration successful!")
        logger.info("\nNext steps:")
        logger.info("  1. Run: python3 backfill_stage2_data.py")
        logger.info("  2. Verify with: python3 check_stage2.py")

    sys.exit(0 if success else 1)

