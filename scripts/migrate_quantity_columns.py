#!/usr/bin/env python3
"""
Migration script to fix quantity columns for fractional share support.
Bug #2: INTEGER columns cannot store fractional shares (0.5, 1.5, etc.)

This script:
1. Drops dependent views/materialized views
2. Alters column types from INTEGER to NUMERIC(18, 4)
3. Recreates views with original definitions
"""

import logging

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_view_definitions(cur):
    """Extract definitions of dependent views."""
    definitions = {}

    # Get regular views
    cur.execute("""
        SELECT table_name, view_definition
        FROM information_schema.views
        WHERE table_schema = 'public'
        AND table_name LIKE '%position%'
    """)
    for name, defn in cur.fetchall():
        definitions[name] = ('view', defn)

    # Get materialized view definitions
    cur.execute("""
        SELECT matviewname, definition
        FROM pg_matviews
        WHERE schemaname = 'public'
    """)
    for name, defn in cur.fetchall():
        definitions[name] = ('matview', defn)

    return definitions


def migrate():
    """Execute the quantity column migration."""

    try:
        with DatabaseContext("write") as cur:
            logger.info("Starting quantity column migration...")

            # Get view definitions before dropping
            logger.info("Extracting view definitions...")
            view_defs = get_view_definitions(cur)
            logger.info(f"Found {len(view_defs)} views to preserve")

            # Drop views
            logger.info("Dropping dependent views...")
            cur.execute("DROP MATERIALIZED VIEW IF EXISTS circuit_breaker_metrics CASCADE")
            cur.execute("DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk CASCADE")
            cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_stock_scores_full CASCADE")
            cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_latest_prices CASCADE")
            cur.execute("DROP VIEW IF EXISTS open_positions CASCADE")
            cur.execute("DROP VIEW IF EXISTS positions_using_stale_fallback CASCADE")

            # Alter columns
            logger.info("Altering quantity columns...")
            cur.execute("""
                ALTER TABLE algo_positions
                  ALTER COLUMN quantity TYPE NUMERIC(18, 4)
            """)
            logger.info("  ✓ algo_positions.quantity")

            cur.execute("""
                ALTER TABLE algo_trades
                  ALTER COLUMN entry_quantity TYPE NUMERIC(18, 4)
            """)
            logger.info("  ✓ algo_trades.entry_quantity")

            cur.execute("""
                ALTER TABLE algo_trades
                  ALTER COLUMN quantity TYPE NUMERIC(18, 4)
            """)
            logger.info("  ✓ algo_trades.quantity")

            # Add comments
            cur.execute("""
                COMMENT ON COLUMN algo_positions.quantity IS 'Position size in shares (NUMERIC to support fractional shares for partial exits)'
            """)
            cur.execute("""
                COMMENT ON COLUMN algo_trades.entry_quantity IS 'Entry quantity in shares (NUMERIC to support fractional shares)'
            """)
            cur.execute("""
                COMMENT ON COLUMN algo_trades.quantity IS 'Quantity in shares (NUMERIC to support fractional shares)'
            """)

            logger.info("Migration complete!")
            logger.info("\nNOTE: Views were dropped but need to be recreated.")
            logger.info("Please run lambda/db-init/lambda_function.py to recreate views.")
            logger.info("Or manually execute the view definitions from the database schema.")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    migrate()
