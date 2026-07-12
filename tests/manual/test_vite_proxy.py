#!/usr/bin/env python3
"""Test if Vite proxy is forwarding API requests correctly"""
import json
import time

import requests

print("=" * 70)
print("VITE PROXY TEST - Simulating browser API calls")
print("=" * 70)

# Test 1: Direct call to dev_server (backend)
print("\n[1] Backend API (direct):")
print("    GET http://localhost:3001/api/algo/status")
try:
    resp = requests.get(
        "http://localhost:3001/api/algo/status",
        headers={"Authorization": "Bearer dev-admin"},
        timeout=5
    )
    print(f"    Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print("    [OK] Backend responding correctly")
        print(f"         Response has: {list(data.keys())}")
    else:
        print(f"    [FAIL] Status {resp.status_code}")
except Exception as e:
    print(f"    [ERROR] {e}")

# Test 2: Call through Vite proxy (frontend → proxy → backend)
print("\n[2] Vite Proxy (simulating browser request):")
print("    GET http://localhost:5175/api/algo/status")
try:
    resp = requests.get(
        "http://localhost:5175/api/algo/status",
        headers={
            "Authorization": "Bearer dev-admin",
            "Origin": "http://localhost:5175"
        },
        timeout=5
    )
    print(f"    Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print("    [OK] Proxy forwarding correctly")
        print(f"         Response has: {list(data.keys())}")
    elif resp.status_code in [404, 502, 503]:
        print(f"    [FAIL] Proxy not forwarding: {resp.status_code}")
        print(f"           Response: {resp.text[:200]}")
    else:
        print(f"    [FAIL] Unexpected status: {resp.status_code}")
        print(f"           Response: {resp.text[:200]}")
except requests.ConnectionError as e:
    print("    [ERROR] Connection refused - Vite proxy not listening?")
    print(f"           {e}")
except Exception as e:
    print(f"    [ERROR] {e}")

# Test 3: Check CORS headers
print("\n[3] CORS Headers from Vite Proxy:")
try:
    resp = requests.options(
        "http://localhost:5175/api/algo/status",
        headers={
            "Origin": "http://localhost:5175",
            "Access-Control-Request-Method": "GET"
        },
        timeout=5
    )
    print(f"    Status: {resp.status_code}")
    cors_headers = {k: v for k, v in resp.headers.items() if 'access' in k.lower()}
    if cors_headers:
        for k, v in cors_headers.items():
            print(f"    {k}: {v}")
    else:
        print("    [NO CORS HEADERS]")
except Exception as e:
    print(f"    [ERROR] {e}")

print("\n" + "=" * 70)
print("DIAGNOSIS:")
print("=" * 70)
print("""
If Backend API works but Vite Proxy fails:
  → Vite proxy target is misconfigured or not running
  → Check: vite.config.js proxy.target should be 'http://localhost:3001'
  → Check: npm run dev is actually starting

If Vite Proxy works but browser still shows 'data not available':
  → Check browser console for JS errors
  → Check Network tab to see actual API responses
  → Verify response format matches frontend expectations
""")
