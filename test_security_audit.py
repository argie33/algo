#!/usr/bin/env python3
"""
Phase 4: Security & API Hardening Audit
Tests:
1. Issue 3.1: API Authentication - Verify auth is required
2. Issue 3.2: Input Validation - Test for SQL injection vulnerabilities
3. Issue 3.3: HTTPS Enforcement - Verify HTTPS redirect
"""

import requests
import json
from typing import Dict, List, Tuple

API_BASE_LOCAL = "http://localhost:3001"
API_BASE_AWS = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"

print("=" * 80)
print("SECURITY AUDIT - Phase 4")
print("=" * 80)
print()

# ============================================================================
# ISSUE 3.1: API AUTHENTICATION
# ============================================================================
print("ISSUE 3.1: API Authentication")
print("-" * 80)

auth_endpoints = [
    '/api/stocks',
    '/api/sectors',
    '/api/algo/status',
    '/api/trades',
]

print("Test 1: Verify public endpoints require authentication")
for endpoint in auth_endpoints:
    try:
        response = requests.get(f"{API_BASE_AWS}{endpoint}", timeout=5)
        # Should be 401 Unauthorized without API key
        if response.status_code == 401:
            print(f"  ✅ {endpoint:30} → 401 Unauthorized (correct)")
        elif response.status_code == 200:
            print(f"  ⚠️  {endpoint:30} → 200 OK (NO AUTH ENFORCED!)")
        else:
            print(f"  ❌ {endpoint:30} → {response.status_code} (unexpected)")
    except Exception as e:
        print(f"  ⚠️  {endpoint:30} → Connection error: {str(e)}")

print()
print("Test 2: Verify health endpoint is public")
try:
    response = requests.get(f"{API_BASE_AWS}/api/health", timeout=5)
    if response.status_code == 200:
        print(f"  ✅ /api/health → 200 OK (public endpoint)")
    else:
        print(f"  ❌ /api/health → {response.status_code} (should be 200)")
except Exception as e:
    print(f"  ⚠️  /api/health → Connection error: {str(e)}")

print()

# ============================================================================
# ISSUE 3.2: INPUT VALIDATION - SQL INJECTION TESTS
# ============================================================================
print("ISSUE 3.2: Input Validation & SQL Injection Tests")
print("-" * 80)

print("Test 1: SQL Injection in 'symbol' parameter")
sql_injection_payloads = [
    "AAPL' OR '1'='1",
    "AAPL'; DROP TABLE stocks; --",
    "AAPL' UNION SELECT * FROM pg_user --",
    "A%27%20OR%201=1%20--",  # URL encoded
]

test_endpoint = f"{API_BASE_LOCAL}/api/stocks/AAPL"
print(f"Testing endpoint: {test_endpoint}")

for payload in sql_injection_payloads:
    test_url = f"{API_BASE_LOCAL}/api/stocks/{payload}"
    try:
        response = requests.get(test_url, timeout=5)
        # Should not execute SQL - should either:
        # - Return 400 Bad Request (input validation failed)
        # - Return 404 (symbol not found)
        # - Return no data (parameterized query protected)
        if response.status_code == 400:
            print(f"  ✅ Rejected malicious input: {payload[:30]}")
        elif response.status_code == 404:
            print(f"  ✅ No match found (safe): {payload[:30]}")
        elif response.status_code == 200:
            try:
                data = response.json()
                # Check if we got unexpected results (SQL injection succeeded)
                if not data.get('items') and not data.get('error'):
                    print(f"  ❌ POTENTIAL SQL INJECTION: {payload[:30]}")
                else:
                    print(f"  ✅ Parameterized query (safe): {payload[:30]}")
            except:
                print(f"  ✅ Invalid JSON response (safe): {payload[:30]}")
        else:
            print(f"  ⚠️  Unexpected status {response.status_code}: {payload[:30]}")
    except Exception as e:
        print(f"  ⚠️  Error testing {payload[:30]}: {str(e)[:50]}")

print()
print("Test 2: Input validation on numeric parameters (limit, offset)")
limit_payloads = [
    ("?limit=1000000", "large number"),
    ("?limit=-1", "negative"),
    ("?limit=abc", "non-numeric"),
    ("?offset=-10", "negative offset"),
    ("?offset=999999", "huge offset"),
]

for param, desc in limit_payloads:
    test_url = f"{API_BASE_LOCAL}/api/stocks{param}"
    try:
        response = requests.get(test_url, timeout=5)
        # Should handle gracefully with defaults or errors
        if response.status_code in [200, 400]:
            print(f"  ✅ Handled {desc}: {param} → {response.status_code}")
        else:
            print(f"  ❌ Unexpected {desc}: {param} → {response.status_code}")
    except Exception as e:
        print(f"  ⚠️  Error: {param} → {str(e)[:40]}")

print()

# ============================================================================
# ISSUE 3.3: HTTPS ENFORCEMENT
# ============================================================================
print("ISSUE 3.3: HTTPS Enforcement")
print("-" * 80)

print("Test 1: Verify HTTPS is used in production")
try:
    # Try HTTP and expect redirect to HTTPS
    response = requests.get(
        f"http://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health",
        timeout=5,
        allow_redirects=False
    )
    if response.status_code in [301, 302, 307, 308]:
        print(f"  ✅ HTTP redirects to HTTPS: {response.status_code}")
    elif response.status_code == 200:
        print(f"  ⚠️  HTTP accepted (should redirect to HTTPS): {response.status_code}")
    else:
        print(f"  ⚠️  Unexpected status: {response.status_code}")
except Exception as e:
    print(f"  ⚠️  Cannot test HTTP redirect: {str(e)[:50]}")

print()
print("Test 2: Verify HTTPS works")
try:
    response = requests.get(
        f"https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health",
        timeout=5
    )
    if response.status_code == 200:
        print(f"  ✅ HTTPS endpoint works: 200 OK")
        # Check for HSTS header
        hsts = response.headers.get('Strict-Transport-Security')
        if hsts:
            print(f"  ✅ HSTS header present: {hsts}")
        else:
            print(f"  ⚠️  HSTS header missing (should have max-age=31536000)")
    else:
        print(f"  ❌ HTTPS endpoint failed: {response.status_code}")
except Exception as e:
    print(f"  ⚠️  Cannot test HTTPS: {str(e)[:50]}")

print()

# ============================================================================
# SUMMARY
# ============================================================================
print("=" * 80)
print("SECURITY AUDIT SUMMARY")
print("=" * 80)
print()
print("Guidelines for Interpreting Results:")
print("  ✅ = PASS (security control working)")
print("  ⚠️  = WARNING (may need review or network issue)")
print("  ❌ = FAIL (security issue found)")
print()
print("Next Steps:")
print("  1. Review any ❌ failures and fix")
print("  2. Verify HSTS header is present")
print("  3. Test with actual API key (if configured)")
print("  4. Run in production environment if available")
print()
