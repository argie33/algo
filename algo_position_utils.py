#!/usr/bin/env python3
"""
Position utilities for safe trade_ids lookup.

Note: Current implementation uses VARCHAR with comma-delimited trade_ids.
This is fragile (LIKE '%TRD-ABC%' matches both 'TRD-ABC' and 'TRD-ABC-2').

Future: Refactor to use PostgreSQL ARRAY type or junction table.
"""

def build_trade_ids_filter(trade_id):
    """Build a safe LIKE pattern for trade_ids lookup.

    Handles comma-delimited trade_ids with word boundaries.
    Returns SQL WHERE clause fragment.

    Example:
        WHERE trade_ids_match('TRD-ABC', trade_ids)
    """
    # For now, use the existing approach but document it's a known issue
    # Trade IDs are comma-delimited, so wrap with commas for safety
    # e.g., 'TRD-ABC,TRD-DEF,TRD-GHI'
    return f"(trade_ids LIKE '%,{trade_id},%' OR trade_ids LIKE '{trade_id},%' OR trade_ids LIKE '%,{trade_id}' OR trade_ids = '{trade_id}')"


def get_position_for_trade(cur, trade_id):
    """Safely fetch position record for a trade_id.

    Args:
        cur: Database cursor
        trade_id: Trade ID to look up

    Returns:
        Tuple of position fields or None if not found
    """
    filter_clause = build_trade_ids_filter(trade_id)
    cur.execute(f"""
        SELECT position_id, symbol, quantity, avg_entry_price, current_price,
               position_value, status, current_stop_price, target_levels_hit
        FROM algo_positions
        WHERE {filter_clause} AND status = 'open'
        LIMIT 1
    """)
    return cur.fetchone()


if __name__ == "__main__":
    print("Position utilities for safe trade_ids handling")
    print("\nKNOWN ISSUE:")
    print("  trade_ids uses VARCHAR with comma delimiters")
    print("  LIKE queries are fragile (TRD-ABC matches TRD-ABC-2)")
    print("\nRECOMMENDED FIX:")
    print("  1. Migrate to PostgreSQL ARRAY type: ARRAY['TRD-ABC', 'TRD-DEF']")
    print("  2. Use ANY operator: WHERE trade_id = ANY(trade_ids)")
    print("  3. Or create junction table: algo_position_trades(position_id, trade_id)")
    print("\nMigration SQL:")
    print("""
    ALTER TABLE algo_positions ADD COLUMN trade_ids_arr TEXT[];
    UPDATE algo_positions SET trade_ids_arr = string_to_array(trade_ids, ',');
    -- Backfill to array, then drop old column after validation
    """)
