#!/usr/bin/env python3
"""Fix: Clear position_value for closed positions.

Root cause: Closed positions retained position_value in database, causing dashboard to display
them as active positions. This created a "mess" where 15 positions were shown but only 3-4 were
actually open.

Fix: Zero out position_value, unrealized_pnl, and unrealized_pnl_pct for all closed positions.
This ensures only open positions (position_value > 0) are displayed in dashboard.

Run: python scripts/fix_closed_positions_values.py
"""

from utils.db import DatabaseContext


def fix_closed_positions() -> int:
    """Clear values for closed positions.

    Returns:
        Number of positions fixed
    """
    with DatabaseContext("write") as cur:
        # Fix: Clear position_value for closed positions
        cur.execute("""
        UPDATE algo_positions
        SET position_value = 0, unrealized_pnl = 0, unrealized_pnl_pct = 0
        WHERE status = 'closed' AND position_value IS NOT NULL AND position_value > 0
        """)

        fixed_count = cur.rowcount

        # Verify the fix
        cur.execute("""
        SELECT status, COUNT(*) as cnt,
               SUM(CASE WHEN position_value > 0 THEN 1 ELSE 0 END) as with_value
        FROM algo_positions
        GROUP BY status
        """)

        print(f"✅ Fixed {fixed_count} closed positions\n")
        print("Position status breakdown after fix:")
        for row in cur.fetchall():
            status = row[0]
            total = row[1]
            active = row[2] or 0
            print(f"  {status}: {total} positions ({active} with value)")

        return fixed_count


if __name__ == "__main__":
    fix_closed_positions()
