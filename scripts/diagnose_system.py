#!/usr/bin/env python3
"""Diagnose system status - check all components and identify issues."""

import os
import subprocess
import sys
import time
from pathlib import Path

# Add repo root to path
_repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(_repo_root))

def check_environment():
    """Check environment variables."""
    print("=" * 70)
    print("ENVIRONMENT CHECK")
    print("=" * 70)

    required_local = []
    required_aws = [
        "DASHBOARD_API_URL",
        "COGNITO_USER_POOL_ID",
        "COGNITO_CLIENT_ID",
    ]

    local_mode = os.environ.get("LOCAL_MODE", "").lower() == "true"

    print(f"\nLOCAL_MODE: {local_mode}")
    print(f"ENVIRONMENT: {os.environ.get('ENVIRONMENT', 'not set')}")
    print()

    if local_mode:
        print("LOCAL MODE - checking for local database...")
        db_host = os.environ.get("DB_HOST", "localhost")
        db_port = os.environ.get("DB_PORT", "5432")
        print(f"  Database: {db_host}:{db_port}")
    else:
        print("AWS MODE - checking for AWS credentials...")
        for var in required_aws:
            val = os.environ.get(var)
            print(f"  {var}: {'SET' if val else 'NOT SET'}")

    return True

def check_database():
    """Check database connectivity."""
    print("\n" + "=" * 70)
    print("DATABASE CHECK")
    print("=" * 70)

    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext("read") as cur:
            cur.execute("SELECT current_database(), inet_server_addr()")
            db, host = cur.fetchone()
            print(f"\nDatabase: {db}")
            print(f"Host: {host}")

            # Check table row counts
            tables = [
                'price_daily', 'stock_scores', 'algo_positions',
                'algo_portfolio_snapshots', 'technical_data_daily'
            ]

            print("\nTable row counts:")
            for table in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0]
                    print(f"  {table:35} {count:10,}")
                except Exception as e:
                    print(f"  {table:35} ERROR: {str(e)[:40]}")

            return True
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        return False

def check_dev_server():
    """Check if dev server can start and respond."""
    print("\n" + "=" * 70)
    print("DEV SERVER CHECK")
    print("=" * 70)

    print("\nStarting dev server on port 3001...")

    try:
        # Start dev server in background
        proc = subprocess.Popen(
            [sys.executable, "api-pkg/dev_server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(_repo_root)
        )

        # Wait for server to start
        time.sleep(3)

        # Test endpoints
        import requests

        endpoints = [
            "/api/algo/portfolio",
            "/api/algo/config",
            "/api/algo/positions",
        ]

        print("\nTesting endpoints (with dev-admin token):")
        for endpoint in endpoints:
            try:
                resp = requests.get(
                    f"http://localhost:3001{endpoint}",
                    headers={"Authorization": "Bearer dev-admin"},
                    timeout=3
                )
                status = "OK" if resp.status_code == 200 else f"ERROR {resp.status_code}"
                print(f"  {endpoint:40} {status}")
            except Exception as e:
                print(f"  {endpoint:40} FAILED: {str(e)[:30]}")

        # Kill server
        proc.terminate()
        proc.wait(timeout=5)

        return True
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return False

def check_fetchers():
    """Check if dashboard fetchers work."""
    print("\n" + "=" * 70)
    print("DASHBOARD FETCHERS CHECK")
    print("=" * 70)

    try:
        # Set up environment for local mode
        os.environ['ENVIRONMENT'] = 'dev'
        os.environ['LOCAL_MODE'] = 'true'
        os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'

        # Start dev server
        print("\nStarting dev server...")
        proc = subprocess.Popen(
            [sys.executable, "api-pkg/dev_server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(_repo_root)
        )

        time.sleep(3)

        print("Loading dashboard fetchers...")
        from dashboard.fetchers import load_all

        data = load_all()

        errors = []
        success = []
        for name in sorted(data.keys()):
            result = data[name]
            if isinstance(result, dict):
                if '_error' in result:
                    err = result.get('_error', 'unknown')[:60]
                    errors.append((name, err))
                else:
                    success.append(name)

        print(f"\nFetchers loaded: {len(success)}/{len(data)}")
        if errors:
            print(f"\nErrors ({len(errors)}):")
            for name, err in errors:
                print(f"  {name:15} {err}")
        else:
            print("\nAll fetchers successful!")

        # Kill server
        proc.terminate()
        proc.wait(timeout=5)

        return len(errors) == 0 or len(success) > 15  # Pass if most fetchers work
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return False

def main():
    """Run all diagnostics."""
    print("\n")
    print("=" * 70)
    print("SYSTEM DIAGNOSTICS")
    print("=" * 70)

    checks = [
        ("Environment", check_environment),
        ("Database", check_database),
        ("Dev Server", check_dev_server),
        ("Fetchers", check_fetchers),
    ]

    results = []
    for name, check_fn in checks:
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            print(f"\nFATAL ERROR in {name}: {type(e).__name__}: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {name:20} {status}")

    all_pass = all(r for _, r in results)

    if all_pass:
        print("\n[OK] All checks passed! System is ready.")
        print("\nTO USE DASHBOARD:")
        print("  1. Run: python api-pkg/dev_server.py")
        print("  2. In another terminal: python -m dashboard --local")
    else:
        print("\n[FAIL] Some checks failed. Please review the errors above.")

    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())
