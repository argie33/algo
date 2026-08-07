#!/usr/bin/env python3
"""
Direct Phase 6 testing to find and document actual issues.
Tests exit logic, concentration enforcement, stop loss handling.
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

def find_issues():
    """Directly call Phase 6 and find any issues"""
    print("\n" + "="*80)
    print("PHASE 6 DIRECT EXECUTION TEST - Finding Actual Issues")
    print("="*80)

    config = get_config()
    alerts = AlertManager()

    # Prepare test data
    position_recs = []
    exposure_actions = []

    print("\n[TEST] Calling Phase 6 directly with current system state...")
    print("This will exercise all Phase 6 logic paths")

    try:
        result = run_phase6(
            config=config,
            run_date=_date.today(),
            dry_run=False,
            alerts=alerts,
            verbose=True,
            log_phase_result_fn=lambda p, n, s, d: print(f"  [PHASE {p}] {n}: {s} - {d}"),
            position_recs=position_recs,
            exposure_actions=exposure_actions,
            executor=None,
            exposure_constraints=None,
        )
        print(f"\n[RESULT] Phase 6 completed: {result}")
        return True, result
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Phase 6 failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False, str(e)

def check_for_silent_failures():
    """Scan logs for silent failures that Phase 6 might have"""
    print("\n" + "="*80)
    print("CHECKING: Silent Failure Patterns in Phase 6")
    print("="*80)

    with DatabaseContext('read') as ctx:
        # Check for positions with issues that Phase 6 might silently skip

        print("\n[CHECK 1] Positions with missing stop losses (should be forced out)")
        ctx.execute('''
        SELECT symbol, position_id, entry_price, current_price, stop_loss_price
        FROM algo_positions
        WHERE status = 'open'
        AND stop_loss_price IS NULL
        LIMIT 5
        ''')
        missing_stops = ctx.fetchall()
        if missing_stops:
            print(f"  FOUND {len(missing_stops)} positions with NULL stop_loss_price:")
            for row in missing_stops:
                print(f"    {row[0]}: {row[1][:8]}... (entry={float(row[2]):.2f}, current={float(row[3]):.2f})")
            print("  ⚠️ ISSUE: Phase 6 might not handle these correctly")

        print("\n[CHECK 2] Positions with extreme P&L (should trigger stops)")
        ctx.execute('''
        SELECT symbol, position_id, entry_price, current_price,
               ((current_price - entry_price) / entry_price * 100) as pnl_pct
        FROM algo_positions
        WHERE status = 'open'
        ORDER BY ABS((current_price - entry_price) / entry_price) DESC
        LIMIT 5
        ''')
        extremes = ctx.fetchall()
        print(f"  Positions with largest P&L:")
        for row in extremes:
            pnl = float(row[4])
            print(f"    {row[0]:6} : {pnl:+7.2f}% (entry={float(row[2]):8.2f}, curr={float(row[3]):8.2f})")

        print("\n[CHECK 3] Checking for trade-position mismatch")
        ctx.execute('''
        SELECT ap.symbol, COUNT(ap.id) as positions, COUNT(t.trade_id) as trades
        FROM algo_positions ap
        LEFT JOIN algo_trades t ON t.position_id = ap.position_id
        WHERE ap.status = 'open'
        GROUP BY ap.symbol
        HAVING COUNT(ap.id) != COUNT(t.trade_id)
        ''')
        mismatches = ctx.fetchall()
        if mismatches:
            print(f"  FOUND {len(mismatches)} position/trade mismatches:")
            for row in mismatches:
                print(f"    {row[0]}: {row[1]} positions but {row[2]} trades")
            print("  🔴 CRITICAL ISSUE: Phase 6 exit might fail on these!")
        else:
            print("  ✓ All positions/trades match correctly")

def test_concentration_enforcement():
    """Test if Phase 6 would force-exit oversized positions"""
    print("\n" + "="*80)
    print("TEST: Concentration Enforcement (Force-Exit Logic)")
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
            print("  ERROR: No portfolio snapshot")
            return False

        portfolio_value = float(row[0])
        max_pct = 6.0
        max_value = portfolio_value * (max_pct / 100)

        print(f"\nPortfolio: ${portfolio_value:,.2f}")
        print(f"Individual limit (6%): ${max_value:,.2f}")

        ctx.execute('''
        SELECT symbol, position_value
        FROM algo_positions
        WHERE status = 'open'
        AND position_value > %s
        ORDER BY position_value DESC
        ''', (Decimal(str(max_value)),))

        violations = ctx.fetchall()

        if violations:
            print(f"\n🔴 FOUND CONCENTRATION VIOLATIONS ({len(violations)}):")
            for symbol, pos_value in violations:
                pct = (float(pos_value) / portfolio_value) * 100
                print(f"  {symbol}: ${float(pos_value):,.2f} ({pct:.2f}%) - EXCEEDS 6% limit")
            print("\n⚠️ ISSUE: Phase 6 should force-exit these but hasn't!")
            return False
        else:
            print("\n✓ No concentration violations - system is currently healthy")
            return True

def main():
    print("\n" + "="*80)
    print("SESSION 20 CONTINUATION: Find and Document Real Issues")
    print("="*80)

    issues_found = []

    # Test 1: Direct Phase 6 execution
    print("\n[STEP 1] Running Phase 6 directly...")
    success, result = find_issues()
    if not success:
        issues_found.append(f"Phase 6 execution failed: {result}")

    # Test 2: Check for silent failures
    print("\n[STEP 2] Checking for silent failure patterns...")
    check_for_silent_failures()

    # Test 3: Test concentration enforcement
    print("\n[STEP 3] Testing concentration limit enforcement...")
    if not test_concentration_enforcement():
        issues_found.append("Concentration enforcement may not be working")

    # Report findings
    print("\n" + "="*80)
    print("ISSUES FOUND")
    print("="*80)

    if issues_found:
        print(f"\n🔴 FOUND {len(issues_found)} ISSUE(S):\n")
        for i, issue in enumerate(issues_found, 1):
            print(f"{i}. {issue}")
        print("\nNext: Fix each issue and re-test")
        return 1
    else:
        print("\n✓ No issues found - system appears healthy")
        print("  (No exit conditions triggered, no concentration violations)")
        print("  Next: Run orchestrator multiple times to verify stability")
        return 0

if __name__ == "__main__":
    sys.exit(main())
