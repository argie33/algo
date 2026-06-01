#!/usr/bin/env python3
"""
Migration 004: Add idempotency_key column to algo_trades table.

This column is required to prevent duplicate trade execution. Previously added
at runtime with ALTER TABLE inside a transaction, which caused AccessExclusiveLock
blocking all reads/writes during trade execution. Moving to a one-time migration.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.database_context import DatabaseContext

DESCRIPTION = "Add idempotency_key column to algo_trades table"


def up():
    with DatabaseContext('write') as cur:
        cur.execute("""
            ALTER TABLE algo_trades
                ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(64)
        """)

        # Create index for idempotency key lookups
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_trades_idempotency_key
            ON algo_trades(idempotency_key)
        """)


def down():
    with DatabaseContext('write') as cur:
        cur.execute("DROP INDEX IF EXISTS idx_algo_trades_idempotency_key")
        cur.execute("""
            ALTER TABLE algo_trades
                DROP COLUMN IF EXISTS idempotency_key
        """)
