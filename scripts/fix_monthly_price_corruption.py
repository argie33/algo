#!/usr/bin/env python3
"""Fix corrupted monthly price tables that contain mid-month dates.

ISSUE: price_monthly and etf_price_monthly were corrupted with daily-like rows
(dates like 2026-07-10, 2026-07-13) instead of month-start dates (2026-07-01).
This prevented derivation from updating to current month because MAX(date) was
a mid-month date, causing the derivation healing window to be too narrow.

ROOT CAUSE: Unknown - likely a one-time loader bug or manual insert error.

FIX: Delete all rows that don't have month-start dates (1st of month).
Then re-derive to populate current month correctly.

VERIFIED: Tested on local DB, corrupt rows identified via:
- price_monthly: has dates 2026-07-02 to 2026-07-13 (should only have 2026-07-01)
- etf_price_monthly: has 2026-07-10 (should have 2026-07-01)
"""

import logging
from datetime import datetime, date, timedelta, timezone
from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def identify_month_start_dates_for_table(cur, table_name: str) -> list[date]:
    """Get all unique month-start dates in a monthly table.

    A valid monthly table should only have dates like 2026-07-01, 2026-06-01, etc.
    Returns list of dates that ARE month starts.
    """
    cur.execute(f"""
        SELECT DISTINCT date FROM {table_name}
        WHERE EXTRACT(day FROM date) = 1
        ORDER BY date DESC
    """)
    return [row[0] for row in cur.fetchall()]


def identify_corrupt_dates(cur, table_name: str) -> list[date]:
    """Identify non-month-start dates in a monthly table (corruption).

    Returns list of dates that are NOT month starts (i.e., should be deleted).
    """
    cur.execute(f"""
        SELECT DISTINCT date FROM {table_name}
        WHERE EXTRACT(day FROM date) != 1
        ORDER BY date DESC
    """)
    return [row[0] for row in cur.fetchall()]


def count_rows_by_corruption_status(cur, table_name: str) -> dict:
    """Count rows to understand corruption scope."""
    cur.execute(f"""
        SELECT
            CASE
                WHEN EXTRACT(day FROM date) = 1 THEN 'valid_month_start'
                ELSE 'corrupt_mid_month'
            END as status,
            COUNT(*) as row_count,
            COUNT(DISTINCT symbol) as symbol_count
        FROM {table_name}
        GROUP BY status
    """)
    result = {}
    for status, row_count, symbol_count in cur.fetchall():
        result[status] = {"rows": row_count, "symbols": symbol_count}
    return result


def fix_table(table_name: str, execute: bool = False):
    """Identify and optionally delete corrupt rows from a monthly table."""
    logger.info(f"\n{'='*70}")
    logger.info(f"Analyzing {table_name}")
    logger.info(f"{'='*70}")

    with DatabaseContext("write") as cur:
        # Check current state
        status = count_rows_by_corruption_status(cur, table_name)
        logger.info(f"Current state:")
        for status_type, counts in status.items():
            logger.info(
                f"  {status_type:20}: {counts['rows']:7} rows, "
                f"{counts['symbols']:5} symbols"
            )

        # Identify corrupt dates
        corrupt_dates = identify_corrupt_dates(cur, table_name)
        if not corrupt_dates:
            logger.info(f"✓ {table_name} is clean (no corrupt dates found)")
            return True

        logger.warning(f"✗ Found {len(corrupt_dates)} corrupt non-month-start dates:")
        for d in corrupt_dates[:10]:  # Show first 10
            logger.warning(f"    {d}")
        if len(corrupt_dates) > 10:
            logger.warning(f"    ... and {len(corrupt_dates) - 10} more")

        # Show what we'd delete
        cur.execute(f"""
            SELECT date, COUNT(*) as rows, COUNT(DISTINCT symbol) as symbols
            FROM {table_name}
            WHERE EXTRACT(day FROM date) != 1
            GROUP BY date
            ORDER BY date DESC
        """)
        logger.info(f"\nRows to be deleted:")
        logger.info(f"  date | row_count | symbol_count")
        logger.info(f"  " + "-" * 40)
        total_delete_rows = 0
        for row_date, row_count, symbol_count in cur.fetchall():
            logger.info(f"  {row_date} | {row_count:9} | {symbol_count:12}")
            total_delete_rows += row_count

        if not execute:
            logger.info(f"\nDRY RUN: Would delete {total_delete_rows} rows")
            logger.info(f"Re-run with --execute to apply fix")
            return False

        # Execute deletion
        logger.info(f"\n{'='*70}")
        logger.info(f"EXECUTING FIX: Deleting {total_delete_rows} corrupt rows")
        logger.info(f"{'='*70}")

        cur.execute(f"""
            DELETE FROM {table_name}
            WHERE EXTRACT(day FROM date) != 1
        """)
        deleted_count = cur.rowcount
        logger.info(f"✓ Deleted {deleted_count} corrupt rows")

        # Verify
        status_after = count_rows_by_corruption_status(cur, table_name)
        logger.info(f"\nAfter fix:")
        for status_type, counts in status_after.items():
            logger.info(
                f"  {status_type:20}: {counts['rows']:7} rows, "
                f"{counts['symbols']:5} symbols"
            )

        # Check MAX date
        cur.execute(f"SELECT MAX(date) FROM {table_name}")
        max_date = cur.fetchone()[0]
        logger.info(f"\nMAX(date) after fix: {max_date}")
        logger.info(f"(Should be month-start: day=1)")

        return True


def main():
    import sys
    execute = "--execute" in sys.argv

    if not execute:
        logger.warning("DRY RUN MODE - no changes will be made")
        logger.warning("Re-run with --execute flag to apply fixes")
        logger.warning("")

    # Fix both tables
    tables = ["price_monthly", "etf_price_monthly"]
    all_clean = True

    for table in tables:
        try:
            is_clean = fix_table(table, execute=execute)
            if not is_clean:
                all_clean = False
        except Exception as e:
            logger.error(f"Error processing {table}: {e}", exc_info=True)
            return 1

    # If we made changes, re-derive to repopulate current month
    if execute and not all_clean:
        logger.info(f"\n{'='*70}")
        logger.info("Re-deriving monthly prices to populate current month")
        logger.info(f"{'='*70}")
        try:
            from loaders.load_prices import derive_aggregate_prices
            for asset_class in ["stock", "etf"]:
                logger.info(f"\nRe-deriving {asset_class} monthly prices...")
                derive_aggregate_prices(asset_class)
                logger.info(f"✓ {asset_class} monthly prices re-derived")
        except Exception as e:
            logger.error(f"Error re-deriving: {e}", exc_info=True)
            return 1

    logger.info(f"\n{'='*70}")
    logger.info("Fix complete")
    logger.info(f"{'='*70}\n")
    return 0


if __name__ == "__main__":
    exit(main())
