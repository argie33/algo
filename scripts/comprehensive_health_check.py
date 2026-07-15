#!/usr/bin/env python3
"""Comprehensive health check for Algo system in AWS mode."""

import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.fetchers import load_all
from dashboard.api_data_layer import api_call


def check_api_health():
    """Check if API is responding."""
    print("\n[1] CHECKING API HEALTH...")
    try:
        response = api_call("/api/health")
        if isinstance(response, dict) and "status" in response:
            print(f"  [OK] API is healthy: {response.get('status')}")
            return True
        else:
            print(f"  [WARN] API returned unexpected response: {response}")
            return False
    except Exception as e:
        print(f"  [FAIL] API health check failed: {e}")
        return False


def check_data_freshness():
    """Check if data is fresh (not stale)."""
    print("\n[2] CHECKING DATA FRESHNESS...")
    try:
        # Try to get market data which includes timestamps
        market_data = api_call("/api/algo/markets")
        if isinstance(market_data, dict):
            # Check for freshness flags
            if "_stale_cache" in market_data:
                age = market_data.get("_cache_age_hours", "unknown")
                print(f"  [WARN] Market data is STALE (cache age: {age}h)")
                return False
            elif "updated_at" in market_data:
                updated = datetime.fromisoformat(market_data["updated_at"])
                age = (datetime.now(timezone.utc) - updated).total_seconds() / 3600
                if age > 4:
                    print(f"  [WARN] Market data is old ({age:.1f}h old)")
                    return False
                else:
                    print(f"  [OK] Market data is fresh ({age:.1f}h old)")
                    return True
            else:
                print(f"  [OK] Market data available")
                return True
        else:
            print(f"  [FAIL] Market data fetch returned unexpected type: {type(market_data)}")
            return False
    except Exception as e:
        print(f"  [FAIL] Data freshness check failed: {e}")
        return False


def check_dashboard_fetchers():
    """Check if all dashboard fetchers are working."""
    print("\n[3] CHECKING DASHBOARD FETCHERS...")
    try:
        data = load_all()

        if not isinstance(data, dict):
            print(f"  [FAIL] load_all() returned {type(data)}, expected dict")
            return False

        total = len(data)
        with_data = sum(1 for v in data.values() if v and not (isinstance(v, dict) and "_error" in v))
        with_errors = sum(1 for v in data.values() if isinstance(v, dict) and "_error" in v)
        with_stale = sum(1 for v in data.values() if isinstance(v, dict) and "_stale_cache" in v)

        print(f"  Total fetchers: {total}")
        print(f"    [OK] With data: {with_data}")
        if with_errors > 0:
            print(f"    [FAIL] With errors: {with_errors}")
            error_list = [k for k, v in data.items() if isinstance(v, dict) and "_error" in v]
            for fname in error_list[:5]:
                print(f"      - {fname}: {data[fname]['_error'][:60]}")
        if with_stale > 0:
            print(f"    [WARN] With stale cache: {with_stale}")

        if with_errors > 0:
            return False
        return True
    except Exception as e:
        print(f"  [FAIL] Fetcher check failed: {e}")
        return False


def check_critical_panels():
    """Check if critical panels have data."""
    print("\n[4] CHECKING CRITICAL PANELS...")
    try:
        data = load_all()

        critical_panels = {
            "port": "Portfolio",
            "pos": "Positions",
            "perf": "Performance",
            "trades": "Trades",
            "sig": "Signals",
            "scores": "Scores",
            "mkt": "Market",
        }

        all_good = True
        for key, name in critical_panels.items():
            if key not in data:
                print(f"  [FAIL] {name}: NOT IN DATA")
                all_good = False
            elif isinstance(data[key], dict) and "_error" in data[key]:
                print(f"  [FAIL] {name}: ERROR - {data[key]['_error'][:50]}")
                all_good = False
            elif isinstance(data[key], dict) and "_stale_cache" in data[key]:
                age = data[key].get("_cache_age_hours", "unknown")
                print(f"  [WARN] {name}: STALE ({age}h old)")
            else:
                # Check if data is empty
                if isinstance(data[key], dict):
                    if not data[key]:
                        print(f"  [WARN] {name}: Empty dict")
                    else:
                        print(f"  [OK] {name}: OK")
                elif isinstance(data[key], list):
                    print(f"  [OK] {name}: OK ({len(data[key])} items)")
                else:
                    print(f"  [OK] {name}: OK")

        return all_good
    except Exception as e:
        print(f"  [FAIL] Panel check failed: {e}")
        return False


def check_scores_data():
    """Specifically check scores panel data."""
    print("\n[5] CHECKING SCORES DATA...")
    try:
        data = load_all()
        if "scores" not in data:
            print("  [FAIL] Scores data not loaded")
            return False

        scores_data = data["scores"]
        if isinstance(scores_data, dict):
            if "_error" in scores_data:
                print(f"  [FAIL] Scores error: {scores_data['_error'][:60]}")
                return False
            elif "top" in scores_data:
                top = scores_data["top"]
                if isinstance(top, list) and len(top) > 0:
                    print(f"  [OK] Scores: {len(top)} stocks loaded")
                    # Check first row for required fields
                    first = top[0]
                    if isinstance(first, dict):
                        required = ["symbol", "composite_score", "rs_percentile"]
                        missing = [f for f in required if f not in first]
                        if missing:
                            print(f"    [WARN] Missing fields in first row: {missing}")
                        else:
                            print(f"    [OK] All required fields present")
                    return True
                else:
                    print(f"  [WARN] Scores: Empty or not a list")
                    return False
            else:
                print(f"  [WARN] Scores: Missing 'top' field")
                return False
        else:
            print(f"  [FAIL] Scores data is {type(scores_data)}, expected dict")
            return False
    except Exception as e:
        print(f"  [FAIL] Scores check failed: {e}")
        return False


def main():
    print("=" * 60)
    print("ALGO SYSTEM COMPREHENSIVE HEALTH CHECK")
    print("=" * 60)
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"API URL: {os.environ.get('DASHBOARD_API_URL', 'LOCAL')}")

    results = {
        "API Health": check_api_health(),
        "Data Freshness": check_data_freshness(),
        "Dashboard Fetchers": check_dashboard_fetchers(),
        "Critical Panels": check_critical_panels(),
        "Scores Data": check_scores_data(),
    }

    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("=" * 60)
    for check_name, passed in results.items():
        status = "[OK] PASS" if passed else "[FAIL] FAIL"
        print(f"{status} {check_name}")

    all_passed = all(results.values())
    print("\n" + ("[OK] ALL CHECKS PASSED" if all_passed else "[FAIL] SOME CHECKS FAILED"))

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
