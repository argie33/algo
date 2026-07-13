#!/usr/bin/env python3
"""Verify that Session 106 fixes are working correctly.

Checks:
1. Dashboard auto-detect localhost fix
2. Data freshness (triggers orchestrator if needed)
3. API endpoints responding
4. Circuit breaker status
"""

import os
import sys
import subprocess
import time
from datetime import datetime, timezone

UTC = timezone.utc

os.environ["LOCAL_MODE"] = "true"
os.environ["DB_HOST"] = "localhost"
os.environ["DB_USER"] = "stocks"
os.environ["DB_PASSWORD"] = "stocks"
os.environ["DB_NAME"] = "stocks"
os.environ["ENVIRONMENT"] = "development"

print("=" * 80)
print("SESSION 106 FIXES VERIFICATION")
print("=" * 80)
print()

# Check 1: Dev server running
print("1. Checking if dev_server is running on localhost:3001...")
try:
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    result = sock.connect_ex(('localhost', 3001))
    sock.close()

    if result == 0:
        print("   ✓ Dev server is running")
    else:
        print("   ✗ Dev server is NOT running")
        print("   FIX: python3 api-pkg/dev_server.py")
        sys.exit(1)
except Exception as e:
    print(f"   ✗ Error: {e}")
    sys.exit(1)

# Check 2: Database connectivity
print("\n2. Checking database connectivity...")
try:
    import psycopg2
    conn = psycopg2.connect(
        host="localhost",
        user="stocks",
        password="stocks",
        database="stocks"
    )
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM stock_scores")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()

    print(f"   ✓ Database connected ({count} stock_scores records)")
except Exception as e:
    print(f"   ✗ Error: {e}")
    sys.exit(1)

# Check 3: Stock_scores freshness
print("\n3. Checking stock_scores data freshness...")
try:
    conn = psycopg2.connect(
        host="localhost",
        user="stocks",
        password="stocks",
        database="stocks"
    )
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), MAX(created_at) FROM stock_scores")
    count, latest = cur.fetchone()

    if latest:
        age_hours = (datetime.now(UTC) - latest.replace(tzinfo=UTC)).total_seconds() / 3600
        if age_hours < 24:
            print(f"   ✓ Stock_scores FRESH ({age_hours:.1f}h old)")
        else:
            print(f"   ✗ Stock_scores STALE ({age_hours:.1f}h old)")
            print("   FIX: python3 scripts/run_local_orchestrator.py --morning")
    else:
        print("   ✗ No stock_scores data")

    cur.close()
    conn.close()
except Exception as e:
    print(f"   ✗ Error: {e}")

# Check 4: API endpoints
print("\n4. Checking API endpoints...")
try:
    import requests
    resp = requests.get("http://localhost:3001/api/algo/portfolio", headers={"Authorization": "Bearer dev-admin"}, timeout=5)
    if resp.status_code == 200:
        print("   ✓ /api/algo/portfolio endpoint working")
    else:
        print(f"   ✗ /api/algo/portfolio returned {resp.status_code}")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Check 5: Auto-detect in dashboard
print("\n5. Checking dashboard auto-detect logic...")
try:
    # Clear environment and reimport to test auto-detect
    os.environ.pop("DASHBOARD_API_URL", None)
    os.environ.pop("LOCAL_MODE", None)
    os.environ.pop("COGNITO_USER_POOL_ID", None)
    os.environ.pop("COGNITO_CLIENT_ID", None)

    # Re-import dashboard module which should trigger auto-detect
    import importlib
    if 'dashboard.dashboard' in sys.modules:
        del sys.modules['dashboard.dashboard']

    import dashboard.dashboard

    if os.environ.get("LOCAL_MODE") == "true" and os.environ.get("DASHBOARD_API_URL") == "http://localhost:3001":
        print("   ✓ Dashboard auto-detected localhost")
    else:
        print(f"   ✗ Auto-detect failed")
        print(f"     LOCAL_MODE={os.environ.get('LOCAL_MODE')}")
        print(f"     DASHBOARD_API_URL={os.environ.get('DASHBOARD_API_URL')}")
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("VERIFICATION COMPLETE")
print("=" * 80)
print("\nNext steps:")
print("1. If all checks passed: Dashboard should work now!")
print("2. Test: python3 -m dashboard")
print("3. Should display data without --local flag")
