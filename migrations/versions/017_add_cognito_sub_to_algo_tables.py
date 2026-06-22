#!/usr/bin/env python3
"""
Migration 011: Add cognito_sub column to algo_trades and algo_positions tables.

These columns enable user isolation and row-level access control, allowing the API
to scope trade history and position data to authenticated users.
"""

from utils.db.context import DatabaseContext


DESCRIPTION = "Add cognito_sub column to algo_trades and algo_positions for user isolation"


def up():
    with DatabaseContext("write") as cur:
        # Add cognito_sub to algo_trades (nullable for backward compatibility)
        cur.execute("""
            ALTER TABLE algo_trades
            ADD COLUMN IF NOT EXISTS cognito_sub VARCHAR(255)
        """)

        # Create index for user-specific trade queries
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_trades_cognito_sub
            ON algo_trades(cognito_sub) WHERE cognito_sub IS NOT NULL
        """)

        # Add cognito_sub to algo_positions (nullable for backward compatibility)
        cur.execute("""
            ALTER TABLE algo_positions
            ADD COLUMN IF NOT EXISTS cognito_sub VARCHAR(255)
        """)

        # Create index for user-specific position queries
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_positions_cognito_sub
            ON algo_positions(cognito_sub) WHERE cognito_sub IS NOT NULL
        """)


def down():
    with DatabaseContext("write") as cur:
        # Drop indexes first
        cur.execute("""
            DROP INDEX IF EXISTS idx_algo_positions_cognito_sub
        """)

        cur.execute("""
            DROP INDEX IF EXISTS idx_algo_trades_cognito_sub
        """)

        # Drop columns
        cur.execute("""
            ALTER TABLE algo_trades
            DROP COLUMN IF EXISTS cognito_sub
        """)

        cur.execute("""
            ALTER TABLE algo_positions
            DROP COLUMN IF EXISTS cognito_sub
        """)
