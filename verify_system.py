#!/usr/bin/env python3
"""Verify critical systems."""
import sys
import os
sys.path.insert(0, '.')

passed = 0
total = 0

def test(name, condition):
    global passed, total
    total += 1
    symbol = "OK" if condition else "XX"
    print(f"[{symbol}] {name}", flush=True)
    sys.stdout.flush()
    if condition:
        passed += 1
    return condition

print("\n=== SYSTEM VERIFICATION ===\n")

# 1. Database
try:
    import psycopg2
    conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM stock_prices_daily")
    count = cursor.fetchone()[0]
    conn.close()
    test("DATABASE", count > 0)
except Exception as e:
    test("DATABASE", False)

# 2. AWS Credentials
api_url = os.environ.get("DASHBOARD_API_URL", "")
pool_id = os.environ.get("COGNITO_USER_POOL_ID", "")
test("AWS_CREDS", bool(api_url and pool_id))

# 3. Cognito Auth
try:
    from dashboard.cognito_auth import get_cognito_auth
    auth = get_cognito_auth(require_auth=True)
    test("COGNITO_AUTH", auth and hasattr(auth, 'access_token') and auth.access_token)
except:
    test("COGNITO_AUTH", False)

# 4. API Connectivity
try:
    from dashboard.api_data_layer import api_call, set_cognito_auth
    from dashboard.cognito_auth import get_cognito_auth
    auth = get_cognito_auth(require_auth=True)
    set_cognito_auth(auth)
    result = api_call("/api/algo/status")
    test("API_CALL", "_error" not in result)
except Exception as e:
    test("API_CALL", False)

# 5. Dashboard Module
try:
    from dashboard.dashboard import main
    test("DASHBOARD_MODULE", True)
except:
    test("DASHBOARD_MODULE", False)

# 6. run_dashboard Script
try:
    with open("run_dashboard.py") as f:
        test("RUN_DASHBOARD", "from dashboard.dashboard import main" in f.read())
except:
    test("RUN_DASHBOARD", False)

# 7. Dev Server
try:
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(("127.0.0.1", 3001))
    sock.close()
    test("DEV_SERVER", result == 0)
except:
    test("DEV_SERVER", False)

# 8. Orchestrator
try:
    import psycopg2
    conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM algo_orchestrator_runs WHERE started_at > NOW() - INTERVAL '24 hours'")
    runs = cursor.fetchone()[0]
    conn.close()
    test("ORCHESTRATOR", runs > 0)
except:
    test("ORCHESTRATOR", False)

# 9. Pre-commit
try:
    with open(".pre-commit-config.yaml") as f:
        test("PRE_COMMIT", "mypy" in f.read())
except:
    test("PRE_COMMIT", False)

print(f"\n=== RESULTS: {passed}/{total} PASSED ===\n")

if passed == total:
    print("STATUS: ALL SYSTEMS OPERATIONAL")
    sys.exit(0)
else:
    print(f"STATUS: {total - passed} SYSTEMS FAILED")
    sys.exit(1)
