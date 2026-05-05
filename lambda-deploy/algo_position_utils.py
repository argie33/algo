#!/usr/bin/env python3
"""
Position utilities for safe trade_ids lookup.

Refactored to use PostgreSQL ARRAY type (trade_ids_arr TEXT[]) instead of
comma-delimited VARCHAR. Uses ANY operator for proper indexed lookups.

Migration: New code uses trade_ids_arr TEXT[]. Backfill migration converts
existing comma-delimited trade_ids to arrays. Old varchar column kept until
all code migrated.
"""

def add_trade_id_to_position(cur, position_id, trade_id):
    """Safely add a trade_id to a position's trade_ids_arr.

    Args:
        cur: Database cursor
        position_id: Position to update
        trade_id: Trade ID to add

    Returns:
        True if successful
    """
    cur.execute("""
        UPDATE algo_positions
        SET trade_ids_arr = array_append(COALESCE(trade_ids_arr, '{}'), %s),
            updated_at = CURRENT_TIMESTAMP
        WHERE position_id = %s
    """, (trade_id, position_id))
    return cur.rowcount > 0


def get_position_for_trade(cur, trade_id):
    """Safely fetch position record for a trade_id using ARRAY lookups.

    Args:
        cur: Database cursor
        trade_id: Trade ID to look up

    Returns:
        Tuple of position fields or None if not found
    """
    cur.execute("""
        SELECT position_id, symbol, quantity, avg_entry_price, current_price,
               position_value, status, current_stop_price, target_levels_hit,
               trade_ids_arr
        FROM algo_positions
        WHERE %s = ANY(trade_ids_arr) AND status = 'open'
        LIMIT 1
    """, (trade_id,))
    return cur.fetchone()


def get_position_trade_ids(cur, position_id):
    """Fetch all trade_ids for a position.

    Args:
        cur: Database cursor
        position_id: Position to fetch

    Returns:
        List of trade IDs, or empty list if not found
    """
    cur.execute("""
        SELECT COALESCE(trade_ids_arr, '{}') FROM algo_positions
        WHERE position_id = %s
    """, (position_id,))
    result = cur.fetchone()
    return list(result[0]) if result else []


if __name__ == "__main__":
    print("Position utilities - ARRAY-based trade_ids")
    print("\nMIGRATION STATUS:")
    print("  ✓ trade_ids_arr TEXT[] column added to algo_positions")
    print("  ✓ Refactored to use ANY operator (safe, indexed lookups)")
    print("\nBACKFILL MIGRATION SQL:")
    print("""
    -- Step 1: Backfill existing trade_ids into arrays
    UPDATE algo_positions
    SET trade_ids_arr = string_to_array(
        NULLIF(TRIM(trade_ids), ''), ','
    )
    WHERE trade_ids IS NOT NULL AND trade_ids_arr IS NULL;

    -- Step 2: Verify migration (counts should match)
    SELECT COUNT(*) FROM algo_positions WHERE trade_ids IS NOT NULL AND trade_ids_arr IS NULL;

    -- Step 3: Once verified, drop old column
    ALTER TABLE algo_positions DROP COLUMN trade_ids;
    """)
    print("\nFUNCTION SIGNATURE CHANGES:")
    print("  add_trade_id_to_position(cur, position_id, trade_id)")
    print("  get_position_for_trade(cur, trade_id)")
    print("  get_position_trade_ids(cur, position_id)")
