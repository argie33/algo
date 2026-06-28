#!/usr/bin/env python3
"""
Migration 091: Fix NULL values in yfinance_ip_ban table

The initial migration (090) left ban_until as NULL, but the new fail-fast
validation requires all fields to be non-NULL when the row exists.
This migration backfills ban_until with CURRENT_TIMESTAMP.
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Fix NULL ban_until values in yfinance_ip_ban table"


def up():
    """Backfill NULL ban_until with CURRENT_TIMESTAMP."""
    with DatabaseContext("write") as cur:
        # Fix any NULL ban_until values
        cur.execute("""
            UPDATE yfinance_ip_ban
            SET ban_until = CURRENT_TIMESTAMP
            WHERE ban_until IS NULL;
        """)

        # Fix any NULL reason values (should be empty string, not NULL)
        cur.execute("""
            UPDATE yfinance_ip_ban
            SET reason = ''
            WHERE reason IS NULL;
        """)

    return True


def down():
    """No-op for down migration (data changes are not reversible)."""
    return True
