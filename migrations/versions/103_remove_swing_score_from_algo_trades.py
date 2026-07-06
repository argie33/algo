#!/usr/bin/env python3
"""
Migration 103: Remove unused swing_score columns from algo_trades

SWING SCORE MIGRATION CLEANUP:
The swing_trader_scores table was created for swing trading analysis, but:
- swing_score and swing_grade fields are NEVER populated during trade execution
- Phase 7 (signal generation) fetches these values but discards them
- TradeContext fields are always NULL at runtime
- algo_trades columns always store NULL values
- No downstream analysis or decision-making uses these columns

SAFE TO REMOVE: These columns have always been NULL since they were added.
This migration removes technical debt without affecting any live data.

This completes the migration to composite_score-only trading logic.
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Remove unused swing_score and swing_grade columns from algo_trades (always NULL)"


def up():
    """Remove swing_score columns from algo_trades."""
    with DatabaseContext("write") as cur:
        # Drop the columns - these have always been NULL, no data loss
        cur.execute("ALTER TABLE algo_trades DROP COLUMN IF EXISTS swing_score")
        cur.execute("ALTER TABLE algo_trades DROP COLUMN IF EXISTS swing_grade")
        cur.execute("ALTER TABLE algo_trades DROP COLUMN IF EXISTS swing_components")


def down():
    """Restore swing_score columns (rollback)."""
    with DatabaseContext("write") as cur:
        # Add columns back with NULL default for backward compatibility
        cur.execute(
            """
            ALTER TABLE algo_trades
            ADD COLUMN swing_score FLOAT DEFAULT NULL,
            ADD COLUMN swing_grade VARCHAR(10) DEFAULT NULL,
            ADD COLUMN swing_components JSONB DEFAULT NULL
            """
        )
