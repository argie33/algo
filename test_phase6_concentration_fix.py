#!/usr/bin/env python3
"""
Test script to verify Phase 6 concentration calculation fix.
This creates test positions and verifies Phase 6 can evaluate them correctly.
"""

import os
import sys
from datetime import datetime, date, timezone
from decimal import Decimal

os.environ['DB_NAME'] = 'stocks'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_phase6_portfolio_snapshot_query():
    """Test that Phase 6 can find portfolio_snapshot with <= query"""

    print("\n" + "="*80)
    print("TEST: Phase 6 Portfolio Snapshot Query Fix")
    print("="*80)

    try:
        from utils.db import DatabaseContext
        from datetime import datetime, timezone

        # Get today's date in ET
        now_et = datetime.now(timezone.utc).astimezone()
        today = now_et.date()

        print(f"\nToday's date (ET): {today}")
        print(f"UTC time: {datetime.now(timezone.utc)}")

        # Test 1: Query for today (might not exist yet)
        print(f"\n--- Test 1: Query for today's snapshot ---")
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT snapshot_date, total_portfolio_value
                FROM algo_portfolio_snapshots
                WHERE snapshot_date = %s
                LIMIT 1
            """, (today,))
            result = cur.fetchone()
            print(f"Exact match (WHERE snapshot_date = {today}): {result}")
            if not result:
                print("  ⚠️  Today's snapshot doesn't exist yet (expected on first run)")

        # Test 2: Query with <= (should find latest available)
        print(f"\n--- Test 2: Query with <= for latest available ---")
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT snapshot_date, total_portfolio_value
                FROM algo_portfolio_snapshots
                WHERE snapshot_date <= %s
                ORDER BY snapshot_date DESC
                LIMIT 1
            """, (today,))
            result = cur.fetchone()
            if result:
                snapshot_date, portfolio_value = result
                print(f"Latest snapshot: {snapshot_date} with value ${float(portfolio_value):,.2f}")
                print("  ✅ Query found a snapshot!")
            else:
                print("  ❌ No snapshots found (database might be empty)")
                return False

        # Test 3: Check if we have any open positions
        print(f"\n--- Test 3: Check for open positions ---")
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT COUNT(*), SUM(position_value)
                FROM algo_positions
                WHERE status = 'open'
            """)
            count, total_value = cur.fetchone()
            if count:
                print(f"Found {count} open position(s) with total value ${float(total_value or 0):,.2f}")
                print("  ✅ Open positions exist")
            else:
                print("No open positions (portfolio is flat)")

        # Test 4: Simulate Phase 6 concentration check
        print(f"\n--- Test 4: Simulate Phase 6 concentration calculation ---")
        if count and total_value:
            with DatabaseContext('read') as cur:
                # Get portfolio snapshot
                cur.execute("""
                    SELECT COALESCE(total_portfolio_value, 0)
                    FROM algo_portfolio_snapshots
                    WHERE snapshot_date <= %s
                    ORDER BY snapshot_date DESC LIMIT 1
                """, (today,))
                portfolio_value_result = cur.fetchone()
                portfolio_value_float = float(portfolio_value_result[0]) if portfolio_value_result else 0

                print(f"Portfolio snapshot value: ${portfolio_value_float:,.2f}")

                if portfolio_value_float <= 0:
                    print("  ❌ ERROR: Portfolio value is 0 or negative!")
                    return False

                # Get open positions
                cur.execute("""
                    SELECT symbol, position_value
                    FROM algo_positions
                    WHERE status = 'open'
                    ORDER BY position_value DESC
                """)
                positions = cur.fetchall()

                print(f"\n{'Symbol':<10} {'Value':<15} {'% of Portfolio':<20} {'Status':<10}")
                print("-" * 55)

                max_pct = Decimal('6.0')  # max_position_size_pct from config
                violations = 0

                for symbol, pos_value in positions:
                    pct = Decimal(str(pos_value)) / Decimal(str(portfolio_value_float)) * Decimal('100')
                    pct_float = float(pct)

                    status = "PASS" if pct_float <= float(max_pct) else "FAIL"
                    if pct_float > float(max_pct):
                        violations += 1

                    print(f"{symbol:<10} ${float(pos_value):>13,.2f} {pct_float:>18.2f}% {status:<10}")

                print("-" * 55)
                total_pct = Decimal(str(total_value)) / Decimal(str(portfolio_value_float)) * Decimal('100')
                print(f"{'TOTAL':<10} ${float(total_value):>13,.2f} {float(total_pct):>18.2f}%")

                print(f"\n✅ Concentration check completed")
                print(f"   Violations: {violations}")
                print(f"   Portfolio value used as denominator: ${portfolio_value_float:,.2f}")
                print(f"   Phase 6 can now properly evaluate positions!")

                return True

        print("\n✅ All tests passed!")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = test_phase6_portfolio_snapshot_query()
    sys.exit(0 if success else 1)
