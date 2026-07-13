#!/usr/bin/env python3
"""Comprehensive system test."""
import sys
import os

print("="*70)
print("COMPREHENSIVE SYSTEM TEST")
print("="*70)

# Test 1: Python environment
print("\n[TEST 1] Python environment...")
print(f"  Python: {sys.version.split()[0]}")
print(f"  Platform: {sys.platform}")

# Test 2: Database connectivity
print("\n[TEST 2] Database connectivity...")
try:
    import psycopg2
    conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM stock_prices_daily LIMIT 1")
    count = cursor.fetchone()[0]
    print(f"  OK - {count} price records")
    conn.close()
except Exception as e:
    print(f"  ERROR: {str(e)[:60]}")

# Test 3: AWS credentials
print("\n[TEST 3] AWS credentials...")
api_url = os.environ.get("DASHBOARD_API_URL")
pool_id = os.environ.get("COGNITO_USER_POOL_ID")
client_id = os.environ.get("COGNITO_CLIENT_ID")
username = os.environ.get("COGNITO_USERNAME")
password = os.environ.get("COGNITO_PASSWORD")
print(f"  API URL: {'SET' if api_url else 'NOT SET'}")
print(f"  Pool ID: {'SET' if pool_id else 'NOT SET'}")
print(f"  Client ID: {'SET' if client_id else 'NOT SET'}")
print(f"  Username: {'SET' if username else 'NOT SET'}")
print(f"  Password: {'SET' if password else 'NOT SET'}")

# Test 4: Cognito authentication
print("\n[TEST 4] Cognito authentication...")
try:
    from dashboard.cognito_auth import get_cognito_auth
    auth = get_cognito_auth(require_auth=True)
    if auth and hasattr(auth, "access_token") and auth.access_token:
        print(f"  OK - Token acquired ({len(auth.access_token)} chars)")
    else:
        print(f"  ERROR: {auth}")
except Exception as e:
    print(f"  ERROR: {str(e)[:60]}")

# Test 5: API connectivity
print("\n[TEST 5] API connectivity...")
try:
    from dashboard.api_data_layer import api_call, _get_api_base_url
    from dashboard.cognito_auth import get_cognito_auth
    from dashboard.api_data_layer import set_cognito_auth

    url = _get_api_base_url()
    print(f"  URL: {url[:50]}...")

    auth = get_cognito_auth(require_auth=True)
    if auth and hasattr(auth, "access_token"):
        set_cognito_auth(auth)

    result = api_call("/api/algo/status")
    if "_error" in result:
        print(f"  ERROR: {result['_error'][:60]}")
    else:
        print(f"  OK - API responded with {len(result)} keys")
except Exception as e:
    print(f"  ERROR: {str(e)[:60]}")

# Test 6: Dashboard module
print("\n[TEST 6] Dashboard module...")
try:
    from dashboard.dashboard import main
    print(f"  OK - Dashboard imports successfully")
except Exception as e:
    print(f"  ERROR: {str(e)[:60]}")

# Test 7: run_dashboard.py script
print("\n[TEST 7] run_dashboard.py script...")
try:
    with open("run_dashboard.py", "r") as f:
        content = f.read()
    if "from dashboard.dashboard import main" in content:
        print(f"  OK - Script is correctly configured")
    else:
        print(f"  ERROR: Script missing required imports")
except Exception as e:
    print(f"  ERROR: {str(e)[:60]}")

# Test 8: Local dev server
print("\n[TEST 8] Local dev server check...")
try:
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(("127.0.0.1", 3001))
    sock.close()
    if result == 0:
        print(f"  OK - Dev server running on localhost:3001")
    else:
        print(f"  NOTE - Dev server NOT running (OK for AWS-only mode)")
except Exception as e:
    print(f"  ERROR: {str(e)[:60]}")

# Test 9: Orchestrator database
print("\n[TEST 9] Orchestrator status...")
try:
    import psycopg2
    conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as runs FROM algo_orchestrator_runs WHERE started_at > NOW() - INTERVAL '24 hours'"
    )
    runs = cursor.fetchone()[0]
    print(f"  OK - {runs} orchestrator runs in last 24h")
    conn.close()
except Exception as e:
    print(f"  ERROR: {str(e)[:60]}")

# Test 10: Pre-commit hooks
print("\n[TEST 10] Pre-commit configuration...")
try:
    with open(".pre-commit-config.yaml", "r") as f:
        content = f.read()
    if "mypy" in content:
        print(f"  OK - Pre-commit hooks configured")
    else:
        print(f"  WARNING - Hooks may be incomplete")
except Exception as e:
    print(f"  NOTE - Pre-commit not configured (optional)")

print("\n" + "="*70)
print("SYSTEM TEST COMPLETE")
print("="*70)
