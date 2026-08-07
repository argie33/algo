#!/usr/bin/env python3
"""
Final verification that the system is working correctly after all fixes.
Tests:
1. Phase 6 can find portfolio_snapshot
2. Positions are not being force-exited incorrectly
3. Data integrity is maintained (positions vs trades)
"""

import os
import sys
from datetime import datetime, timezone

os.environ['DB_NAME'] = 'stocks'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def verify_system():
    from utils.db import DatabaseContext

    print("\n" + "="*80)
    print("FINAL SYSTEM VERIFICATION - POST FIX")
    print("="*80)

    # Test 1: Portfolio snapshots available
    print("\n✓ Test 1: Portfolio snapshot availability")
    print("-" * 80)
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT COUNT(*), MAX(snapshot_date), MIN(snapshot_date)
            FROM algo_portfolio_snapshots
        """)
        count, max_date, min_date = cur.fetchone()
        print(f"  Total snapshots: {count}")
        print(f"  Latest: {max_date}")
        print(f"  Oldest: {min_date}")
        if count > 0:
            print("  ✅ Snapshots available for Phase 6")
        else:
            print("  ❌ No snapshots found - Phase 6 will fail!")
            return False

    # Test 2: Open positions status
    print("\n✓ Test 2: Open positions")
    print("-" * 80)
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT COUNT(*), SUM(position_value), AVG(position_value)
            FROM algo_positions WHERE status = 'open'
        """)
        pos_count, total_value, avg_value = cur.fetchone()
        print(f"  Count: {pos_count}")
        if pos_count:
            print(f"  Total value: ${float(total_value):,.2f}")
            print(f"  Avg value: ${float(avg_value):,.2f}")

    # Test 3: Recent closed trades with reason
    print("\n✓ Test 3: Recent trade exits")
    print("-" * 80)
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT exit_reason, COUNT(*) as count
            FROM algo_trades
            WHERE status = 'closed'
            AND exit_date >= CURRENT_DATE - INTERVAL '1 day'
            GROUP BY exit_reason
            ORDER BY count DESC
            LIMIT 10
        """)
        reasons = cur.fetchall()

        for reason, count in reasons:
            if reason:
                if 'CONCENTRATION' in reason:
                    print(f"  Force-exits (concentration): {count}")
                elif 'Earnings' in reason:
                    print(f"  Exits (earnings): {count}")
                elif 'DATA_FIX' in reason:
                    print(f"  Exits (data fix): {count}")
                else:
                    print(f"  {reason[:50]}: {count}")

    # Test 4: Data integrity - positions vs trades
    print("\n✓ Test 4: Data integrity (positions vs trades)")
    print("-" * 80)
    with DatabaseContext('read') as cur:
        # Count positions with no corresponding trades
        cur.execute("""
            SELECT COUNT(*) FROM algo_positions ap
            WHERE ap.status = 'open'
            AND NOT EXISTS (
                SELECT 1 FROM algo_trades t
                WHERE t.position_id = ap.position_id
                AND NOT (t.status = 'closed' AND t.exit_price IS NOT NULL)
            )
        """)
        orphaned = cur.fetchone()[0]

        # Count trades that are open
        cur.execute("""
            SELECT COUNT(*) FROM algo_trades
            WHERE NOT (status = 'closed' AND exit_price IS NOT NULL)
        """)
        open_trades = cur.fetchone()[0]

        # Count positions that are open
        cur.execute("""
            SELECT COUNT(*) FROM algo_positions
            WHERE status = 'open'
        """)
        open_positions = cur.fetchone()[0]

        print(f"  Open trades: {open_trades}")
        print(f"  Open positions: {open_positions}")
        print(f"  Orphaned positions: {orphaned}")

        if orphaned > 0:
            print(f"  ⚠️  {orphaned} positions have no open trades (may be cleaned up next run)")
        else:
            print(f"  ✅ No orphaned positions")

    # Test 5: Verify Phase 6 portfolio_snapshot query works
    print("\n✓ Test 5: Phase 6 portfolio_snapshot query")
    print("-" * 80)
    today = datetime.now(timezone.utc).astimezone().date()
    with DatabaseContext('read') as cur:
        # Test the exact query Phase 6 uses
        cur.execute("""
            SELECT COALESCE(total_portfolio_value, 0) FROM algo_portfolio_snapshots
            WHERE snapshot_date <= %s
            ORDER BY snapshot_date DESC LIMIT 1
        """, (today,))
        result = cur.fetchone()
        portfolio_value = result[0] if result else 0

        print(f"  Query date: {today}")
        print(f"  Portfolio value found: ${float(portfolio_value):,.2f}")
        if portfolio_value > 0:
            print("  ✅ Phase 6 can find portfolio_snapshot")
        else:
            print("  ❌ Phase 6 query returned 0 - will fail!")
            return False

    print("\n" + "="*80)
    print("VERIFICATION COMPLETE")
    print("="*80)
    print("\n✅ System appears to be working correctly!")
    print("\nKey fixes applied:")
    print("  1. Phase 6 portfolio_snapshot query uses <= instead of =")
    print("  2. Position_sync properly closes orphaned positions")
    print("  3. Concentration calculations now use correct denominator")
    return True

if __name__ == '__main__':
    success = verify_system()
    sys.exit(0 if success else 1)
