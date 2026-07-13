#!/usr/bin/env python3
"""Test dashboard data fetching to identify "data not available" root cause."""

import os
import sys
import time

# Set local mode
os.environ['LOCAL_MODE'] = 'true'
os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 80)
print("DASHBOARD DATA FETCHING TEST")
print("=" * 80)

# Start dev server if not running
print("\n[1/5] Starting dev_server...")
import subprocess
import socket

def check_port(host, port, timeout=2):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    finally:
        sock.close()

if not check_port('127.0.0.1', 3001):
    print("  Dev server not running. Starting...")
    proc = subprocess.Popen(
        [sys.executable, 'api-pkg/dev_server.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    time.sleep(3)
    if not check_port('127.0.0.1', 3001):
        print("  ERROR: Failed to start dev_server on localhost:3001")
        sys.exit(1)
    print("  OK - dev_server started")
else:
    print("  OK - dev_server already running on localhost:3001")

# Test API endpoint
print("\n[2/5] Testing API endpoint...")
try:
    from dashboard.api_data_layer import api_call, reset_circuit_breaker
    reset_circuit_breaker()

    result = api_call("/api/algo/config")
    if "_error" in result:
        print(f"  ERROR: {result['_error']}")
        sys.exit(1)
    if "statusCode" in result and result["statusCode"] >= 400:
        print(f"  ERROR: Status {result.get('statusCode')}")
        sys.exit(1)
    print(f"  OK - API returned {len(str(result))} bytes")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test fetchers
print("\n[3/5] Testing fetchers...")
try:
    from dashboard.fetchers import load_all

    print("  Loading all fetchers...")
    data = load_all()

    print(f"  Loaded {len(data)} fetcher results:")
    for key, value in data.items():
        if isinstance(value, dict):
            if "_error" in value:
                print(f"    {key}: ERROR - {value.get('_error', '?')}")
            elif "statusCode" in value and value["statusCode"] >= 400:
                print(f"    {key}: HTTP {value['statusCode']}")
            else:
                print(f"    {key}: OK ({len(str(value))} bytes)")
        else:
            print(f"    {key}: {type(value).__name__}")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Analyze failures
print("\n[4/5] Analyzing failures...")
failures = {k: v for k, v in data.items() if isinstance(v, dict) and ("_error" in v or (v.get("statusCode", 200) >= 400))}
if failures:
    print(f"  Found {len(failures)} failed fetchers:")
    for key, error in failures.items():
        if "_error" in error:
            print(f"    {key}: {error['_error'][:100]}")
        else:
            print(f"    {key}: HTTP {error.get('statusCode')}")
else:
    print("  All fetchers succeeded!")

# Summary
print("\n[5/5] Summary")
print("=" * 80)
total = len(data)
failed = len(failures)
passed = total - failed
print(f"Total fetchers: {total}")
print(f"Passed: {passed}")
print(f"Failed: {failed}")
if failed > 0:
    print("\nTo fix 'data not available':")
    for key in list(failures.keys())[:3]:
        error = failures[key]
        if "_error" in error:
            print(f"  - {key}: {error['_error'][:80]}")
        else:
            print(f"  - {key}: Check API response")

print("=" * 80)
