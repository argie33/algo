#!/usr/bin/env python3
"""
Migration 089: Fix position sizing configuration conflict

There is a geometric conflict in the position sizing configuration:
- max_positions = 12
- max_position_size_pct = 8%
- Total theoretical exposure = 96% (12 * 8%)
- But max_total_invested_pct = 95%

This violates the constraint: max_positions * max_position_size_pct <= max_total_invested_pct

Solution: Reduce max_position_size_pct to 7.9% to ensure 12 * 7.9% = 94.8% < 95%

This ensures position sizing respects the portfolio-wide exposure limit.
"""

from utils.db.context import DatabaseContext


DESCRIPTION = "Fix position sizing conflict (max_position_size_pct should be 7.9%)"


def up():
    """Adjust max_position_size_pct to resolve geometric conflict."""
    with DatabaseContext("write") as cur:
        cur.execute(
            """
            UPDATE algo_config
            SET value = '7.9', updated_by = 'migration-089'
            WHERE key = 'max_position_size_pct'
            """,
        )

    return True


def down():
    """Revert max_position_size_pct back to 8%."""
    with DatabaseContext("write") as cur:
        cur.execute(
            """
            UPDATE algo_config
            SET value = '8.0'
            WHERE key = 'max_position_size_pct' AND updated_by = 'migration-089'
            """,
        )

    return True
