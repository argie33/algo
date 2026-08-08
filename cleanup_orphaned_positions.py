#!/usr/bin/env python3
"""Clean up orphaned positions from database.

Orphaned positions are:
1. Duplicate positions for the same symbol created on the same day
2. Positions with empty trade_ids_arr
3. Positions that don't have corresponding trades

This script safely removes duplicates by keeping only the position with trades.
"""

import logging
from decimal import Decimal
from utils.db import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_orphaned_positions():
    """Rebuild empty trade_ids_arr in orphaned positions."""

    try:
        with DatabaseContext("write") as cur:
            # GOAL: Fix data consistency, not delete historical data
            # Duplicate closed positions are harmless - only fix data integrity issues

            # Step 1: Find positions with empty trade_ids_arr but actual trades
            cur.execute("""
                SELECT position_id, symbol, status
                FROM algo_positions
                WHERE (trade_ids_arr IS NULL OR trade_ids_arr = ARRAY[]::text[])
                ORDER BY symbol, created_at DESC
            """)

            empty_positions = cur.fetchall()
            logger.info(f"Found {len(empty_positions)} positions with empty/NULL trade_ids_arr")

            fixed_count = 0
            for pos_id, symbol, status in empty_positions:
                # Check if this position has any trades
                cur.execute("""
                    SELECT ARRAY_AGG(trade_id)
                    FROM algo_trades
                    WHERE position_id = %s
                """, (pos_id,))

                result = cur.fetchone()
                trade_ids = result[0] if result and result[0] else []

                if trade_ids:
                    # Has trades - rebuild trade_ids_arr
                    logger.info(f"Rebuilding {symbol} {pos_id[:8]}... ({len(trade_ids)} trades)")
                    cur.execute("""
                        UPDATE algo_positions
                        SET trade_ids_arr = %s,
                            trade_ids = %s
                        WHERE position_id = %s
                    """, (trade_ids, ','.join(trade_ids), pos_id))
                    fixed_count += 1
                    logger.info(f"✓ Rebuilt trade_ids_arr for {symbol} {pos_id[:8]}...")
                else:
                    # No trades - log as orphaned but don't delete (preserve history)
                    logger.warning(f"Position {symbol} {pos_id[:8]}... has no trades (orphaned, but not deleting)")

        logger.info(f"Cleanup complete. Fixed {fixed_count} positions with empty trade_ids_arr.")
        return fixed_count

    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    fixed = cleanup_orphaned_positions()
    print(f"\nSuccessfully fixed {fixed} positions with empty trade_ids_arr")
