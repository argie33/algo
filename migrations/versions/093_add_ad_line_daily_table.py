#!/usr/bin/env python3
"""
Migration 093: Add ad_line_daily table

Advance-Decline Line (A/D Line) is a critical market breadth indicator used in the
market exposure calculation (6 points out of 100). The table was missing from the schema,
causing market_exposure_daily loader failures and pipeline staleness.

The A/D line tracks market direction by comparing advancing vs declining stocks.
It's computed daily from trend_template_data and used to confirm or diverge from SPY price action.
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Add ad_line_daily table for market breadth tracking"


def up():
    with DatabaseContext("write") as cur:
        # Create table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ad_line_daily (
                date DATE PRIMARY KEY,
                advances INTEGER NOT NULL DEFAULT 0,
                declines INTEGER NOT NULL DEFAULT 0,
                direction VARCHAR(10) NOT NULL CHECK (direction IN ('up', 'down')),
                advance_decline_ratio NUMERIC(5, 4),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ad_line_date ON ad_line_daily(date DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ad_line_updated_at ON ad_line_daily(updated_at DESC)")

        # Grant permissions
        cur.execute("GRANT SELECT ON ad_line_daily TO stocks")


def down():
    """Drop ad_line_daily table."""
    with DatabaseContext("write") as cur:
        cur.execute("DROP TABLE IF EXISTS ad_line_daily CASCADE")
