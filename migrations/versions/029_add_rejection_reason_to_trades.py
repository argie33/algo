#!/usr/bin/env python3
"""Add rejection_reason field to algo_trades to capture Alpaca API errors."""

from migrations.migration_helper import DatabaseContext

DESCRIPTION = "Add rejection_reason column to algo_trades"

def up():
    with DatabaseContext("write") as cur:
        cur.execute("""
            ALTER TABLE algo_trades
            ADD COLUMN IF NOT EXISTS rejection_reason TEXT
        """)
        cur.execute("""
            COMMENT ON COLUMN algo_trades.rejection_reason IS 'Error message from Alpaca API when order is rejected'
        """)

def down():
    with DatabaseContext("write") as cur:
        cur.execute("""
            ALTER TABLE algo_trades
            DROP COLUMN IF EXISTS rejection_reason
        """)
