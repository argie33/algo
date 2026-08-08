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
    """Remove orphaned duplicate positions."""

    try:
        with DatabaseContext("write") as cur:
            # Find positions with empty trade_ids_arr
            cur.execute("""
                SELECT position_id, symbol, status, created_at
                FROM algo_positions
                WHERE trade_ids_arr IS NULL OR trade_ids_arr = ARRAY[]::text[]
                ORDER BY symbol, created_at DESC
            """)

            empty_trade_positions = cur.fetchall()
            logger.info(f"Found {len(empty_trade_positions)} positions with empty trade_ids_arr")

            if not empty_trade_positions:
                logger.info("No orphaned positions found. Database is clean.")
                return 0

            deleted_count = 0
            for pos_id, symbol, status, created_at in empty_trade_positions:
                # For each symbol with empty trade_ids, check if there's another position
                # with trades that we should keep
                cur.execute("""
                    SELECT position_id, trade_ids_arr
                    FROM algo_positions
                    WHERE symbol = %s
                    AND created_at::date = %s
                    AND (trade_ids_arr IS NOT NULL AND trade_ids_arr != ARRAY[]::text[])
                    LIMIT 1
                """, (symbol, created_at.date() if hasattr(created_at, 'date') else created_at))

                good_position = cur.fetchone()
                if good_position:
                    # There's a good position with trades, safe to delete the orphaned one
                    logger.info(f"Deleting orphaned position {pos_id} for {symbol} (has empty trade_ids_arr)")
                    # Use SQL to safely delete with foreign key handling
                    try:
                        # First, close all trades for this position
                        cur.execute("""
                            UPDATE algo_trades
                            SET status = 'canceled', exit_price = NULL, exit_date = NOW()
                            WHERE position_id = %s AND status != 'closed'
                        """, (pos_id,))

                        # Then delete the position
                        cur.execute("""
                            DELETE FROM algo_positions WHERE position_id = %s
                        """, (pos_id,))
                        deleted_count += 1
                        logger.info(f"✓ Deleted orphaned position {pos_id} for {symbol}")
                    except Exception as e:
                        logger.error(f"✗ Failed to delete {pos_id}: {e}")
                else:
                    # No good position found, this position is the only one
                    logger.warning(f"Position {pos_id} for {symbol} has empty trade_ids_arr but no alternate. Investigating...")
                    # Check if it has any trades at all
                    cur.execute("""
                        SELECT COUNT(*) FROM algo_trades WHERE position_id = %s
                    """, (pos_id,))
                    trade_count = cur.fetchone()[0]
                    if trade_count == 0:
                        logger.warning(f"Position {pos_id} has NO trades at all. Safe to delete.")
                        try:
                            cur.execute("""
                                DELETE FROM algo_positions WHERE position_id = %s
                            """, (pos_id,))
                            deleted_count += 1
                            logger.info(f"✓ Deleted position {pos_id} with no trades")
                        except Exception as e:
                            logger.error(f"✗ Failed to delete {pos_id}: {e}")
                    else:
                        logger.warning(f"Position {pos_id} has {trade_count} trades but empty trade_ids_arr. Fixing...")
                        # Try to rebuild trade_ids_arr
                        cur.execute("""
                            SELECT ARRAY_AGG(trade_id)
                            FROM algo_trades
                            WHERE position_id = %s AND status IN ('filled', 'open')
                        """, (pos_id,))
                        rebuilt_trades = cur.fetchone()[0]
                        if rebuilt_trades:
                            cur.execute("""
                                UPDATE algo_positions
                                SET trade_ids_arr = %s,
                                    trade_ids = %s
                                WHERE position_id = %s
                            """, (rebuilt_trades, ','.join(rebuilt_trades), pos_id))
                            logger.info(f"✓ Rebuilt trade_ids_arr for position {pos_id}")

        logger.info(f"Cleanup complete. Deleted {deleted_count} orphaned positions.")
        return deleted_count

    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    deleted = cleanup_orphaned_positions()
    print(f"\n✓ Successfully cleaned up {deleted} orphaned positions")
