#!/usr/bin/env python3
"""Clean up aged loader_watermarks records to prevent table bloat and insert timeouts.

SESSION 109: Fixes the weekly Monday brittleness caused by:
1. loader_watermarks table growing to 205K+ rows
2. ON CONFLICT inserts timing out on bloated index
3. Loaders appearing to complete but watermark update fails
4. Cascades to "stale RUNNING" → auto-fail → retry cycle

This job runs daily (scheduled via cron/EventBridge) to keep table healthy.
Retention: Keep 14 days of history (covers all production replay windows).

Usage:
    python scripts/cleanup_loader_watermarks.py [--retention-days 14]
    python scripts/cleanup_loader_watermarks.py --dry-run          # See what would delete
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from typing import Any

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def cleanup_old_watermarks(retention_days: int = 14, dry_run: bool = False, batch_size: int = 5000) -> dict[str, Any]:
    """Delete watermark records older than retention_days.

    Args:
        retention_days: Keep records from this many days back (default 14)
        dry_run: If True, only report what would be deleted
        batch_size: Delete in batches to avoid timeout on huge tables

    Returns:
        Dict with cleanup stats
    """
    stats = {"total_deleted": 0, "batches": 0, "errors": 0}
    cutoff_date = datetime.now(EASTERN_TZ) - timedelta(days=retention_days)

    logger.info(
        f"[CLEANUP] Starting cleanup of loader_watermarks (retention: {retention_days} days, cutoff: {cutoff_date})"
    )

    # First, check what we're dealing with
    with DatabaseContext("read") as cur:
        cur.execute("SELECT COUNT(*) FROM loader_watermarks")
        before_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM loader_watermarks WHERE updated_at < %s", (cutoff_date,))
        delete_count = cur.fetchone()[0]

    logger.info(f"[CLEANUP] Table has {before_count:,} rows, will delete {delete_count:,} (>{retention_days}d old)")

    if dry_run:
        logger.info("[DRY_RUN] No changes made")
        return {"total_deleted": delete_count, "batches": 0, "dry_run": True}

    if delete_count == 0:
        logger.info("[CLEANUP] No old records to delete")
        return stats

    # Delete in batches to avoid timeout
    for batch_num in range(1000):  # Safety limit: max 1000 batches = 5M rows
        try:
            with DatabaseContext("write") as cur:
                # Use subquery to select batch, then delete by values
                # This is safer than trying to delete large ranges at once
                cur.execute(
                    """
                    DELETE FROM loader_watermarks
                    WHERE (loader, symbol, granularity, updated_at) IN (
                        SELECT loader, symbol, granularity, updated_at
                        FROM loader_watermarks
                        WHERE updated_at < %s
                        LIMIT %s
                    )
                    """,
                    (cutoff_date, batch_size),
                )
                deleted_this_batch = cur.rowcount

                if deleted_this_batch == 0:
                    logger.info(f"[CLEANUP] Completed after {batch_num} batches")
                    break

                stats["total_deleted"] += deleted_this_batch
                stats["batches"] += 1

                pct = (stats["total_deleted"] / delete_count) * 100 if delete_count > 0 else 0
                logger.info(
                    f"[CLEANUP] Batch {batch_num + 1}: -  {deleted_this_batch:,} rows "
                    f"({stats['total_deleted']:,}/{delete_count:,}, {pct:.1f}%)"
                )

                # Brief pause between batches to avoid overwhelming DB
                if deleted_this_batch == batch_size:  # More to delete
                    time.sleep(0.1)

        except Exception as e:
            logger.error(f"[CLEANUP] Batch {batch_num + 1} failed: {e}")
            stats["errors"] += 1

            # Stop if too many errors
            if stats["errors"] >= 3:
                logger.error("[CLEANUP] Too many errors, aborting cleanup")
                break

            # Brief backoff before retry
            time.sleep(1)

    # Check final state
    with DatabaseContext("read") as cur:
        cur.execute("SELECT COUNT(*) FROM loader_watermarks")
        after_count = cur.fetchone()[0]

    logger.info(f"[CLEANUP] Final: {after_count:,} rows (reduction: {before_count - after_count:,} rows)")

    return stats


def analyze_watermarks(retention_days: int = 14) -> dict[str, Any]:
    """Analyze watermark table health."""
    cutoff_date = datetime.now(EASTERN_TZ) - timedelta(days=retention_days)

    with DatabaseContext("read") as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN updated_at < %s THEN 1 END) as older_than_retention,
                COUNT(DISTINCT loader) as unique_loaders,
                COUNT(DISTINCT symbol) as unique_symbols,
                MIN(updated_at) as oldest_record,
                MAX(updated_at) as newest_record
            FROM loader_watermarks
            """,
            (cutoff_date,),
        )

        row = cur.fetchone()
        if not row:
            return {}

        total, old_count, loaders, symbols, oldest, newest = row

        return {
            "total_rows": total,
            "rows_older_than_retention": old_count,
            "unique_loaders": loaders,
            "unique_symbols": symbols,
            "oldest_record": oldest,
            "newest_record": newest,
            "pct_old": (old_count / total * 100) if total > 0 else 0,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retention-days", type=int, default=14, help="Days of history to keep (default 14)")
    parser.add_argument("--dry-run", action="store_true", help="Report what would delete, make no changes")
    parser.add_argument("--no-analyze", action="store_true", help="Skip analysis step")
    args = parser.parse_args()

    # Analyze before
    if not args.no_analyze:
        logger.info("[ANALYSIS] Before cleanup:")
        analysis = analyze_watermarks(args.retention_days)
        for key, value in analysis.items():
            if isinstance(value, float):
                logger.info(f"  {key}: {value:.1f}")
            else:
                logger.info(f"  {key}: {value}")

    # Run cleanup
    stats = cleanup_old_watermarks(args.retention_days, args.dry_run, batch_size=5000)

    # Analyze after
    if not args.dry_run and not args.no_analyze:
        logger.info("[ANALYSIS] After cleanup:")
        analysis = analyze_watermarks(args.retention_days)
        for key, value in analysis.items():
            if isinstance(value, float):
                logger.info(f"  {key}: {value:.1f}")
            else:
                logger.info(f"  {key}: {value}")

    logger.info(f"[CLEANUP] Deleted {stats['total_deleted']:,} rows in {stats['batches']} batches")

    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
