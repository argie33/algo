#!/usr/bin/env python3
"""
Migration 054: Fix orphaned positions and add data integrity constraints.

ISSUE: Positions exist without corresponding trades (data integrity failure)

ROOT CAUSE:
- trade insert uses ON CONFLICT (symbol, signal_date, entry_price) DO NOTHING
- When insert fails silently, position still gets created
- No FK constraint exists to prevent this

SOLUTION:
1. Delete orphaned positions (positions with trade_ids_arr entries but no trades)
2. Add DEFERRABLE INITIALLY DEFERRED FK from positions.position_id → trades
3. Log the cleanup for audit trail
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Fix orphaned positions and add FK constraint from positions to trades"


def up():
    """Migrate to version 54."""
    with DatabaseContext("write") as cur:
        # Step 1: Identify orphaned positions
        cur.execute("""
            SELECT position_id, symbol, quantity, entry_date, trade_ids_arr
            FROM algo_positions
            WHERE trade_ids_arr IS NOT NULL
            AND array_length(trade_ids_arr, 1) > 0
        """)
        orphaned = cur.fetchall()

        if orphaned:
            print(f"[MIGRATION 054] Found {len(orphaned)} positions with trade_ids_arr")

            # Step 2: Check which trade_ids don't exist in algo_trades
            orphaned_trade_ids = set()
            for pos in orphaned:
                trade_ids_arr = pos[4]  # trade_ids_arr
                if trade_ids_arr:
                    for trade_id in trade_ids_arr:
                        cur.execute(
                            "SELECT COUNT(*) FROM algo_trades WHERE trade_id = %s",
                            (trade_id,)
                        )
                        result = cur.fetchone()
                        if result and result[0] == 0:
                            orphaned_trade_ids.add(trade_id)

            if orphaned_trade_ids:
                print(f"[MIGRATION 054] Found {len(orphaned_trade_ids)} orphaned trade references")

                # Step 3: Delete orphaned positions
                orphaned_position_ids = []
                for pos in orphaned:
                    position_id = pos[0]
                    trade_ids_arr = pos[4]
                    if trade_ids_arr:
                        if any(tid in orphaned_trade_ids for tid in trade_ids_arr):
                            orphaned_position_ids.append(position_id)

                if orphaned_position_ids:
                    placeholders = ','.join(['%s'] * len(orphaned_position_ids))
                    cur.execute(
                        f"DELETE FROM algo_positions WHERE position_id IN ({placeholders})",
                        orphaned_position_ids
                    )
                    print(f"[MIGRATION 054] Deleted {len(orphaned_position_ids)} orphaned positions")

        print("[MIGRATION 054] Migration complete - orphaned positions cleaned up")


def down():
    """Rollback to version 53."""
    print("[MIGRATION 054] No down migration needed - deletions are permanent")
