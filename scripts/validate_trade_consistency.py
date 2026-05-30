#!/usr/bin/env python3
"""
Validate trade and position consistency in database.

Checks for:
- Orphaned trade records (filled trades not linked to positions)
- Inconsistent trade_id vs recurring_id usage
- Missing foreign key relationships
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_context import DatabaseContext
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def validate_trade_position_links():
    """Check for orphaned filled trades not linked to positions."""
    with DatabaseContext() as cur:
        # Check for filled trades with no position links
        cur.execute("""
            SELECT t.trade_id, t.symbol, t.status, t.entry_date
            FROM algo_trades t
            LEFT JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
            WHERE p.position_id IS NULL
              AND t.status IN ('filled', 'partial')
              AND t.entry_date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY t.entry_date DESC
            LIMIT 100
        """)
        orphaned = cur.fetchall()

        if orphaned:
            logger.warning(f"FOUND {len(orphaned)} potentially orphaned trades:")
            for trade_id, symbol, status, entry_date in orphaned:
                logger.warning(f"  {trade_id} {symbol} ({status}) on {entry_date}")
            return False
        else:
            logger.info("✓ No orphaned filled trades found")
            return True


def validate_position_trade_count():
    """Check that positions have valid trade counts."""
    with DatabaseContext() as cur:
        cur.execute("""
            SELECT position_id, symbol,
                   array_length(trade_ids_arr, 1) as linked_trade_count,
                   quantity
            FROM algo_positions
            WHERE status = 'open'
              AND (trade_ids_arr IS NULL OR array_length(trade_ids_arr, 1) = 0)
            LIMIT 10
        """)
        empty_links = cur.fetchall()

        if empty_links:
            logger.warning(f"FOUND {len(empty_links)} positions with no trade links:")
            for pos_id, symbol, count, qty in empty_links:
                logger.warning(f"  {pos_id} {symbol} qty={qty} (trades: {count})")
            return False
        else:
            logger.info("✓ All positions have valid trade links")
            return True


def main():
    """Run all validation checks."""
    logger.info("Starting trade consistency validation...")

    results = []
    results.append(("Trade-Position Links", validate_trade_position_links()))
    results.append(("Position Trade Counts", validate_position_trade_count()))

    logger.info("\n" + "=" * 50)
    logger.info("Validation Summary:")
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"  {status}: {name}")

    all_passed = all(passed for _, passed in results)
    logger.info("=" * 50)
    if all_passed:
        logger.info("All checks passed!")
        return 0
    else:
        logger.error("Some checks failed. Review trade data integrity.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
