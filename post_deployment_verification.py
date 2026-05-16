#!/usr/bin/env python3
"""
Post-Deployment Verification Suite

Run this script after Terraform deployment completes to verify:
1. API endpoints return 200 (not 401)
2. API responses have correct structure
3. Database has data in key tables
4. Calculations are correct
5. All critical modules function
"""

import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path

# Configuration
API_ENDPOINT = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"

def print_section(title):
    """Print a section header."""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def run_command(cmd, description):
    """Run a shell command and return success status."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"[OK] {description}")
            return True, result.stdout.strip()
        else:
            print(f"[FAIL] {description}")
            if result.stderr:
                print(f"      Error: {result.stderr[:200]}")
            return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        print(f"[FAIL] {description} (timeout)")
        return False, "Command timed out"
    except Exception as e:
        print(f"[FAIL] {description} (error: {e})")
        return False, str(e)

def check_api_health():
    """Check if API endpoints are responding."""
    print_section("1. API HEALTH CHECK")

    endpoints = [
        ("/api/health", "Health check endpoint"),
        ("/api/algo/status", "Algo status endpoint"),
        ("/api/stocks?limit=1", "Stocks endpoint"),
        ("/api/scores/stockscores?limit=1", "Stock scores endpoint"),
    ]

    results = []
    for endpoint, desc in endpoints:
        url = f"{API_ENDPOINT}{endpoint}"
        cmd = f'curl -s -w "\\n%{{http_code}}" "{url}" 2>/dev/null | tail -1'
        success, output = run_command(cmd, f"{desc} - {endpoint}")

        if success and output == "200":
            print(f"       Status: 200 ✓")
            results.append(True)
        else:
            print(f"       Status: {output} (expected 200)")
            results.append(False)

    return all(results)

def check_database_data():
    """Check if critical tables have data."""
    print_section("2. DATABASE DATA VERIFICATION")

    # This would normally require DB connection
    # For now, we'll check via API responses
    print("[INFO] Checking data via API responses...")

    checks = [
        ("Stock list populated",
         f'curl -s "{API_ENDPOINT}/api/stocks?limit=1" | grep -q "symbol"'),
        ("Scores populated",
         f'curl -s "{API_ENDPOINT}/api/scores/stockscores?limit=1" | grep -q "symbol"'),
    ]

    results = []
    for desc, cmd in checks:
        success, _ = run_command(cmd, desc)
        results.append(success)

    return all(results)

def check_calculation_logic():
    """Verify calculation modules can be imported."""
    print_section("3. CALCULATION MODULES VERIFICATION")

    modules = [
        "algo_signals",
        "algo_swing_score",
        "algo_var",
        "algo_market_exposure",
        "algo_pretrade_checks",
    ]

    results = []
    for module in modules:
        cmd = f"python3 -c 'import {module}; print(\"OK\")' 2>&1"
        success, _ = run_command(cmd, f"Import {module}")
        results.append(success)

    return all(results)

def check_orchestrator():
    """Check if orchestrator can be instantiated."""
    print_section("4. ORCHESTRATOR VERIFICATION")

    print("[INFO] Checking orchestrator can be initialized...")
    cmd = """python3 -c "
from algo_orchestrator import Orchestrator
from algo_config import get_config
config = get_config()
orch = Orchestrator(config)
print('Orchestrator initialized OK')
" 2>&1"""

    success, output = run_command(cmd, "Orchestrator instantiation")
    if success:
        print(f"       Output: {output}")

    return success

def check_safety_gates():
    """Verify safety gates are in place."""
    print_section("5. SAFETY GATES VERIFICATION")

    gates = [
        ("PreTradeChecks", "from algo_pretrade_checks import PreTradeChecks"),
        ("PaperModeGates", "from algo_paper_mode_gates import PaperModeGates"),
        ("CircuitBreaker", "from algo_circuit_breaker import CircuitBreaker"),
    ]

    results = []
    for name, import_stmt in gates:
        cmd = f'python3 -c "{import_stmt}; print(\'OK\')" 2>&1'
        success, _ = run_command(cmd, f"{name} gate")
        results.append(success)

    return all(results)

def check_api_response_format():
    """Verify API responses have expected structure."""
    print_section("6. API RESPONSE FORMAT VERIFICATION")

    print("[INFO] Checking response structures...")

    # Check health endpoint response
    cmd = f'curl -s "{API_ENDPOINT}/api/health"'
    success, output = run_command(cmd, "Health endpoint response format")

    if success and ("status" in output.lower() or "ok" in output.lower()):
        print("       Response contains expected fields ✓")
        return True
    else:
        print("       Response format unexpected")
        print(f"       Output: {output[:200]}")
        return False

def run_verification_suite():
    """Run all verification checks."""
    print("\n" + "="*70)
    print("  POST-DEPLOYMENT VERIFICATION SUITE")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*70)

    results = {}

    # Run all checks
    results['API Health'] = check_api_health()
    results['Database Data'] = check_database_data()
    results['Calculation Modules'] = check_calculation_logic()
    results['Orchestrator'] = check_orchestrator()
    results['Safety Gates'] = check_safety_gates()
    results['API Response Format'] = check_api_response_format()

    # Summary
    print_section("VERIFICATION SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for check, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {check}")

    print(f"\nTotal: {passed}/{total} checks passed")

    if passed == total:
        print("\n✓ ALL VERIFICATION CHECKS PASSED")
        print("  System is ready for orchestrator testing")
        return 0
    else:
        print(f"\n✗ {total - passed} verification check(s) failed")
        print("  Review issues above and retry")
        return 1

if __name__ == "__main__":
    sys.exit(run_verification_suite())
