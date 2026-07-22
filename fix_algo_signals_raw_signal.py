#!/usr/bin/env python3
"""Backfill raw_signal column in algo_signals table.

The raw_signal column was not being populated when signals were inserted,
causing the health check to show 0 buy signals. This script backfills all
NULL raw_signal entries with 'BUY' (since this system only generates buy signals).

Run: python3 fix_algo_signals_raw_signal.py
"""

import logging
import sys

import psycopg2

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def main():
    """Backfill raw_signal column in algo_signals."""
    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext("write") as cur:
            # Check current state: count NULLs
            cur.execute(
                "SELECT COUNT(*) FROM algo_signals WHERE raw_signal IS NULL"
            )
            null_count = cur.fetchone()[0]
            logger.info(f"Found {null_count} signals with NULL raw_signal")

            if null_count > 0:
                # Backfill NULLs with 'BUY' (this system only generates buy signals)
                cur.execute(
                    "UPDATE algo_signals SET raw_signal = 'BUY' WHERE raw_signal IS NULL"
                )
                updated = cur.rowcount
                logger.info(f"Updated {updated} signals with raw_signal = 'BUY'")

                # Verify: count BUY signals
                cur.execute(
                    "SELECT COUNT(*) FROM algo_signals WHERE raw_signal = 'BUY'"
                )
                buy_count = cur.fetchone()[0]
                logger.info(f"Total BUY signals in algo_signals: {buy_count}")

                # Verify: check for any remaining NULLs
                cur.execute(
                    "SELECT COUNT(*) FROM algo_signals WHERE raw_signal IS NULL"
                )
                remaining_nulls = cur.fetchone()[0]
                logger.info(f"Remaining NULL raw_signal entries: {remaining_nulls}")

                if remaining_nulls == 0:
                    logger.info("✓ Backfill complete: all raw_signal entries are now 'BUY'")
                    return 0
                else:
                    logger.error(f"✗ Backfill incomplete: {remaining_nulls} NULLs remain")
                    return 1
            else:
                logger.info("No NULL raw_signal entries found - no backfill needed")
                return 0

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Database error: {e}", exc_info=True)
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
