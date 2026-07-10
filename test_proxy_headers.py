#!/usr/bin/env python3
"""Debug Vite proxy header handling"""
import requests
import json

def test_direct_with_short_token():
    """Test if the API directly works with dev-admin token"""
    print("\n[1] Direct to backend with 'dev-admin' token:")
    resp = requests.get(
        "http://localhost:3001/api/algo/status",
        headers={"Authorization": "Bearer dev-admin"},
        timeout=5
    )
    print(f"   Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"   Error: {resp.text[:200]}")
    else:
        print(f"   OK: Got portfolio data")

def test_with_proper_bearer_format():
    """Test if Bearer prefix is the issue"""
    print("\n[2] Test different Authorization formats to :3001:")

    formats = [
        ("Bearer dev-admin", "Standard Bearer format"),
        ("dev-admin", "Token only"),
        ("Bearer dev-admin-token", "Longer token"),
    ]

    for auth_val, desc in formats:
        resp = requests.get(
            "http://localhost:3001/api/algo/status",
            headers={"Authorization": auth_val},
            timeout=5
        )
        status = resp.status_code
        if status == 200:
            print(f"   [{desc}] > {status} OK")
        elif "Token too short" in resp.text:
            print(f"   [{desc}] > {status} (Token too short)")
        else:
            print(f"   [{desc}] > {status} (Other error)")

def test_vite_proxy_with_headers():
    """Test Vite proxy with explicit header handling"""
    print("\n[3] Test Vite proxy (:5175) with bearer token:")

    headers = {
        "Authorization": "Bearer dev-admin",
        "Origin": "http://localhost:5175",
        "User-Agent": "Python-requests",
        "Accept": "application/json",
    }

    resp = requests.get(
        "http://localhost:5175/api/algo/status",
        headers=headers,
        timeout=5
    )
    print(f"   Status: {resp.status_code}")
    print(f"   Response: {resp.text[:200]}")

if __name__ == "__main__":
    test_direct_with_short_token()
    test_with_proper_bearer_format()
    test_vite_proxy_with_headers()
