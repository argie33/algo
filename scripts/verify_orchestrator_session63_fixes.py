#!/usr/bin/env python3
"""
Comprehensive verification script for Session 63 orchestrator fixes.

Designed to run immediately after orchestrator completes on Monday trading day.
Checks for the 4 critical bugs reported in Session 62:
1. run_date mismatch
2. Decimal/float TypeError
3. NameError position_id
4. UniqueViolation database constraint

Usage:
  python scripts/verify_orchestrator_session63_fixes.py
"""

import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal

def check_orchestrator_execution():
    """Verify orchestrator ran successfully and logged correct run_date."""
    from utils.db import DatabaseContext

    et = ZoneInfo("America/New_York")
    today = datetime.now(et).date()

    print("\n" + "="*70)
    print("CHECK 1: Orchestrator Execution & run_date Correctness")
    print("="*70)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT run_id, run_date, overall_status, started_at
            FROM orchestrator_execution_log
            WHERE DATE(started_at) = %s
            ORDER BY started_at DESC
            LIMIT 5
        """, [today])

        rows = cur.fetchall()
        if not rows:
            print(f"❌ FAIL: No orchestrator runs found for today ({today})")
            return False

        print(f"Found {len(rows)} orchestrator runs for {today}:")
        all_correct = True
        for row in rows:
            run_id, run_date, status, started_at = row
            run_date_correct = (run_date == today)
            status_icon = "✅" if run_date_correct else "❌"
            print(f"  {status_icon} {run_id}: run_date={run_date} (expected {today}), status={status}")
            if not run_date_correct:
                all_correct = False

        return all_correct


def check_decimal_float_errors():
    """Search for Decimal/float TypeError in signal rejections."""
    from utils.db import DatabaseContext

    et = ZoneInfo("America/New_York")
    today = datetime.now(et).date()

    print("\n" + "="*70)
    print("CHECK 2: Decimal/float TypeError")
    print("="*70)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT rejection_reason, COUNT(*) as count
            FROM filter_rejection_log
            WHERE eval_date = %s
            AND rejection_reason ILIKE '%Decimal%float%'
            GROUP BY rejection_reason
        """, [today])

        rows = cur.fetchall()
        if rows:
            print(f"❌ FAIL: Found {sum(r[1] for r in rows)} Decimal/float errors:")
            for reason, count in rows:
                print(f"  {count}x: {reason[:80]}")
            return False
        else:
            print("✅ PASS: No Decimal/float TypeErrors found")
            return True


def check_position_id_errors():
    """Search for NameError position_id in signal rejections."""
    from utils.db import DatabaseContext

    et = ZoneInfo("America/New_York")
    today = datetime.now(et).date()

    print("\n" + "="*70)
    print("CHECK 3: NameError position_id")
    print("="*70)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT rejection_reason, COUNT(*) as count
            FROM filter_rejection_log
            WHERE eval_date = %s
            AND rejection_reason ILIKE '%position_id%not defined%'
            GROUP BY rejection_reason
        """, [today])

        rows = cur.fetchall()
        if rows:
            print(f"❌ FAIL: Found {sum(r[1] for r in rows)} position_id NameErrors:")
            for reason, count in rows:
                print(f"  {count}x: {reason[:80]}")
            return False
        else:
            print("✅ PASS: No position_id NameErrors found")
            return True


def check_unique_violation_errors():
    """Search for UniqueViolation in signal rejections."""
    from utils.db import DatabaseContext

    et = ZoneInfo("America/New_York")
    today = datetime.now(et).date()

    print("\n" + "="*70)
    print("CHECK 4: UniqueViolation Database Constraints")
    print("="*70)

    with DatabaseContext("read") as cur:
        # Check for UniqueViolation in signal rejections
        cur.execute("""
            SELECT rejection_reason, COUNT(*) as count
            FROM filter_rejection_log
            WHERE eval_date = %s
            AND rejection_reason ILIKE '%UniqueViolation%'
            GROUP BY rejection_reason
        """, [today])

        rows = cur.fetchall()
        if rows:
            print(f"❌ FAIL: Found {sum(r[1] for r in rows)} UniqueViolation errors:")
            for reason, count in rows:
                print(f"  {count}x: {reason[:80]}")

            # Investigate: check for duplicate idempotency_keys or trade_ids
            print("\n  Investigating duplicate keys in algo_trades:")
            cur.execute("""
                SELECT idempotency_key, COUNT(*) as count
                FROM algo_trades
                WHERE trade_date = %s
                GROUP BY idempotency_key
                HAVING COUNT(*) > 1
                LIMIT 5
            """, [today])

            dup_rows = cur.fetchall()
            if dup_rows:
                print(f"  Found {len(dup_rows)} duplicate idempotency_keys:")
                for key, count in dup_rows:
                    print(f"    {count}x: {key[:20]}...")
            else:
                print("  No duplicate idempotency_keys found")

            return False
        else:
            print("✅ PASS: No UniqueViolation errors found")
            return True


def check_entry_execution():
    """Verify entry execution is working (check for actual trades)."""
    from utils.db import DatabaseContext

    et = ZoneInfo("America/New_York")
    today = datetime.now(et).date()

    print("\n" + "="*70)
    print("BONUS: Entry Execution Verification")
    print("="*70)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status IN ('open', 'filled', 'partially_filled') THEN 1 ELSE 0 END) as active
            FROM algo_trades
            WHERE trade_date = %s
        """, [today])

        row = cur.fetchone()
        total, active = row[0], row[1] or 0

        if total == 0:
            print(f"⚠️  WARNING: No trades executed today (total={total})")
            return True  # Not a failure, just unusual

        print(f"✅ Trades executed: {total} total, {active} active")
        return True


