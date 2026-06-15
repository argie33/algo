"""Add user isolation (cognito_sub) to portfolio and trading tables.

Enables per-user portfolio isolation so each authenticated user only sees/trades their own account.

Schema changes:
- Add cognito_sub column to: algo_portfolio_snapshots, algo_trade_adds (columns already added by migration 011)
- Backfill admin's user ID for existing data
- Add unique constraints on (cognito_sub, symbol, date) where applicable
"""

from migrations.migration_helper import DatabaseContext

DESCRIPTION = "Add user isolation to portfolio snapshots and trade adds"

def up():
    """Add user isolation columns to remaining trading tables."""
    with DatabaseContext("write") as cur:
        # Note: cognito_sub was already added to algo_positions and algo_trades by migration 011
        # This migration adds it to algo_portfolio_snapshots and algo_trade_adds

        # 1. Add cognito_sub column to algo_portfolio_snapshots
        cur.execute("""
            ALTER TABLE algo_portfolio_snapshots
            ADD COLUMN IF NOT EXISTS cognito_sub VARCHAR(255)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_portfolio_snapshots_user_date
            ON algo_portfolio_snapshots(cognito_sub, snapshot_date)
        """)

        # 2. Add cognito_sub column to algo_trade_adds
        cur.execute("""
            ALTER TABLE algo_trade_adds
            ADD COLUMN IF NOT EXISTS cognito_sub VARCHAR(255)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_trade_adds_user_date
            ON algo_trade_adds(cognito_sub, add_date)
        """)

        # 3. Backfill admin user's cognito_sub for existing data
        admin_cognito_sub = "admin-user"

        cur.execute(
            """
            UPDATE algo_portfolio_snapshots
            SET cognito_sub = %s
            WHERE cognito_sub IS NULL
        """,
            (admin_cognito_sub,),
        )

        cur.execute(
            """
            UPDATE algo_trade_adds
            SET cognito_sub = %s
            WHERE cognito_sub IS NULL
        """,
            (admin_cognito_sub,),
        )

def down():
    """Remove user isolation columns."""
    with DatabaseContext("write") as cur:
        # Drop indexes
        cur.execute("DROP INDEX IF EXISTS idx_algo_trade_adds_user_date")
        cur.execute("DROP INDEX IF EXISTS idx_algo_portfolio_snapshots_user_date")

        # Drop columns
        cur.execute("ALTER TABLE algo_trade_adds DROP COLUMN IF EXISTS cognito_sub")
        cur.execute(
            "ALTER TABLE algo_portfolio_snapshots DROP COLUMN IF EXISTS cognito_sub"
        )
