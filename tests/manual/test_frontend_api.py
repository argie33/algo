#!/usr/bin/env python3
"""Test frontend API connectivity from browser perspective.

Manual diagnostic script - run directly with `python tests/manual/test_frontend_api.py`.
Not a real pytest test: it prints connectivity results rather than asserting, so it must
stay guarded from pytest collection (see test_market_handler.py for the same pattern) -
otherwise every full test-suite run silently fires live HTTP requests at localhost during
collection, with no pass/fail signal to show for it.
"""

import sys

if "pytest" in sys.modules:
    import pytest

    pytest.skip(allow_module_level=True)

from typing import Any

import requests


def check_endpoint(url: str, headers: dict[str, str] | None = None) -> tuple[int | None, Any]:
    """Test if an endpoint is accessible"""
    if headers is None:
        headers = {"Authorization": "Bearer dev-admin"}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        return resp.status_code, resp.json() if resp.text else None
    except Exception as e:
        return None, str(e)


def main() -> None:
    # Test backend API on localhost:3001 (what dev_server should serve)
    endpoints = [
        ("Portfolio", "http://localhost:3001/api/portfolio"),
        ("Holdings", "http://localhost:3001/api/holdings"),
        ("Signals", "http://localhost:3001/api/signals"),
        ("Market Sentiment", "http://localhost:3001/api/market/sentiment"),
        ("Portfolio Health", "http://localhost:3001/api/health/portfolio"),
    ]

    print("=" * 60)
    print("TESTING API ENDPOINTS")
    print("=" * 60)

    for name, url in endpoints:
        status, resp = check_endpoint(url)
        if status == 200:
            print(f"[OK] {name:20} {url}")
            if isinstance(resp, dict) and "data" in resp:
                data_keys = list(resp["data"].keys())[:3]
                print(f"     Data keys: {', '.join(data_keys)}...")
        elif status:
            print(f"[FAIL] {name:20} Status {status}")
        else:
            print(f"[FAIL] {name:20} {resp}")

    print("\n" + "=" * 60)
    print("TESTING VITE PROXY SIMULATION")
    print("=" * 60)

    # Test what the frontend (on 5174) would see via Vite proxy
    # This simulates the Vite proxy that should forward /api to localhost:3001
    print("\nVite proxy should forward /api/* to http://localhost:3001")
    print("Frontend on localhost:5174 makes request to: http://localhost:5174/api/portfolio")
    print("Vite proxy forwards to: http://localhost:3001/api/portfolio")

    status, resp = check_endpoint("http://localhost:3001/api/portfolio")
    if status == 200:
        print("[OK] Backend is accessible via proxy target")
    else:
        print(f"[FAIL] Backend NOT accessible: {resp}")


if __name__ == "__main__":
    main()