def check_exit_execution():
    """Verify exit execution is working (check for exit orders)."""
    from utils.db import DatabaseContext

    et = ZoneInfo("America/New_York")
    today = datetime.now(et).date()

    print("\n" + "="*70)
    print("BONUS: Exit Execution Verification")
    print("="*70)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN exit_reason IS NOT NULL THEN 1 ELSE 0 END) as exited
            FROM algo_trades
            WHERE trade_date = %s
        """, [today])

        row = cur.fetchone()
        total, exited = row[0], row[1] or 0

        if total > 0 and exited == 0:
            print(f"⚠️  WARNING: {total} trades but 0 exits (unusual but not necessarily an error)")
            return True

        if total > 0:
            exit_rate = exited / total * 100
            print(f"✅ Exit execution: {exited}/{total} trades exited ({exit_rate:.1f}%)")

        return True


def check_concentration_enforcement():
    """Verify concentration checks are enforcing position limits."""
    from utils.db import DatabaseContext

    et = ZoneInfo("America/New_York")
    today = datetime.now(et).date()

    print("\n" + "="*70)
    print("BONUS: Concentration Limit Enforcement")
    print("="*70)

    with DatabaseContext("read") as cur:
        # Check for position rejections due to concentration
        cur.execute("""
            SELECT rejection_reason, COUNT(*) as count
            FROM filter_rejection_log
            WHERE eval_date = %s
            AND rejection_reason ILIKE '%concentration%'
            GROUP BY rejection_reason
            ORDER BY count DESC
            LIMIT 3
        """, [today])

        rows = cur.fetchall()
        if rows:
            total_concentration_rejections = sum(r[1] for r in rows)
            print(f"ℹ️  {total_concentration_rejections} signals rejected for concentration limits:")
            for reason, count in rows[:3]:
                print(f"  {count}x: {reason[:80]}")
        else:
            print("ℹ️  No concentration-based rejections found (market may not be at risk thresholds)")

        return True


def main():
    """Run all verification checks."""
    print("\n" + "="*70)
    print("SESSION 63 ORCHESTRATOR FIX VERIFICATION")
    print("="*70)

    checks = [
        ("Orchestrator Execution", check_orchestrator_execution),
        ("Decimal/float TypeError", check_decimal_float_errors),
        ("position_id NameError", check_position_id_errors),
        ("UniqueViolation", check_unique_violation_errors),
        ("Entry Execution", check_entry_execution),
        ("Exit Execution", check_exit_execution),
        ("Concentration Enforcement", check_concentration_enforcement),
    ]

    results = []
    for name, check_fn in checks:
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            print(f"❌ ERROR running {name}: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    critical_passed = all(r[1] for r in results[:4])

    for name, result in results:
        icon = "✅" if result else "❌"
        print(f"{icon} {name}")

    print("\n" + "="*70)
    if critical_passed:
        print("✅ ALL CRITICAL CHECKS PASSED - System appears healthy!")
        print("="*70)
        return 0
    else:
        print("❌ CRITICAL CHECKS FAILED - Issues detected, review above")
        print("="*70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
