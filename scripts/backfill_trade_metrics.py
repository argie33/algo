#!/usr/bin/env python3
"""Backfill trade metrics for existing closed trades.

Calculates exit_r_multiple, trade_duration_days, mfe_pct, mae_pct for all
closed trades that don't yet have these metrics. Safe to run multiple times.

Usage:
    python scripts/backfill_trade_metrics.py              # Show count, ask for confirmation
    python scripts/backfill_trade_metrics.py --force      # Skip confirmation
    python scripts/backfill_trade_metrics.py --dry-run    # Show what would be updated
"""

import argparse
import logging
import sys
from typing import Any

from utils.db import DatabaseContext
from utils.trade_metrics import backfill_all_trade_metrics

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def count_trades_needing_metrics() -> int:
    """Count closed trades without exit_r_multiple calculated."""
    try:
        with DatabaseContext("read") as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM algo_trades
                WHERE status = 'closed'
                  AND exit_price IS NOT NULL
                  AND exit_r_multiple IS NULL
            """
            )
            row = cursor.fetchone()
            return int(row["count"]) if row else 0
    except Exception as e:
        logger.error(f"Failed to count trades: {e}")
        return -1


def backfill_metrics(dry_run: bool = False, force: bool = False) -> bool:
    """Backfill trade metrics for all closed trades without metrics.

    Args:
        dry_run: If True, show what would be updated without making changes
        force: If True, skip confirmation prompt

    Returns:
        True if successful, False otherwise
    """
    try:
        count = count_trades_needing_metrics()
        if count < 0:
            logger.error("Failed to determine trade count. Aborting.")
            return False

        if count == 0:
            logger.info("✅ No trades need metric calculation. All done!")
            return True

        logger.info(f"Found {count} closed trade(s) needing metric calculation")

        if dry_run:
            logger.info("[DRY RUN] Would update metrics for these trades (no changes made)")
            return True

        if not force:
            response = input(f"Backfill metrics for {count} trade(s)? (yes/no): ").strip().lower()
            if response not in ("yes", "y"):
                logger.info("Cancelled by user")
                return False

        logger.info("Starting backfill...")
        with DatabaseContext("write") as cursor:
            result = backfill_all_trade_metrics(cursor)

        if "total_updated" in result:
            updated = result["total_updated"]
            logger.info(f"✅ Successfully updated metrics for {updated} trade(s)")

            # Show sample of updated trades
            if updated > 0 and "results" in result:
                results = result["results"]
                for i, trade_result in enumerate(results[:3]):
                    if "error" not in trade_result:
                        logger.info(
                            f"  Trade {i+1}: {trade_result.get('trade_id')} "
                            f"R={trade_result.get('exit_r_multiple'):.2f}R, "
                            f"Duration={trade_result.get('trade_duration_days')}d"
                        )
                if len(results) > 3:
                    logger.info(f"  ... and {len(results) - 3} more trades")

            return True
        else:
            logger.error(f"Backfill failed: {result.get('message', 'unknown error')}")
            return False

    except Exception as e:
        logger.error(f"Backfill failed with exception: {e}")
        return False


def main() -> int:
    """Parse arguments and run backfill."""
    parser = argparse.ArgumentParser(
        description="Backfill trade metrics for existing closed trades",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/backfill_trade_metrics.py              # Show count, ask for confirmation
  python scripts/backfill_trade_metrics.py --force      # Skip confirmation prompt
  python scripts/backfill_trade_metrics.py --dry-run    # Show what would be updated
        """,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt (automatically proceed)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )

    args = parser.parse_args()

    success = backfill_metrics(dry_run=args.dry_run, force=args.force)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
