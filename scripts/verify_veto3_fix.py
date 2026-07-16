#!/usr/bin/env python3
"""Verify that the veto3 threshold fix is working correctly."""

import psycopg2
import sys
from datetime import datetime
from decimal import Decimal

def check_veto3_fix() -> bool:
    """Verify veto3 fix is deployed and working."""
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cur = conn.cursor()

        print("=" * 70)
        print("VETO3 THRESHOLD FIX VERIFICATION")
        print("=" * 70)
        print()

        # 1. Check config value
        cur.execute(
            "SELECT value FROM algo_config "
            "WHERE key = 'market_exposure_veto3_distribution_days_threshold'"
        )
        config_value = cur.fetchone()
        if config_value:
            config_threshold = int(config_value[0])
            print(f"✓ Config value: market_exposure_veto3_distribution_days_threshold = {config_threshold}")
            if config_threshold != 9:
                print(f"  WARNING: Expected 9, got {config_threshold}")
        else:
            print("✗ Config value not found!")
            return False
        print()

        # 2. Check latest orchestrator runs
        print("Recent Orchestrator Runs:")
        cur.execute(
            """
            SELECT run_id, started_at, overall_status, halt_reason
            FROM algo_orchestrator_runs
            ORDER BY started_at DESC
            LIMIT 5
            """
        )
        runs = cur.fetchall()
        for run in runs:
            run_id, started_at, status, halt_reason = run
            halt_msg = f" | Halt: {halt_reason[:40]}" if halt_reason else ""
            print(f"  {run_id:40} | {status:10}{halt_msg}")

        # Check if new runs show correct threshold in halt message
        if runs and "selling-pressure days >=" in (runs[0][3] or ""):
            halt_str = runs[0][3]
            if ">= 9" in halt_str:
                print(f"\n✓ NEW threshold detected in latest run: {halt_str}")
            elif ">= 6" in halt_str:
                print(f"\n✗ OLD threshold still in use: {halt_str}")
                print("  FIX NOT YET DEPLOYED - ECS image may not have been updated")
                return False
        print()

        # 3. Check if trades are being executed
        cur.execute("SELECT COUNT(*) FROM algo_trades WHERE entry_date >= CURRENT_DATE - 1")
        recent_trades = cur.fetchone()[0]
        print(f"Recent Trades (last 2 days): {recent_trades}")
        if recent_trades > 0:
            print("✓ Trades are being executed (fix working!)")
        else:
            print("✗ No recent trades - may still be halted by other reasons")
            # Check what's halting the most recent runs
            cur.execute(
                """
                SELECT overall_status, COUNT(*)
                FROM algo_orchestrator_runs
                WHERE started_at >= NOW() - INTERVAL '6 hours'
                GROUP BY overall_status
                ORDER BY COUNT(*) DESC
                """
            )
            statuses = cur.fetchall()
            print("\n  Recent run statuses:")
            for status, count in statuses:
                print(f"    {status:15} {count:3} runs")
        print()

        # 4. Check signal generation
        cur.execute(
            "SELECT COUNT(*) FROM algo_signals WHERE signal_date >= CURRENT_DATE - 1"
        )
        recent_signals = cur.fetchone()[0]
        print(f"Recent Signals (last 2 days): {recent_signals}")
        print()

        cur.close()
        conn.close()

        print("=" * 70)
        print("SUMMARY:")
        if recent_trades > 0:
            print("✓ VETO3 FIX IS WORKING - Trades are executing")
            return True
        else:
            print("⚠ VETO3 FIX DEPLOYED - But need to check why trades not executing")
            print("  Possible causes:")
            print("  1. ECS image not yet updated (check deployment status)")
            print("  2. Different halt reason blocking trades")
            print("  3. No signals generated")
            return False

    except Exception as e:
        print(f"Error during verification: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    success = check_veto3_fix()
    sys.exit(0 if success else 1)
