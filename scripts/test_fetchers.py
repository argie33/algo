#!/usr/bin/env python3
"""Test all fetchers to identify which ones are returning errors."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dashboard.fetchers import FETCHERS


def test_all_fetchers():
    """Test each fetcher and report which ones have errors."""
    results = {}

    for name, fetcher_fn in sorted(FETCHERS.items()):
        try:
            print(f"Testing {name}...", end=" ", flush=True)
            result = fetcher_fn(None)

            if isinstance(result, dict) and "_error" in result:
                results[name] = {
                    "status": "ERROR",
                    "error": result.get("_error", "Unknown error"),
                    "error_type": result.get("_error_type", "unknown"),
                }
                print(f"[ERROR] {result['_error'][:80]}")
            else:
                # Check if result has expected structure
                if isinstance(result, dict):
                    keys = list(result.keys())[:5]
                    results[name] = {
                        "status": "OK",
                        "keys": keys,
                        "data_points": len(result)
                    }
                    print(f"[OK] ({len(result)} fields)")
                elif isinstance(result, list):
                    # Lists are OK for some fetchers (e.g., algo_metrics returns list)
                    results[name] = {
                        "status": "OK",
                        "type": "list",
                        "length": len(result)
                    }
                    print(f"[OK] (list with {len(result)} items)")
                else:
                    results[name] = {
                        "status": "UNKNOWN",
                        "type": type(result).__name__
                    }
                    print(f"[UNKNOWN] {type(result).__name__}")
        except Exception as e:
            results[name] = {
                "status": "EXCEPTION",
                "exception": type(e).__name__,
                "message": str(e)[:100]
            }
            print(f"[EXCEPTION] {type(e).__name__}: {str(e)[:60]}")

    # Print summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    errors = {k: v for k, v in results.items() if v["status"] != "OK"}
    ok_count = {k: v for k, v in results.items() if v["status"] == "OK"}

    print(f"\n[OK] Working fetchers: {len(ok_count)}")
    for name in sorted(ok_count.keys()):
        print(f"  - {name}")

    if errors:
        print(f"\n[BROKEN] Error fetchers: {len(errors)}")
        for name, info in sorted(errors.items()):
            print(f"  - {name}: {info['status']}")
            if 'error' in info:
                print(f"    Error: {info['error']}")
            elif 'message' in info:
                print(f"    Exception: {info['exception']}: {info['message']}")

    return results

if __name__ == "__main__":
    results = test_all_fetchers()

    # Exit with error code if any fetchers failed
    failed = sum(1 for r in results.values() if r["status"] != "OK")
    sys.exit(1 if failed else 0)
