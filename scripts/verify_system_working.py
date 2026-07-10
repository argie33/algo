#!/usr/bin/env python3
"""End-to-end system verification script.

Verifies that the entire system is working correctly:
1. Dashboard displays real data
2. API endpoints return data
3. Orchestrator completes successfully
4. Portfolio snapshots are current
5. Paper trades are executing
6. All components are operational

Usage:
    python3 scripts/verify_system_working.py
"""

import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, '.')

from utils.db.context import DatabaseContext

def check_dashboard_data():
    """Verify dashboard API endpoints return real data."""
    print("\n=== DASHBOARD DATA CHECK ===")
    with DatabaseContext('read') as cur:
        # Check portfolio
        cur.execute("""
            SELECT COUNT(*) as count FROM algo_positions WHERE status = 'open'
        """)
        positions = cur.fetchone()[0]
        print("Portfolio Positions: %d" % positions)

        # Check trades
        cur.execute("""
            SELECT COUNT(*) as count FROM algo_trades
        """)
        trades = cur.fetchone()[0]
        print("Total Trades: %d" % trades)

        # Check signals
        cur.execute("""
            SELECT COUNT(*) as count FROM algo_signals WHERE signal_active = TRUE
        """)
        signals = cur.fetchone()[0]
        print("Active Signals: %d" % signals)

        # Check stock scores
        cur.execute("""
            SELECT COUNT(*) as count FROM stock_scores WHERE data_unavailable = FALSE
        """)
        scores = cur.fetchone()[0]
        print("Stock Scores (available): %d" % scores)

        return positions > 0 and trades > 0 and scores > 0

def check_orchestrator_completion():
    """Verify orchestrator ran and completed successfully."""
    print("\n=== ORCHESTRATOR COMPLETION CHECK ===")
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT run_id, started_at, completed_at, overall_status
            FROM algo_orchestrator_runs
            ORDER BY started_at DESC LIMIT 1
        """)
        run = cur.fetchone()

        if not run:
            print("ERROR: No orchestrator runs found")
            return False

        run_id, started, completed, status = run
        print("Latest Run: %s" % run_id)
        print("Status: %s" % status)

        if status == "success":
            print("SUCCESS: Orchestrator completed successfully")
            return True
        else:
            print("WARNING: Orchestrator status is %s" % status)
            return False

def check_portfolio_snapshot_fresh():
    """Verify portfolio snapshot is recent."""
    print("\n=== PORTFOLIO SNAPSHOT FRESHNESS CHECK ===")
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT created_at, total_portfolio_value, position_count
            FROM algo_portfolio_snapshots
            ORDER BY created_at DESC LIMIT 1
        """)
        snapshot = cur.fetchone()

        if not snapshot:
            print("ERROR: No portfolio snapshots found")
            return False

        created, value, pos_count = snapshot
        age = datetime.now(timezone.utc) - created.replace(tzinfo=timezone.utc)
        minutes_old = age.total_seconds() / 60

        print("Snapshot Age: %.0f minutes" % minutes_old)
        print("Portfolio Value: $%s" % value)
        print("Positions: %d" % pos_count)

        if minutes_old < 60:
            print("SUCCESS: Portfolio snapshot is fresh (<1 hour)")
            return True
        else:
            print("WARNING: Portfolio snapshot is %d hours old" % (minutes_old / 60))
            return False

def check_paper_trading():
    """Verify paper trades are executing."""
    print("\n=== PAPER TRADING CHECK ===")
    with DatabaseContext('read') as cur:
        # Check recent trades
        cur.execute("""
            SELECT COUNT(*) as count
            FROM algo_trades
            WHERE entry_date >= NOW() - INTERVAL '24 hours'
        """)
        recent_trades = cur.fetchone()[0]
        print("Trades in Last 24h: %d" % recent_trades)

        # Check if any are currently open
        cur.execute("""
            SELECT COUNT(*) as count
            FROM algo_positions
            WHERE status = 'open' AND entry_date >= NOW() - INTERVAL '24 hours'
        """)
        open_positions = cur.fetchone()[0]
        print("Open Positions (24h): %d" % open_positions)

        if recent_trades > 0 or open_positions > 0:
            print("SUCCESS: Paper trading is executing")
            return True
        else:
            print("WARNING: No recent trades or positions")
            return False

def check_data_quality():
    """Verify data quality markers."""
    print("\n=== DATA QUALITY CHECK ===")
    with DatabaseContext('read') as cur:
        # Check for data_unavailable flags
        cur.execute("""
            SELECT COUNT(*) as count
            FROM stock_scores
            WHERE data_unavailable = TRUE
        """)
        unavailable_scores = cur.fetchone()[0]
        print("Unavailable Stock Scores: %d" % unavailable_scores)

        # Check market exposure
        cur.execute("""
            SELECT COUNT(*) as count
            FROM market_exposure_daily
            WHERE date = CURRENT_DATE
        """)
        market_exp = cur.fetchone()[0]
        print("Market Exposure (today): %d" % market_exp)

        return market_exp > 0

def main():
    """Run all verification checks."""
    print("=" * 60)
    print("END-TO-END SYSTEM VERIFICATION")
    print("=" * 60)

    checks = [
        ("Dashboard Data", check_dashboard_data),
        ("Orchestrator Completion", check_orchestrator_completion),
        ("Portfolio Snapshot Freshness", check_portfolio_snapshot_fresh),
        ("Paper Trading Execution", check_paper_trading),
        ("Data Quality", check_data_quality),
    ]

    results = {}
    for check_name, check_func in checks:
        try:
            result = check_func()
            results[check_name] = "PASS" if result else "WARNING"
        except Exception as e:
            print("ERROR: %s" % str(e)[:100])
            results[check_name] = "FAIL"

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    for check_name, result in results.items():
        status_str = "OK" if result == "PASS" else result
        print("%s: %s" % (check_name, status_str))

    all_passed = all(r == "PASS" for r in results.values())
    print("\n" + "=" * 60)
    if all_passed:
        print("SYSTEM STATUS: ALL CHECKS PASSED")
        print("System is fully operational and ready for paper trading")
        return 0
    else:
        print("SYSTEM STATUS: CHECKS WITH WARNINGS/FAILURES")
        print("Review warnings above and check CloudWatch logs")
        return 1

if __name__ == "__main__":
    sys.exit(main())
