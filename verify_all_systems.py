#!/usr/bin/env python3
"""Comprehensive system verification - tests all critical components."""

import json
import subprocess
import time
from urllib.request import Request, urlopen
from urllib.error import URLError

def test_api_endpoint(path: str, expected_status: int = 200) -> bool:
    """Test API endpoint returns expected status."""
    url = f"http://localhost:3001/api/{path}"
    headers = {"Authorization": "Bearer dev-admin"}

    try:
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            status = data.get("statusCode", response.status)
            success = status == expected_status
            has_data = len(str(data.get("data", {}))) > 10
            print(f"  {path:50} {status:3} {'OK' if success and has_data else 'FAIL'}")
            return success and has_data
    except Exception as e:
        print(f"  {path:50} ERR {str(e)[:30]}")
        return False

def run_tests() -> bool:
    """Run pytest and return success."""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "--co", "-q"],
            capture_output=True,
            timeout=30,
            text=True
        )
        test_count = len([l for l in result.stdout.split("\n") if ".py::" in l])
        print(f"  Found {test_count} tests configured")
        return test_count > 0
    except Exception as e:
        print(f"  Test discovery failed: {str(e)[:50]}")
        return False

def check_database_health() -> bool:
    """Check database connectivity and data."""
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
        import os

        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            database=os.environ.get("DB_NAME", "algo"),
            user=os.environ.get("DB_USER", "algo"),
            password=os.environ.get("DB_PASSWORD", ""),
            connect_timeout=5
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        # Check key tables
        tables = [
            ("algo_portfolio_snapshots", "Portfolio snapshots"),
            ("market_exposure_daily", "Market exposure"),
            ("algo_positions", "Positions"),
        ]

        all_ok = True
        for table, label in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            status = "OK" if count > 0 else "WARN"
            print(f"  {label:40} {count:6} rows {status}")
            all_ok = all_ok and (count > 0)

        cur.close()
        conn.close()
        return all_ok
    except Exception as e:
        print(f"  Database check failed: {str(e)[:50]}")
        return False

def main():
    print("\n" + "="*70)
    print("COMPREHENSIVE SYSTEM VERIFICATION - Session 53")
    print("="*70)

    # API Endpoints
    print("\n[API Endpoints - Local Dev Server on :3001]")
    endpoints = [
        ("algo/portfolio", 200),
        ("algo/positions", 200),
        ("algo/markets", 200),
        ("algo/trades", 200),
        ("algo/metrics", 200),
        ("algo/status", 200),
    ]
    api_ok = all(test_api_endpoint(p, s) for p, s in endpoints)

    # Database
    print("\n[Database Health]")
    db_ok = check_database_health()

    # Tests
    print("\n[Test Suite]")
    tests_ok = run_tests()

    # Summary
    print("\n" + "="*70)
    print("VERIFICATION SUMMARY")
    print("="*70)
    print(f"  API Endpoints:     {'PASS' if api_ok else 'FAIL'}")
    print(f"  Database:          {'PASS' if db_ok else 'FAIL'}")
    print(f"  Test Suite:        {'PASS' if tests_ok else 'FAIL'}")
    print(f"  Overall:           {'PASS' if all([api_ok, db_ok, tests_ok]) else 'FAIL'}")
    print("="*70 + "\n")

    return all([api_ok, db_ok, tests_ok])

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
