#!/usr/bin/env python3
"""Verify that recent fixes are working correctly."""

from utils.db.context import DatabaseContext
from datetime import datetime, timedelta
import sys

def check_fixed_issues():
    """Verify that recent fixes are working."""

    print("=" * 80)
    print("VERIFICATION OF RECENT FIXES")
    print("=" * 80)

    issues_status = []

    with DatabaseContext(role='read') as ctx:
        cursor = ctx.connection.cursor()

        # 1. Check profit_loss_pct NULL issue
        print("\n[1/4] Checking profit_loss_pct NULL bug fix...")
        cursor.execute('''
            SELECT COUNT(*) as null_pct_count
            FROM algo_trades
            WHERE status = 'closed'
              AND exit_price IS NOT NULL
              AND profit_loss_pct IS NULL
        ''')

        null_count = cursor.fetchone()[0]
        if null_count == 0:
            print("  [OK] PASS: No NULL profit_loss_pct on closed trades")
            issues_status.append(('profit_loss_pct_null', 'FIXED'))
        else:
            print(f"  [FAIL] {null_count} closed trades still have NULL profit_loss_pct")
            issues_status.append(('profit_loss_pct_null', 'STILL_BROKEN'))

        # 2. Check position bulk update fix
        print("\n[2/4] Checking position bulk update fix...")
        cursor.execute('''
            SELECT symbol, COUNT(*) as open_count
            FROM algo_positions
            WHERE status = 'open'
            GROUP BY symbol
            HAVING COUNT(*) > 1
        ''')

        dups = cursor.fetchall()
        if not dups:
            print("  [OK] PASS: No duplicate open positions for same symbol")
            issues_status.append(('duplicate_positions', 'FIXED'))
        else:
            print(f"  [WARN] WARNING: {len(dups)} symbols still have duplicate open positions:")
            for symbol, count in dups:
                print(f"    - {symbol}: {count} open positions")
            issues_status.append(('duplicate_positions', 'WARNING'))

        # 3. Check for recent orchestrator errors
        print("\n[3/4] Checking orchestrator error rate...")
        cursor.execute('''
            SELECT overall_status, COUNT(*) as cnt
            FROM algo_orchestrator_runs
            WHERE started_at >= NOW() - interval '6 hours'
            GROUP BY overall_status
            ORDER BY overall_status
        ''')

        results_by_status = dict(cursor.fetchall())
        errors = results_by_status.get('error', 0)
        halts = results_by_status.get('halted', 0)
        success = results_by_status.get('success', 0) + results_by_status.get('ok', 0)

        total = errors + halts + success + results_by_status.get('degraded', 0)

        print(f"  Last 6 hours: {success} success, {errors} errors, {halts} halts, {results_by_status.get('degraded', 0)} degraded")

        if errors == 0 and halts <= 5:  # Allow some halts (market hours guard)
            print(f"  [OK] PASS: Error rate acceptable")
            issues_status.append(('orchestrator_stability', 'GOOD'))
        else:
            print(f"  [WARN] {errors} errors and {halts} halts in last 6 hours")
            issues_status.append(('orchestrator_stability', 'NEEDS_MONITORING'))

        # 4. Check data integrity
        print("\n[4/4] Checking data integrity...")

        cursor.execute('''
            SELECT
                COUNT(*) as total_trades,
                COUNT(CASE WHEN status = 'closed' AND exit_price IS NULL THEN 1 END) as closed_no_exit,
                COUNT(CASE WHEN status = 'open' AND exit_price IS NOT NULL THEN 1 END) as open_with_exit
            FROM algo_trades
            WHERE entry_date >= NOW()::date - 10
        ''')

        total_trades, closed_no_exit, open_with_exit = cursor.fetchone()

        if closed_no_exit == 0 and open_with_exit == 0:
            print(f"  [OK] PASS: {total_trades} trades, all consistent (no integrity issues)")
            issues_status.append(('data_integrity', 'GOOD'))
        else:
            print(f"  [FAIL] Integrity issues - {closed_no_exit} closed trades without exit, {open_with_exit} open trades with exit")
            issues_status.append(('data_integrity', 'BROKEN'))

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for issue, status in issues_status:
        symbol = "OK" if status == "GOOD" or status == "FIXED" else ("WARN" if "WARNING" in status else "FAIL")
        print(f"[{symbol}] {issue:30} {status}")

    all_good = all(s in ('FIXED', 'GOOD', 'WARNING') for _, s in issues_status)

    if all_good:
        print("\n[OK] FIXES APPEAR TO BE WORKING")
        return 0
    else:
        print("\n[FAIL] SOME ISSUES REMAIN - FURTHER INVESTIGATION NEEDED")
        return 1

if __name__ == '__main__':
    sys.exit(check_fixed_issues())
