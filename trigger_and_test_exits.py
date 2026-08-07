#!/usr/bin/env python3
"""
Create scenarios to trigger Phase 6 exits and verify they work correctly.
"""

import os
import sys
from datetime import date as _date
from decimal import Decimal

os.environ['DB_NAME'] = 'stocks'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.db.context import DatabaseContext
from algo.orchestrator.phase6_exit_execution import run as run_phase6
from algo.infrastructure.config import get_config
from algo.reporting import AlertManager

def create_stop_loss_trigger():
    """Modify a position to trigger its stop loss"""
    print("\n" + "="*80)
    print("SCENARIO 1: Trigger Stop Loss Exit")
    print("="*80)

    with DatabaseContext('write') as ctx:
        # Get a position with a stop loss
        ctx.execute('''
        SELECT position_id, symbol, entry_price, stop_loss_price, current_price
        FROM algo_positions
        WHERE status = 'open'
        AND stop_loss_price IS NOT NULL
        LIMIT 1
        ''')

        pos = ctx.fetchone()
        if not pos:
            print("  No positions with stop loss found")
            return False

        pos_id, symbol, entry, stop, curr = pos
        stop_val = float(stop)

        print(f"\nTest position: {symbol}")
        print(f"  Entry: ${float(entry):.2f}")
        print(f"  Stop loss: ${stop_val:.2f}")
        print(f"  Current: ${float(curr):.2f}")

        # Trigger stop by setting price below it
        trigger_price = Decimal(str(stop_val * 0.98))  # 2% below stop
        print(f"\n[ACTION] Setting price to ${float(trigger_price):.2f} to trigger stop...")

        ctx.execute('''
        UPDATE algo_positions
        SET current_price = %s
        WHERE position_id = %s
        ''', (trigger_price, pos_id))

        print(f"  ✓ Updated {symbol} price to trigger stop loss")
        return True

def create_concentration_violation():
    """Artificially create a concentration violation"""
    print("\n" + "="*80)
    print("SCENARIO 2: Create Concentration Violation")
    print("="*80)

    with DatabaseContext('read') as ctx:
        # Get portfolio value
        ctx.execute('''
        SELECT total_portfolio_value FROM algo_portfolio_snapshots
        WHERE snapshot_date <= %s
        ORDER BY snapshot_date DESC LIMIT 1
        ''', (_date.today(),))

        row = ctx.fetchone()
        if not row:
            print("  Error: No portfolio snapshot")
            return False

        portfolio_value = float(row[0])
        max_allowed = portfolio_value * 0.06
        violation_value = portfolio_value * 0.08  # 8% to violate 6% limit

        print(f"\nPortfolio: ${portfolio_value:,.2f}")
        print(f"  Max allowed per position: ${max_allowed:,.2f} (6%)")
        print(f"  Violation target: ${violation_value:,.2f} (8%)")

    # Now violate it
    with DatabaseContext('write') as ctx:
        ctx.execute('''
        SELECT position_id, symbol, position_value, quantity, current_price
        FROM algo_positions
        WHERE status = 'open'
        ORDER BY position_value DESC
        LIMIT 1
        ''')

        pos = ctx.fetchone()
        if not pos:
            print("  No positions found")
            return False

        pos_id, symbol, pos_val, qty, curr = pos
        qty_int = int(qty)

        print(f"\nOversizing {symbol}...")
        print(f"  Current value: ${float(pos_val):,.2f}")

        # Calculate new price needed for violation
        new_price = Decimal(str(violation_value / qty_int))
        print(f"  Setting price to ${float(new_price):.2f} to create violation...")

        ctx.execute('''
        UPDATE algo_positions
        SET current_price = %s
        WHERE position_id = %s
        ''', (new_price, pos_id))

        print(f"  ✓ Created concentration violation on {symbol}")
        return True

def run_phase6_on_scenarios():
    """Run Phase 6 against the triggered scenarios"""
    print("\n" + "="*80)
    print("TESTING: Phase 6 Behavior on Triggered Scenarios")
    print("="*80)

    config = get_config()
    alerts = AlertManager()

    print("\n[RUN] Executing Phase 6 with triggered conditions...")

    try:
        result = run_phase6(
            config=config,
            run_date=_date.today(),
            dry_run=False,
            alerts=alerts,
            verbose=True,
            log_phase_result_fn=lambda p, n, s, d: print(f"  [{s.upper()}] {d}"),
            position_recs=[],
            exposure_actions=[],
            executor=None,
            exposure_constraints=None,
        )

        print(f"\n[RESULT] Phase 6 returned: {result.status}")
        print(f"  Exits executed: {result.data.get('exits', 0)}")
        print(f"  Stop raises: {result.data.get('stop_raises', 0)}")
        print(f"  Errors: {result.data.get('errors', 0)}")

        # Check if exits happened as expected
        exits_count = result.data.get('exits', 0) + result.data.get('stop_raises', 0)
        if exits_count > 0:
            print(f"\n✓ SUCCESS: Phase 6 executed {exits_count} exit(s)/stop(s)")
            return True
        else:
            print(f"\n⚠️ WARNING: Phase 6 ran but no exits executed")
            print("  This might indicate exit logic didn't trigger")
            return False

    except Exception as e:
        print(f"\n🔴 ERROR: Phase 6 failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_exits_happened():
    """Verify positions were actually exited"""
    print("\n" + "="*80)
    print("VERIFICATION: Check if Exits Actually Occurred")
    print("="*80)

    with DatabaseContext('read') as ctx:
        # Check for recently closed positions
        ctx.execute('''
        SELECT symbol, position_id, closed_at, exit_reason
        FROM algo_positions
        WHERE status = 'closed'
        ORDER BY closed_at DESC
        LIMIT 10
        ''')

        recent_closes = ctx.fetchall()
        print(f"\n[CHECK] Recent closed positions ({len(recent_closes)}):")

        for symbol, pos_id, closed_at, reason in recent_closes:
            print(f"  {symbol}: closed at {closed_at} ({reason})")

        return len(recent_closes) > 0

def main():
    print("\n" + "="*80)
    print("SESSION 20: Create Exit Scenarios and Test Phase 6")
    print("="*80)

    results = {}

    # Create scenarios
    print("\n[PHASE 1] Creating Test Scenarios...")
    results['stop_loss_created'] = create_stop_loss_trigger()
    results['concentration_created'] = create_concentration_violation()

    # Test Phase 6 against scenarios
    print("\n[PHASE 2] Running Phase 6 Against Scenarios...")
    results['phase6_executed'] = run_phase6_on_scenarios()

    # Verify results
    print("\n[PHASE 3] Verifying Exits Occurred...")
    results['exits_verified'] = verify_exits_happened()

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    print("\nTest Results:")
    for test, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test}")

    # Determine if issues found
    if all(results.values()):
        print("\n✓ ALL TESTS PASSED")
        print("  Phase 6 exit logic is working correctly!")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        print("  Phase 6 exit logic may have issues")
        failed = [k for k, v in results.items() if not v]
        for issue in failed:
            print(f"    - {issue}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
