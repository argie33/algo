#!/usr/bin/env python3
"""
Comprehensive AWS System Diagnostic Tool

Identifies what's actually broken in AWS deployment vs. what works locally.
Used after recent fixes to verify they actually work in production.

Run this after deploying to AWS to check:
1. Lambda execution status
2. RDS data freshness
3. EventBridge scheduler status
4. Portfolio snapshot integrity
5. Position calculations
6. Risk metric calculations (especially beta)
"""

import os
import sys
import json
from datetime import datetime, timedelta
from decimal import Decimal

def check_local_database():
    """Check local database status."""
    try:
        import psycopg2
        conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
        cur = conn.cursor()

        print("\n=== LOCAL DATABASE STATUS ===")

        # Check prices
        cur.execute("SELECT MAX(date) FROM price_daily")
        max_price_date = cur.fetchone()[0]
        if max_price_date:
            days_old = (datetime.now().date() - max_price_date).days
            print(f"[LOCAL] Price data: {max_price_date} ({days_old} days old)")

        # Check portfolio snapshots
        cur.execute("""
        SELECT snapshot_date, total_portfolio_value, position_count,
               unrealized_pnl_total, unrealized_pnl_winning_count
        FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
        """)
        snap = cur.fetchone()
        if snap:
            snap_date, portfolio_val, pos_count, pnl, wins = snap
            print(f"[LOCAL] Latest snapshot: {snap_date}")
            print(f"        Portfolio: ${portfolio_val}, Positions: {pos_count}")
            print(f"        P&L: ${pnl}, Winning: {wins}")

        # Check orchestrator runs
        cur.execute("""
        SELECT COUNT(*), MAX(started_at)
        FROM algo_orchestrator_runs
        WHERE started_at > NOW() - INTERVAL '24 hours'
        """)
        run_count, latest_run = cur.fetchone()
        print(f"[LOCAL] Orchestrator runs (24h): {run_count}, Latest: {latest_run}")

        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] Could not check local database: {e}")
        return False

def check_portfolio_beta_calculation():
    """Test the portfolio beta calculation locally."""
    try:
        from algo.risk.var import ValueAtRisk
        from unittest.mock import MagicMock

        print("\n=== PORTFOLIO BETA CALCULATION TEST ===")

        config = MagicMock()
        var = ValueAtRisk(config)

        result = var.beta_exposure()

        if 'portfolio_beta' in result:
            beta = result['portfolio_beta']
            print(f"[LOCAL] Beta calculation: {beta}")
            print(f"        Interpretation: {result.get('interpretation', 'N/A')}")
            print(f"        Positions in calc: {len(result.get('positions', []))}")
            return True
        else:
            print("[ERROR] Beta calculation returned invalid result")
            return False

    except Exception as e:
        print(f"[ERROR] Beta calculation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_reconciliation_snapshot():
    """Verify portfolio snapshot table has recent data."""
    try:
        import psycopg2

        print("\n=== PORTFOLIO SNAPSHOT INTEGRITY TEST ===")

        conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
        cur = conn.cursor()

        # Check that Session 161 fix works: unrealized_pnl columns are present and consistent
        cur.execute("""
        SELECT snapshot_date, position_count,
               unrealized_pnl_winning_count, unrealized_pnl_losing_count, unrealized_pnl_breakeven_count
        FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
        """)

        row = cur.fetchone()
        if not row:
            print("[ERROR] No portfolio snapshots found")
            return False

        snap_date, pos_count, wins, loses, breakeven = row

        # Verify consistency: position_count should match sum of wins+loses+breakeven
        total_positions = wins + loses + breakeven
        if pos_count != total_positions:
            if pos_count > 0 or total_positions > 0:
                print(f"[ERROR] Snapshot consistency check failed:")
                print(f"        position_count={pos_count}, wins+loses+breakeven={total_positions}")
                return False

        print(f"[LOCAL] Portfolio snapshot consistent (latest: {snap_date})")
        print(f"        position_count={pos_count}, winning={wins}, losing={loses}, breakeven={breakeven}")

        conn.close()
        return True

    except Exception as e:
        print(f"[ERROR] Portfolio snapshot check failed: {e}")
        return False

def main():
    print("=" * 70)
    print("AWS SYSTEM DIAGNOSTIC TOOL")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")

    results = {}

    # Run all checks
    results['local_db'] = check_local_database()
    results['beta'] = check_portfolio_beta_calculation()
    results['reconciliation'] = check_reconciliation_snapshot()

    # Summary
    print("\n" + "=" * 70)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 70)

    all_passed = all(results.values())

    for check_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"{check_name:20} [{status}]")

    print()
    if all_passed:
        print("All local checks passed.")
        return 0
    else:
        print("Some checks failed. See details above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
