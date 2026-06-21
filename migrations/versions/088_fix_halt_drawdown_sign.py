#!/usr/bin/env python3
"""
Migration 088: Fix halt_drawdown_pct sign error

The halt_drawdown_pct parameter was stored as positive 20.0 in the database
when it should be negative -20.0 (representing a 20% downside loss threshold).

This migration corrects the sign to match the expected semantics where:
- Negative value = downside loss threshold
- Positive value would incorrectly represent upside (not used for halt triggers)

This fix ensures the config validation warning is resolved.
"""

from utils.db.context import DatabaseContext


DESCRIPTION = "Fix halt_drawdown_pct sign error (should be negative)"


def up():
    """Convert halt_drawdown_pct from positive to negative if needed."""
    with DatabaseContext("write") as cur:
        # Check current value
        cur.execute("SELECT value FROM algo_config WHERE key = 'halt_drawdown_pct'")
        row = cur.fetchone()

        if row and row[0]:
            current = float(row[0])
            # If positive, negate it
            if current > 0:
                new_value = str(-current)
                cur.execute(
                    """
                    UPDATE algo_config
                    SET value = %s, updated_by = 'migration-088'
                    WHERE key = 'halt_drawdown_pct'
                    """,
                    (new_value,),
                )
                return True

    return True


def down():
    """Revert halt_drawdown_pct to previous state (negate if negative)."""
    with DatabaseContext("write") as cur:
        cur.execute("SELECT value FROM algo_config WHERE key = 'halt_drawdown_pct'")
        row = cur.fetchone()

        if row and row[0]:
            current = float(row[0])
            # If negative, make it positive (reverting the fix)
            if current < 0:
                new_value = str(-current)
                cur.execute(
                    """
                    UPDATE algo_config
                    SET value = %s
                    WHERE key = 'halt_drawdown_pct' AND updated_by = 'migration-088'
                    """,
                    (new_value,),
                )

    return True
