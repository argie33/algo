#!/usr/bin/env python3
"""
Migration: Add 'active' column to stock_symbols table

This fixes an accuracy issue where loaders query for a non-existent 'active' column.
The column is needed to:
1. Support loader coverage calculations
2. Allow filtering active vs inactive symbols
3. Enable symbol universe management

Run: python3 scripts/migrate-add-active-column.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from utils.database_context import DatabaseContext

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def add_active_column():
    """Add 'active' column to stock_symbols if it doesn't exist."""
    try:
        with DatabaseContext('write') as cur:
            # Check if column already exists
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'stock_symbols' AND column_name = 'active'
            """)

            if cur.fetchone():
                logger.info("Column 'active' already exists in stock_symbols, skipping migration")
                return True

            logger.info("Adding 'active' column to stock_symbols table...")

            # Add the column with default value
            cur.execute("""
                ALTER TABLE stock_symbols
                ADD COLUMN active BOOLEAN DEFAULT TRUE
            """)
            logger.info("✓ Added column 'active' to stock_symbols")

            # Create index for faster queries
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_stock_symbols_active ON stock_symbols(active)
            """)
            logger.info("✓ Created index on 'active' column")

            # Verify the column exists
            cur.execute("""
                SELECT COUNT(*) FROM stock_symbols WHERE active = true
            """)
            count = cur.fetchone()[0]
            logger.info(f"✓ Migration successful: {count} symbols marked as active")

            return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def main():
    """Run the migration."""
    logger.info("="*70)
    logger.info("MIGRATION: Add 'active' column to stock_symbols")
    logger.info("="*70)

    success = add_active_column()

    logger.info("="*70)
    if success:
        logger.info("✓ Migration completed successfully")
        logger.info("\nThis fixes Issue #ACCURACY-001:")
        logger.info("- Loaders can now query: SELECT COUNT(*) FROM stock_symbols WHERE active = true")
        logger.info("- Coverage calculations will be accurate")
        logger.info("- Symbol universe can be managed via 'active' flag")
        return 0
    else:
        logger.error("✗ Migration failed - see errors above")
        return 1


if __name__ == '__main__':
    sys.exit(main())
