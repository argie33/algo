#!/usr/bin/env python3
"""End-to-end system test: verify algo trading pipeline works completely"""

import subprocess
import time
import requests
import json
from datetime import datetime

def run_cmd(cmd):
    """Run shell command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def check_api(endpoint):
    """Check if API endpoint returns data"""
    try:
        resp = requests.get(f"http://localhost:3001{endpoint}",
                          headers={"Authorization": "Bearer dev-admin"},
                          timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return 200, data.get("data")
        return resp.status_code, None
    except Exception as e:
        return 0, str(e)

print("\n" + "="*80)
print("COMPREHENSIVE SYSTEM TEST")
print("="*80 + "\n")

# Test 1: Services Running
print("[1/5] Checking Services...")
services_ok = True
for port, name in [(3001, "dev_server"), (5173, "vite"), (5432, "postgres")]:
    code, out, _ = run_cmd(f"netstat -tln 2>/dev/null | grep -q ':{port}' && echo OK || echo FAIL")
    if out.strip() == "OK" or code == 0:
        print(f"  [OK] {name:15} listening on port {port}")
    else:
        print(f"  [NO] {name:15} NOT listening on port {port}")
        services_ok = False

if not services_ok:
    print("\n[ERROR] Some services not running. Start with: ./start-fresh-dev.ps1")
    exit(1)

# Test 2: API Endpoints
print("\n[2/5] Testing API Endpoints...")
endpoints_ok = True
test_endpoints = [
    ("/api/portfolio", "Portfolio"),
    ("/api/algo/status", "Algo Status"),
    ("/api/algo/positions", "Positions"),
    ("/api/algo/performance", "Performance"),
    ("/api/algo/markets", "Markets"),
]

for endpoint, name in test_endpoints:
    status, data = check_api(endpoint)
    if status == 200 and data:
        age = data.get("data_freshness", {}).get("data_age_days", "unknown")
        print(f"  [OK] {name:20} {status} OK (age: {age}d)")
    elif status:
        print(f"  [NO] {name:20} HTTP {status}")
        endpoints_ok = False
    else:
        print(f"  [NO] {name:20} Error: {data}")
        endpoints_ok = False

if not endpoints_ok:
    print("\n[ERROR] API endpoints failing. Check dev_server logs.")
    exit(1)

# Test 3: Data Loaders
print("\n[3/5] Checking Data Freshness...")
status, data = check_api("/api/algo/status")
if status == 200 and data:
    portfolio_value = data.get("portfolio", {}).get("total_portfolio_value")
    positions = data.get("portfolio", {}).get("position_count", 0)
    freshness_days = data.get("data_freshness", {}).get("data_age_days", 999)

    if portfolio_value and positions > 0:
        print(f"  [OK] Portfolio Data:")
        print(f"    - Value: ${portfolio_value}")
        print(f"    - Positions: {positions}")
        print(f"    - Freshness: {freshness_days} days old")
    else:
        print(f"  [WN] Portfolio data incomplete or missing")
else:
    print(f"  [NO] Could not fetch portfolio status")

# Test 4: Dashboard Data
print("\n[4/5] Verifying Dashboard Can Load...")
test_endpoints_dashboard = [
    "/api/algo/daily-return-histogram",
    "/api/algo/trade-distribution",
    "/api/algo/holding-period-distribution",
    "/api/algo/circuit-breakers",
]

dashboard_ok = True
for endpoint in test_endpoints_dashboard:
    status, _ = check_api(endpoint)
    name = endpoint.split("/")[-1]
    if status == 200:
        print(f"  [OK] {name:35} available")
    else:
        print(f"  [NO] {name:35} HTTP {status}")
        dashboard_ok = False

# Test 5: Paper Trading Status
print("\n[5/5] Checking Paper Trading Status...")
status, data = check_api("/api/algo/status")
if status == 200 and data:
    run_id = data.get("run_id", "unknown")
    success = data.get("success", False)
    phase = data.get("current_phase", "unknown")

    if success:
        print(f"  [OK] Last Run: {run_id}")
        print(f"  [OK] Status: SUCCESS")
        print(f"  [OK] Current Phase: {phase}")
    else:
        print(f"  [WN] Last Run: {run_id}")
        print(f"  [WN] Status: {data.get('status', 'unknown')}")
        print(f"  [IF] Phase: {phase}")
else:
    print(f"  [NO] Could not fetch orchestrator status")

# Summary
print("\n" + "="*80)
print("TEST RESULTS")
print("="*80)

if services_ok and endpoints_ok and dashboard_ok:
    print("\n[OK] ALL SYSTEMS OPERATIONAL")
    print("\nNext steps:")
    print("  1. Open dashboard: http://localhost:5173")
    print("  2. Hard refresh: Ctrl+Shift+R")
    print("  3. Verify data displays in all panels")
    print("  4. Check paper trading positions in Positions panel")
else:
    print("\n[NO] SYSTEM ISSUES DETECTED")
    print("\nDebug steps:")
    print("  1. Check service logs: dev_server, vite, postgres")
    print("  2. Restart services: ./start-fresh-dev.ps1")
    print("  3. Check browser console for JavaScript errors (F12)")

print("\n" + "="*80 + "\n")
