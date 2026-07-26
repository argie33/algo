#!/usr/bin/env python3
"""Directly sync score fields from stock_scores to metrics tables.

This script bypasses OptimalLoader and uses direct SQL updates for efficiency
and simplicity. Syncs all 6 score types in one pass.
"""

import logging
import sys

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Map each metrics table to its score column
# These columns are populated from stock_scores table
SCORE_MAPPINGS = {
    "value_metrics": "value_score",
    "quality_metrics": "quality_score",
    # Note: growth/positioning/stability/momentum don't have score columns in DB yet (need migrations)
}


def sync_scores() -> int:
    """Sync all scores from stock_scores to metrics tables."""
    total_updated = 0

    with DatabaseContext("write") as cur:
        for table, score_col in SCORE_MAPPINGS.items():
            logger.info(f"\nSyncing {score_col} to {table}...")

            # Update the score column from stock_scores
            update_sql = f"""
                UPDATE {table} m
                SET {score_col} = s.{score_col},
                    updated_at = NOW()
                FROM stock_scores s
                WHERE m.symbol = s.symbol
            """

            cur.execute(update_sql)
            updated = cur.rowcount
            total_updated += updated

            logger.info(f"  Updated {updated} rows in {table}")

            # Log coverage
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {score_col} IS NOT NULL")
            populated = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            total = cur.fetchone()[0]
            pct = (populated / total * 100) if total > 0 else 0
            logger.info(f"  Coverage: {populated}/{total} ({pct:.1f}%)")

    logger.info(f"\nTotal rows updated across all tables: {total_updated}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(sync_scores())
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        sys.exit(1)
