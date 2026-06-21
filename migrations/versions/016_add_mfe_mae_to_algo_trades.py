#!/usr/bin/env python3
"""
Migration 010: Add mfe_pct and mae_pct columns to algo_trades table.

These columns track Maximum Favorable Excursion (MFE) and Maximum Adverse
Excursion (MAE) - the best and worst prices reached during a trade's lifetime.
They are computed by algo_daily_reconciliation.py and used by the API to
display trade analysis and performance metrics.
"""

from utils.db.context import DatabaseContext


DESCRIPTION = "Add mfe_pct and mae_pct columns to algo_trades table"


def up():
    with DatabaseContext("write") as cur:
        # Add mfe_pct column (Maximum Favorable Excursion percentage)
        cur.execute("""
            ALTER TABLE algo_trades
            ADD COLUMN IF NOT EXISTS mfe_pct DECIMAL(8, 4)
        """)

        # Add mae_pct column (Maximum Adverse Excursion percentage)
        cur.execute("""
            ALTER TABLE algo_trades
            ADD COLUMN IF NOT EXISTS mae_pct DECIMAL(8, 4)
        """)

        # Create index for queries filtering by these metrics
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_trades_mfe_mae
            ON algo_trades(mfe_pct, mae_pct) WHERE mfe_pct IS NOT NULL AND mae_pct IS NOT NULL
        """)


def down():
    with DatabaseContext("write") as cur:
        # Drop index first
        cur.execute("""
            DROP INDEX IF EXISTS idx_algo_trades_mfe_mae
        """)

        # Drop columns
        cur.execute("""
            ALTER TABLE algo_trades
            DROP COLUMN IF EXISTS mfe_pct,
            DROP COLUMN IF EXISTS mae_pct
        """)
