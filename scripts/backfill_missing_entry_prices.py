#!/usr/bin/env python3
"""Backfill missing or zero entry prices from trade history.

This script fixes positions created before entry_price was consistently populated.
It updates NULL or 0 entry_prices from the first fill price in the corresponding trade record.

CRITICAL: This script should only be run once to backfill existing data.
After the main code fixes, all new positions will have proper entry prices.
"""

import logging
import sys
from decimal import Decimal

from utils.db import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backfill_entry_prices() -> dict[str, int]:
    """Backfill missing entry prices from trade history.

    Returns:
        dict with counts of positions updated, trades with missing entry prices, etc.
    """
    result = {
        "positions_updated": 0,
        "positions_with_null_entry": 0,
        "positions_with_zero_entry": 0,
        "trades_missing_entry_price": 0,
        "errors": [],
    }

    try:
        # First, identify positions with missing/zero entry prices
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT symbol, entry_price, status
                FROM algo_positions
                WHERE status IN ('open', 'paper_open', 'closed')
                  AND (entry_price IS NULL OR entry_price = 0)
                ORDER BY symbol
            """)
            problem_positions = cur.fetchall()

        logger.info(f"Found {len(problem_positions)} positions with missing/zero entry prices")

        if not problem_positions:
            logger.info("No positions need backfill - all have valid entry prices")
            return result

        result["positions_with_null_entry"] = len(problem_positions)

        # For each problem position, find the first trade and use its entry price
        positions_to_update = {}
        with DatabaseContext("read") as cur:
            for symbol, entry_price, status in problem_positions:
                # Get the first (earliest) entry from trades for this symbol
                cur.execute("""
                    SELECT entry_price
                    FROM algo_trades
                    WHERE symbol = %s
                      AND entry_date IS NOT NULL
                      AND entry_price IS NOT NULL
                      AND entry_price > 0
                    ORDER BY entry_date ASC LIMIT 1
                """, (symbol,))
                trade_row = cur.fetchone()

                if trade_row and trade_row[0]:
                    trade_entry_price = float(trade_row[0])
                    if trade_entry_price > 0:
                        positions_to_update[symbol] = trade_entry_price
                        logger.info(f"  {symbol}: will update from trade entry_price ${trade_entry_price:.2f}")
                    else:
                        result["errors"].append(f"{symbol}: trade entry_price is {trade_entry_price}")
                        logger.warning(f"  {symbol}: trade entry_price invalid ({trade_entry_price})")
                else:
                    result["trades_missing_entry_price"] += 1
                    result["errors"].append(f"{symbol}: no valid trade entry_price found")
                    logger.error(f"  {symbol}: NO VALID TRADE ENTRY PRICE - cannot backfill")

        # Update positions with the recovered entry prices
        if positions_to_update:
            with DatabaseContext("write") as cur:
                for symbol, entry_price in positions_to_update.items():
                    try:
                        cur.execute("""
                            UPDATE algo_positions
                            SET entry_price = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE symbol = %s
                        """, (entry_price, symbol))
                        result["positions_updated"] += 1
                        logger.info(f"✓ Updated {symbol}: entry_price = ${entry_price:.2f}")
                    except Exception as e:
                        result["errors"].append(f"{symbol}: failed to update - {e}")
                        logger.error(f"✗ Failed to update {symbol}: {e}")

        logger.info("\n" + "=" * 70)
        logger.info("BACKFILL SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Positions updated: {result['positions_updated']}")
        logger.info(f"Positions with NULL entry_price: {result['positions_with_null_entry']}")
        logger.info(f"Trades missing entry_price: {result['trades_missing_entry_price']}")
        if result["errors"]:
            logger.info(f"\nErrors encountered ({len(result['errors'])}):")
            for err in result["errors"][:10]:  # Show first 10
                logger.info(f"  - {err}")
            if len(result["errors"]) > 10:
                logger.info(f"  ... and {len(result['errors']) - 10} more")

        # Verify fixes
        logger.info("\n" + "=" * 70)
        logger.info("VERIFICATION")
        logger.info("=" * 70)
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM algo_positions
                WHERE status IN ('open', 'paper_open', 'closed')
                  AND (entry_price IS NULL OR entry_price = 0)
            """)
            remaining_bad = cur.fetchone()[0]
            logger.info(f"Positions still with invalid entry_price: {remaining_bad}")

            if remaining_bad > 0:
                cur.execute("""
                    SELECT symbol, entry_price, status
                    FROM algo_positions
                    WHERE status IN ('open', 'paper_open', 'closed')
                      AND (entry_price IS NULL OR entry_price = 0)
                    LIMIT 5
                """)
                bad_positions = cur.fetchall()
                logger.warning("Remaining positions with invalid entry_price:")
                for sym, price, status in bad_positions:
                    logger.warning(f"  {sym}: entry_price={price}, status={status}")

        return result

    except Exception as e:
        logger.critical(f"Backfill failed: {e}", exc_info=True)
        result["errors"].append(f"CRITICAL: {e}")
        raise


if __name__ == "__main__":
    logger.info("Starting backfill of missing entry prices...")
    result = backfill_entry_prices()

    # Exit with error if critical issues remain
    if result["trades_missing_entry_price"] > 0:
        logger.error(
            f"\nWARNING: {result['trades_missing_entry_price']} positions could not be backfilled "
            f"(no valid trade entry_price). These positions may need manual review."
        )
        sys.exit(1)

    logger.info("\n✓ Backfill complete!")
    sys.exit(0)
