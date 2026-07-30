#!/usr/bin/env python3
"""
Stress test to verify all recent fixes are working.
Runs orchestrator multiple times and checks for:
1. Phase 7 lock timeouts (should be eliminated)
2. Consecutive losses halts (should be eliminated)
3. Duplicate trades (should be prevented)
4. Data integrity (should be maintained)
"""

import subprocess
import time
from utils.db.context import DatabaseContext

def run_orchestrator():
    """Run one orchestrator iteration."""
    result = subprocess.run(
        ["python", "scripts/run_local_orchestrator.py", "--afternoon", "--force"],
        capture_output=True,
        text=True,
        timeout=300
    )
    return result.returncode == 0

def check_results():
    """Verify that recent fixes are working."""

    with DatabaseContext(role='read') as ctx:
        cursor = ctx.connection.cursor()

        # 1. Check for Phase 7 lock timeouts
        cursor.execute('''
            SELECT COUNT(*)
            FROM algo_orchestrator_runs
            WHERE started_at >= NOW() - interval '3 hours'
            AND halt_reason LIKE '%Phase 7%'
            AND halt_reason LIKE '%LockAcquisition%'
        ''')
        phase7_timeouts = cursor.fetchone()[0]

        # 2. Check for consecutive losses halts
        cursor.execute('''
            SELECT COUNT(*)
            FROM algo_orchestrator_runs
            WHERE started_at >= NOW() - interval '3 hours'
            AND halt_reason LIKE '%Consecutive%'
        ''')
        consecutive_halts = cursor.fetchone()[0]

        # 3. Check for duplicate trades (same symbol, same day)
        cursor.execute('''
            SELECT COUNT(DISTINCT symbol)
            FROM (
                SELECT symbol
                FROM algo_trades
                WHERE trade_date >= NOW()::date - 5
                GROUP BY symbol, trade_date
                HAVING COUNT(*) > 1
            ) dup_check
        ''')
        duplicate_symbols = cursor.fetchone()[0]

        # 4. Check data integrity
        cursor.execute('''
            SELECT
                COUNT(*) as total_closed,
                COUNT(CASE WHEN profit_loss_pct IS NULL THEN 1 END) as null_pct
            FROM algo_trades
            WHERE status = 'closed'
            AND exit_price IS NOT NULL
            AND trade_date >= NOW()::date - 5
        ''')
        total_closed, null_pct = cursor.fetchone()

        # 5. Check recent success rate
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN overall_status IN ('success', 'ok') THEN 1 ELSE 0 END) as success_count
            FROM algo_orchestrator_runs
            WHERE started_at >= NOW() - interval '3 hours'
        ''')
        total_runs, success_runs = cursor.fetchone()
        success_rate = 100 * success_runs / total_runs if total_runs > 0 else 0

        return {
            'phase7_timeouts': phase7_timeouts,
            'consecutive_halts': consecutive_halts,
            'duplicate_symbols': duplicate_symbols,
            'null_pct_count': null_pct,
            'total_closed_trades': total_closed,
            'total_runs': total_runs,
            'success_rate': success_rate
        }

def main():
    print("=" * 80)
    print("STRESS TEST: Verifying All Fixes")
    print("=" * 80)

    print("\nRunning orchestrator 3 times to stress test fixes...")
    for i in range(3):
        print(f"\n  Run {i+1}/3...", end=" ", flush=True)
        try:
            if run_orchestrator():
                print("OK")
            else:
                print("FAILED")
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(2)

    print("\nVerifying fix results...")
    results = check_results()

    print("\n" + "=" * 80)
    print("VERIFICATION RESULTS")
    print("=" * 80)

    all_good = True

    # Phase 7 lock timeouts
    print(f"\n[1/4] Phase 7 Lock Timeouts (last 3h)")
    print(f"  Count: {results['phase7_timeouts']}")
    if results['phase7_timeouts'] > 0:
        print(f"  STATUS: FAILED - Still occurring")
        all_good = False
    else:
        print(f"  STATUS: PASS - No timeouts detected")

    # Consecutive losses halts
    print(f"\n[2/4] Consecutive Losses Halts (last 3h)")
    print(f"  Count: {results['consecutive_halts']}")
    if results['consecutive_halts'] > 0:
        print(f"  STATUS: FAILED - Still occurring")
        all_good = False
    else:
        print(f"  STATUS: PASS - No halts detected")

    # Duplicate trades
    print(f"\n[3/4] Duplicate Trades (last 5d)")
    print(f"  Symbols with duplicates: {results['duplicate_symbols']}")
    if results['duplicate_symbols'] > 0:
        print(f"  STATUS: FAILED - Duplicates still being created")
        all_good = False
    else:
        print(f"  STATUS: PASS - No duplicates detected")

    # Data integrity
    print(f"\n[4/4] Data Integrity")
    print(f"  Total closed trades (last 5d): {results['total_closed_trades']}")
    print(f"  NULL profit_loss_pct: {results['null_pct_count']}")
    if results['null_pct_count'] > 0:
        print(f"  STATUS: FAILED - Still have NULL values")
        all_good = False
    else:
        print(f"  STATUS: PASS - All P&L values populated")

    # Success rate
    print(f"\n[5/5] Orchestrator Stability")
    print(f"  Recent runs: {results['total_runs']}")
    print(f"  Success rate: {results['success_rate']:.1f}%")
    if results['success_rate'] < 80:
        print(f"  STATUS: WARNING - Success rate below 80%")
        all_good = False
    else:
        print(f"  STATUS: PASS - Success rate acceptable")

    print("\n" + "=" * 80)
    if all_good:
        print("RESULT: ALL FIXES VERIFIED - SYSTEM IS BULLETPROOF")
        return 0
    else:
        print("RESULT: SOME ISSUES REMAIN - FURTHER INVESTIGATION NEEDED")
        return 1

if __name__ == '__main__':
    import sys
    sys.exit(main())
