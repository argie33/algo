#!/usr/bin/env python
"""
Verify that scores API returns factor input objects correctly.
Tests against local dev_server (must be running).
"""

import requests
import json
import sys
from typing import Any

def check_api_health(base_url: str = "http://localhost:3001") -> bool:
    """Check if API is responding."""
    try:
        response = requests.get(f"{base_url}/api/health", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def get_scores(base_url: str = "http://localhost:3001", limit: int = 3) -> dict[str, Any]:
    """Get scores from API."""
    response = requests.get(
        f"{base_url}/api/scores",
        params={"sort_by": "composite_score", "limit": limit},
        timeout=10
    )
    response.raise_for_status()
    return response.json()

def verify_factor_inputs(stock: dict[str, Any]) -> dict[str, bool]:
    """Verify all expected factor input objects are present."""
    expected_factors = [
        "quality_inputs",
        "momentum_inputs",
        "value_inputs",
        "growth_inputs",
        "positioning_inputs",
        "stability_inputs"
    ]

    results = {}
    for factor in expected_factors:
        present = factor in stock
        is_dict = isinstance(stock.get(factor), dict) if present else False
        has_content = bool(stock.get(factor)) if is_dict else False
        results[factor] = {
            "present": present,
            "is_dict": is_dict,
            "has_content": has_content,
        }

    return results

def main():
    print("=" * 70)
    print("SCORES API FACTOR INPUT VERIFICATION")
    print("=" * 70)

    # Check API health
    print("\n1. Checking API health...")
    if not check_api_health():
        print("   [FAIL] API is not responding. Start dev_server with:")
        print("      python lambda/api/dev_server.py")
        sys.exit(1)
    print("   [OK] API is healthy")

    # Fetch scores
    print("\n2. Fetching scores from API...")
    try:
        data = get_scores(limit=3)
        stocks = data.get("data", {}).get("top", [])
        print(f"   [OK] Got {len(stocks)} stocks")
    except Exception as e:
        print(f"   [FAIL] Failed to fetch scores: {e}")
        sys.exit(1)

    # Verify factor inputs for each stock
    print("\n3. Verifying factor input objects...")
    all_passed = True

    for i, stock in enumerate(stocks, 1):
        symbol = stock.get("symbol", "UNKNOWN")
        print(f"\n   Stock {i}: {symbol}")

        results = verify_factor_inputs(stock)

        for factor, check in results.items():
            if check["present"] and check["is_dict"]:
                field_count = len(stock.get(factor, {}))
                print(f"     [OK] {factor}: {field_count} fields")
            else:
                status = "missing" if not check["present"] else "not a dict"
                print(f"     [FAIL] {factor}: {status}")
                all_passed = False

    # Summary
    print("\n" + "=" * 70)
    if all_passed:
        print("[OK] VERIFICATION PASSED: All factor input objects present and properly structured")
        print("\nSample factor_inputs from first stock:")
        if stocks:
            sample = stocks[0]
            print(f"  Symbol: {sample.get('symbol')}")
            print(f"  Composite Score: {sample.get('composite_score')}")

            # Show sample quality_inputs
            quality = sample.get("quality_inputs", {})
            if quality:
                print(f"\n  Quality Inputs Sample:")
                for k, v in list(quality.items())[:5]:
                    print(f"    - {k}: {v}")
                print(f"    ... ({len(quality)} total fields)")

            # Show sample momentum_inputs
            momentum = sample.get("momentum_inputs", {})
            if momentum:
                print(f"\n  Momentum Inputs Sample:")
                for k, v in list(momentum.items())[:3]:
                    print(f"    - {k}: {v}")
                print(f"    ... ({len(momentum)} total fields)")
    else:
        print("[FAIL] VERIFICATION FAILED: Some factor input objects are missing or malformed")
        sys.exit(1)

    print("=" * 70)

if __name__ == "__main__":
    main()
