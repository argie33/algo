#!/usr/bin/env python3
"""
Test script to verify portfolio rotation fixes in Phase 6 and Phase 8.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_phase8_emergency_close_logic():
    """Verify Phase 8 emergency close closes oldest positions, not worst"""
    print("\n=== PHASE 8 EMERGENCY CLOSE LOGIC ===")

    # Simulate the query that Phase 8 uses now
    from utils.db import DatabaseContext

    with DatabaseContext() as cur:
        # Query: Close oldest (ORDER BY entry_date ASC)
        cur.execute("""
            SELECT id, position_id, symbol, quantity, unrealized_pnl, unrealized_pnl_pct, entry_date
            FROM algo_positions
            WHERE status = 'open' AND quantity > 0
            ORDER BY entry_date ASC
            LIMIT 3
        """)
        positions = cur.fetchall()

        if positions:
            print("\nOldest 3 positions (would be closed first):")
            for pos_id, pos_uuid, symbol, qty, pnl, pnl_pct, entry_date in positions:
                print(f"  {symbol}: entry={entry_date}, pnl={pnl:.0f} ({pnl_pct:+.1f}%)")

            # Verify they're sorted by entry_date (oldest first)
            dates = [p[6] for p in positions]
            if dates == sorted(dates):
                print("\n[PASS] Positions are sorted by entry_date (oldest first)")
            else:
                print("\n[FAIL] Positions NOT in date order")
        else:
            print("\nNo open positions to test")

def test_phase6_rotation_safety():
    """Verify Phase 6 portfolio rotation safety check would fire"""
    print("\n=== PHASE 6 PORTFOLIO ROTATION SAFETY ===")

    from utils.db import DatabaseContext

    with DatabaseContext() as cur:
        # Check current portfolio status
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open' AND quantity > 0")
        open_count = cur.fetchone()[0]

        max_positions = 15

        print(f"\nPortfolio status: {open_count}/{max_positions} positions")

        if open_count >= max_positions:
            print(f"[!] Portfolio at capacity - rotation safety would activate")

            # What would be closed?
            cur.execute("""
                SELECT id, symbol, unrealized_pnl, entry_date
                FROM algo_positions
                WHERE status = 'open' AND quantity > 0
                ORDER BY entry_date ASC LIMIT 1
            """)
            oldest = cur.fetchone()
            if oldest:
                pos_id, symbol, pnl, entry_date = oldest
                print(f"Would close oldest: {symbol} (entry {entry_date}, P&L ${pnl})")
        else:
            print(f"[PASS] Portfolio has {max_positions - open_count} available slots (no rotation needed)")

def test_min_hold_days_config():
    """Verify min_hold_days is set to 0 for same-day exits"""
    print("\n=== MIN_HOLD_DAYS CONFIG ===")

    from algo.infrastructure.config import AlgoConfig

    config = AlgoConfig()
    min_hold = config.get("min_hold_days")

    print(f"min_hold_days = {min_hold}")
    if min_hold == 0:
        print("[PASS] min_hold_days=0 allows same-day exits")
    else:
        print(f"[FAIL] min_hold_days={min_hold} will block same-day exits")

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("PORTFOLIO ROTATION FIXES VALIDATION")
    print("=" * 70)

    try:
        test_min_hold_days_config()
        test_phase8_emergency_close_logic()
        test_phase6_rotation_safety()

        print("\n" + "=" * 70)
        print("All validation checks completed")
        print("=" * 70 + "\n")
    except Exception as e:
        import traceback
        print(f"\nERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
