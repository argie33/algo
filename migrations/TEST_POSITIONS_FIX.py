#!/usr/bin/env python3
"""
Complete end-to-end test for positions view fix.

Run this BEFORE and AFTER AWS deployment to verify the fix is working.

Usage:
  # Test local database
  python TEST_POSITIONS_FIX.py

  # Test AWS production (after deployment)
  export DASHBOARD_API_URL="https://your-api-endpoint"
  export COGNITO_USER_POOL_ID="your-pool-id"
  export COGNITO_CLIENT_ID="your-client-id"
  python TEST_POSITIONS_FIX.py
"""

import os
import sys
import json

sys.path.insert(0, os.getcwd())

def test_database_view():
    """Test 1: Database materialized view exists and has data"""
    print("\n" + "=" * 80)
    print("TEST 1: Database Materialized View")
    print("=" * 80)

    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN status = 'open' THEN 1 END) as open_count,
                       array_agg(DISTINCT symbol ORDER BY symbol) as symbols
                FROM algo_positions_with_risk
            """)

            result = cur.fetchone()
            if not result:
                print("FAIL: View query returned no results")
                return False

            total, open_count, symbols = result

            print(f"Total positions: {total}")
            print(f"Open positions: {open_count}")
            print(f"Symbols: {', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''}")

            if open_count >= 10 and total >= 10:
                print("\n[PASS] View has all required positions")
                return True
            else:
                print(f"\n[FAIL] Expected 10+ positions, got {open_count}")
                return False

    except Exception as e:
        print(f"[FAIL] {type(e).__name__}: {e}")
        return False


def test_positions_api():
    """Test 2: Positions API endpoint returns correct data"""
    print("\n" + "=" * 80)
    print("TEST 2: Positions API Endpoint")
    print("=" * 80)

    try:
        os.environ.setdefault("DASHBOARD_API_URL", "http://localhost:8000")
        os.environ.setdefault("COGNITO_USER_POOL_ID", "test")
        os.environ.setdefault("COGNITO_CLIENT_ID", "test")

        # Clear any cache
        try:
            from dashboard import api_data_layer
            api_data_layer._response_cache.clear()
        except:
            pass

        from dashboard.api_data_layer import api_call

        print(f"API URL: {os.environ.get('DASHBOARD_API_URL')}")
        print("\nCalling /api/algo/positions...")

        response = api_call("/api/algo/positions")

        items = response.get('items', [])
        coverage = response.get('coverage', {})
        stale_alerts = response.get('stale_alerts', [])

        print(f"Items returned: {len(items)}")
        print(f"Coverage: {coverage.get('valid_count', 0)}/{coverage.get('total_count', 0)} ({coverage.get('coverage_pct', 0):.1f}%)")

        if stale_alerts:
            print(f"Stale alerts: {', '.join(stale_alerts)}")

        if len(items) >= 10:
            print(f"\n✓ PASS: API returns all {len(items)} positions")
            print("First 3 positions:")
            for item in items[:3]:
                print(f"  - {item.get('symbol'):10} | ${item.get('position_value'):10.2f}")
            return True
        else:
            print(f"\n✗ FAIL: Expected 10+ positions, got {len(items)}")
            if items:
                print("Returned positions:")
                for item in items:
                    print(f"  - {item.get('symbol')}")
            return False

    except Exception as e:
        print(f"✗ FAIL: {type(e).__name__}: {e}")
        return False


def test_dashboard_credentials():
    """Test 3: Dashboard.py AWS mode credential validation"""
    print("\n" + "=" * 80)
    print("TEST 3: Dashboard.py AWS Mode Credentials")
    print("=" * 80)

    try:
        from dashboard.dashboard import (
            _fetch_and_validate_aws_credentials,
            _validate_api_url,
        )

        # Test with valid credentials
        os.environ["DASHBOARD_API_URL"] = "https://api.example.com"
        os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_test"
        os.environ["COGNITO_CLIENT_ID"] = "test-client"

        url, pool_id, client_id = _fetch_and_validate_aws_credentials()

        print("Credentials extracted:")
        print(f"  - URL: {url}")
        print(f"  - Pool: {pool_id}")
        print(f"  - Client: {client_id}")

        url_valid = _validate_api_url(url)
        print(f"  - URL valid: {url_valid}")

        # Test missing credentials detection
        for var in ["DASHBOARD_API_URL", "COGNITO_USER_POOL_ID", "COGNITO_CLIENT_ID"]:
            os.environ.pop(var, None)

        missing_detected = False
        try:
            url, pool_id, client_id = _fetch_and_validate_aws_credentials()
        except SystemExit:
            missing_detected = True

        print(f"Missing credentials detected: {missing_detected}")

        if url_valid and missing_detected:
            print("\n✓ PASS: AWS mode validation working correctly")
            return True
        else:
            print("\n✗ FAIL: Credential validation incomplete")
            return False

    except Exception as e:
        print(f"✗ FAIL: {type(e).__name__}: {e}")
        return False


def test_memory_system():
    """Test 4: Memory system properly organized"""
    print("\n" + "=" * 80)
    print("TEST 4: Memory System")
    print("=" * 80)

    try:
        memory_file = os.path.expanduser("~/.claude/projects/C--Users-arger-code-algo/memory/MEMORY.md")

        if not os.path.exists(memory_file):
            print(f"✗ FAIL: MEMORY.md not found at {memory_file}")
            return False

        with open(memory_file, 'r') as f:
            content = f.read()

        checks = {
            "CRITICAL BLOCKERS": "CRITICAL BLOCKERS" in content,
            "EVERGREEN patterns": "EVERGREEN" in content,
            "ARCHIVE section": "ARCHIVE" in content,
            "Infrastructure blocker": "Infrastructure Failure" in content,
            "Positions API fix": "Positions API" in content,
        }

        all_passed = True
        for check, result in checks.items():
            status = "✓" if result else "✗"
            print(f"  {status} {check}")
            all_passed = all_passed and result

        if all_passed:
            print("\n✓ PASS: Memory system properly organized")
            return True
        else:
            print("\n✗ FAIL: Memory system incomplete")
            return False

    except Exception as e:
        print(f"✗ FAIL: {type(e).__name__}: {e}")
        return False


def main():
    print("\n" + "=" * 80)
    print("POSITIONS FIX - COMPREHENSIVE TEST SUITE")
    print("=" * 80)

    results = {
        "Database View": test_database_view(),
        "Positions API": test_positions_api(),
        "Dashboard Credentials": test_dashboard_credentials(),
        "Memory System": test_memory_system(),
    }

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        print(f"  {symbol} {test_name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ ALL TESTS PASSED - System is working correctly!")
        print("\nIf testing against local database:")
        print("  - Positions view is ready")
        print("  - Dashboard API is working")
        print("  - AWS mode code is validated")
        print("\nNext: Deploy to AWS RDS using DEPLOY_POSITIONS_FIX.ps1")
        return 0
    else:
        print(f"\n✗ {total - passed} TEST(S) FAILED")
        print("\nDebugging tips:")
        print("  - Check database connection")
        print("  - Verify migration 999 is applied")
        print("  - Check API endpoint accessibility")
        return 1


if __name__ == "__main__":
    sys.exit(main())
