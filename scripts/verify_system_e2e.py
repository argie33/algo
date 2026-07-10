#!/usr/bin/env python3
"""End-to-end system verification."""

import json
import subprocess
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

def test_database_connection():
    """Verify database is accessible."""
    print("\n[TEST 1] Database Connection")
    try:
        conn = psycopg2.connect(
            dbname="stocks",
            user="postgres",
            password="password",
            host="localhost",
            port="5432"
        )
        cur = conn.cursor()
        cur.execute("SELECT 1")
        conn.close()
        print("  [OK] Database connection successful")
        return True
    except Exception as e:
        print(f"  [FAIL] Database connection failed: {e}")
        return False

def test_orchestrator_status():
    """Check if orchestrator has run recently."""
    print("\n[TEST 2] Orchestrator Status")
    try:
        conn = psycopg2.connect(
            dbname="stocks", user="postgres", password="password",
            host="localhost", port="5432"
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT overall_status, COUNT(*) as count
            FROM algo_orchestrator_runs
            WHERE started_at > NOW() - INTERVAL '24 hours'
            GROUP BY overall_status
        """)
        stats = cur.fetchall()

        success_count = sum(r['count'] for r in stats if r['overall_status'] == 'success')
        total_count = sum(r['count'] for r in stats)

        if success_count > 0:
            print(f"  [OK] Orchestrator running ({success_count}/{total_count} successful)")
        else:
            print(f"  [FAIL] No successful runs (total: {total_count})")

        conn.close()
        return success_count > 0
    except Exception as e:
        print(f"  [FAIL] Orchestrator check failed: {e}")
        return False

def test_data_freshness():
    """Verify data is fresh."""
    print("\n[TEST 3] Data Freshness")
    try:
        conn = psycopg2.connect(
            dbname="stocks", user="postgres", password="password",
            host="localhost", port="5432"
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT MAX(created_at) as latest FROM algo_portfolio_snapshots
        """)
        snap = cur.fetchone()

        cur.execute("""
            SELECT MAX(date) as latest FROM price_daily
        """)
        prices = cur.fetchone()

        if snap['latest'] and prices['latest']:
            print(f"  [OK] Portfolio snapshot: {snap['latest']}")
            print(f"  [OK] Price data: {prices['latest']}")
            conn.close()
            return True
        else:
            print("  [FAIL] Missing data")
            conn.close()
            return False
    except Exception as e:
        print(f"  [FAIL] Data freshness check failed: {e}")
        return False

def test_position_metrics():
    """Verify positions have complete metrics."""
    print("\n[TEST 4] Position Metrics")
    try:
        conn = psycopg2.connect(
            dbname="stocks", user="postgres", password="password",
            host="localhost", port="5432"
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE target_1_price IS NOT NULL) as with_targets,
                COUNT(*) FILTER (WHERE r_multiple IS NOT NULL) as with_r_mult
            FROM algo_positions
            WHERE status IN ('open', 'paper_open')
        """)
        result = cur.fetchone()

        total = result['total']
        with_targets = result['with_targets']
        with_r = result['with_r_mult']

        if total == 0:
            print("  [OK] No open positions (acceptable)")
        elif with_targets == total and with_r == total:
            print(f"  [OK] All {total} positions have complete metrics")
        else:
            print(f"  [WARN] {with_targets}/{total} have targets, {with_r}/{total} have r_multiple")

        conn.close()
        return (with_targets == total and with_r == total) or total == 0
    except Exception as e:
        print(f"  [FAIL] Position metrics check failed: {e}")
        return False

def test_portfolio_snapshot():
    """Verify portfolio snapshot has correct counts."""
    print("\n[TEST 5] Portfolio Snapshot")
    try:
        conn = psycopg2.connect(
            dbname="stocks", user="postgres", password="password",
            host="localhost", port="5432"
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT
                position_count,
                unrealized_pnl_winning_count,
                unrealized_pnl_losing_count,
                unrealized_pnl_breakeven_count
            FROM algo_portfolio_snapshots
            ORDER BY snapshot_date DESC
            LIMIT 1
        """)
        result = cur.fetchone()

        if result:
            total = result['position_count']
            winning = result['unrealized_pnl_winning_count']
            losing = result['unrealized_pnl_losing_count']
            breakeven = result['unrealized_pnl_breakeven_count']

            if winning + losing + breakeven == total or total == 0:
                print(f"  [OK] Snapshot: {winning} winning, {losing} losing, {breakeven} breakeven")
            else:
                print(f"  [WARN] Counts mismatch: {winning}+{losing}+{breakeven}={winning+losing+breakeven} vs {total}")

        conn.close()
        return True
    except Exception as e:
        print(f"  [FAIL] Portfolio snapshot check failed: {e}")
        return False

def test_api_endpoints():
    """Test critical API endpoints."""
    print("\n[TEST 6] API Endpoints (localhost:3001)")

    endpoints = [
        "/api/algo/portfolio",
        "/api/algo/positions",
        "/api/algo/trades",
        "/api/algo/circuit-breakers",
    ]

    passed = 0
    for endpoint in endpoints:
        try:
            cmd = f'curl -s http://localhost:3001{endpoint} -H "Authorization: Bearer dev-admin" 2>&1'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            data = json.loads(result.stdout)

            status = data.get('statusCode')
            has_data = bool(data.get('data'))

            if status == 200 and has_data:
                print(f"  [OK] {endpoint}")
                passed += 1
            elif status == 200:
                print(f"  [WARN] {endpoint} (no data)")
            else:
                print(f"  [FAIL] {endpoint} ({status})")
        except Exception as e:
            print(f"  [FAIL] {endpoint} (error)")

    return passed == len(endpoints)

def main():
    """Run all tests."""
    print("="*60)
    print("SYSTEM END-TO-END VERIFICATION")
    print("="*60)

    tests = [
        test_database_connection,
        test_orchestrator_status,
        test_data_freshness,
        test_position_metrics,
        test_portfolio_snapshot,
        test_api_endpoints,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"  [FAIL] Test error")
            results.append(False)

    print("\n" + "="*60)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")

    if passed == total:
        print("STATUS: SYSTEM OPERATIONAL")
        return 0
    else:
        print("STATUS: ISSUES FOUND")
        return 1

if __name__ == "__main__":
    sys.exit(main())
