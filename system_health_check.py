#!/usr/bin/env python3
"""Comprehensive system health check for production deployment."""

import os
import sys
import subprocess
from pathlib import Path

os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
os.environ['LOCAL_MODE'] = 'true'

from utils.db import DatabaseContext
import requests

print("=" * 80)
print("ALGO SYSTEM HEALTH CHECK")
print("=" * 80)

# Test 1: Database connectivity
print("\n[TEST 1] Database Connectivity...")
try:
    with DatabaseContext('read') as cur:
        cur.execute("SELECT 1")
        print("  [OK] Database connection OK")
except Exception as e:
    print(f"  [FAIL] Database connection FAILED: {e}")
    sys.exit(1)

# Test 2: API server health
print("\n[TEST 2] API Server Health...")
try:
    resp = requests.get("http://localhost:3001/api/health", headers={"Authorization": "Bearer dev-admin"}, timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        print(f"  [OK] API server OK - version {data['data'].get('version', 'unknown')}")
    else:
        print(f"  [FAIL] API health check failed: {resp.status_code}")
except Exception as e:
    print(f"  [FAIL] API server unreachable: {e}")

# Test 3: Critical API endpoints
print("\n[TEST 3] Critical API Endpoints...")
critical_endpoints = [
    ("/api/portfolio", "Portfolio data"),
    ("/api/positions", "Open positions"),
    ("/api/trades", "Trade history"),
    ("/api/algo/scores", "Stock scores"),
    ("/api/algo/dashboard-signals", "Trading signals"),
]

for endpoint, desc in critical_endpoints:
    try:
        resp = requests.get(f"http://localhost:3001{endpoint}", headers={"Authorization": "Bearer dev-admin"}, timeout=5)
        if resp.status_code == 200:
            print(f"  [OK] {desc:20} ({endpoint})")
        else:
            print(f"  [FAIL] {desc:20} ({endpoint}) - {resp.status_code}")
    except Exception as e:
        print(f"  [FAIL] {desc:20} ({endpoint}) - {type(e).__name__}")

# Test 4: Data completeness
print("\n[TEST 4] Data Completeness...")

checks = [
    ("Stock scores", "SELECT COUNT(*) as count FROM stock_scores WHERE data_unavailable = FALSE"),
    ("Portfolio snapshots", "SELECT COUNT(*) as count FROM algo_portfolio_snapshots"),
    ("Open positions", "SELECT COUNT(*) as count FROM algo_positions WHERE quantity != 0"),
    ("Recent trades", "SELECT COUNT(*) as count FROM algo_trades WHERE created_at > CURRENT_DATE - INTERVAL '7 days'"),
    ("Price data", "SELECT COUNT(*) as count FROM price_daily"),
]

for name, query in checks:
    try:
        with DatabaseContext('read') as cur:
            cur.execute(query)
            result = cur.fetchone()
            count = result['count'] if result else 0
            status = "[OK]" if count > 0 else "[FAIL]"
            print(f"  {status} {name:25} {count:,} records")
    except Exception as e:
        print(f"  [FAIL] {name:25} Query failed: {str(e)[:50]}")

# Test 5: Recent orchestrator execution
print("\n[TEST 5] Recent Orchestrator Execution...")
try:
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT overall_status, COUNT(*) as count
            FROM algo_orchestrator_runs
            WHERE started_at > NOW() - INTERVAL '24 hours'
            GROUP BY overall_status
        """)
        results = cur.fetchall()
        for r in results:
            print(f"  [OK] {r['overall_status']:10} {r['count']} runs")
except Exception as e:
    print(f"  [FAIL] Orchestrator query failed: {e}")

# Test 6: Code quality
print("\n[TEST 6] Code Quality Checks...")

# Check for common problems
issues_found = []

# Check for print statements in library code
result = subprocess.run(
    ["grep", "-r", "^\\s*print(", "algo/", "lambda/", "loaders/", "utils/", "--include=*.py"],
    capture_output=True,
    text=True
)
if result.stdout:
    lines = result.stdout.strip().split('\n')[:3]  # Show first 3
    issues_found.append(f"print() statements in library code ({len(result.stdout.splitlines())} found)")

# Check for pdb
result = subprocess.run(
    ["grep", "-r", "pdb|ipdb|breakpoint", "algo/", "lambda/", "loaders/", "utils/", "--include=*.py"],
    capture_output=True,
    text=True
)
if result.stdout:
    issues_found.append(f"Debug statements found ({len(result.stdout.splitlines())} found)")

if issues_found:
    for issue in issues_found:
        print(f"  [FAIL] {issue}")
else:
    print(f"  [OK] No obvious code quality issues detected")

# Test 7: Configuration
print("\n[TEST 7] Configuration...")
config_checks = [
    ("Environment", "ORCHESTRATOR_EXECUTION_MODE", os.environ.get("ORCHESTRATOR_EXECUTION_MODE", "not set")),
    ("Paper trading", "ALPACA_PAPER_TRADING", os.environ.get("ALPACA_PAPER_TRADING", "not set")),
    ("Dev mode", "DEV_MODE", os.environ.get("DEV_MODE", "not set")),
]

for name, var, value in config_checks:
    print(f"  - {name:20} {var:30} = {value}")

print("\n" + "=" * 80)
print("HEALTH CHECK COMPLETE")
print("=" * 80)
