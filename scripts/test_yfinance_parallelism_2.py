#!/usr/bin/env python3
"""Test yfinance with parallelism=2 to verify no rate limiting occurs.

This test safely increases parallelism from 1 to 2 and monitors for HTTP 429 errors.
If no rate limiting is detected, the optimization can be enabled.
"""

import os
import re
import subprocess
import sys
from pathlib import Path


def run_analyst_loader_with_parallelism(parallelism: int, timeout_minutes: int = 30) -> dict:
    """Run analyst_sentiment_analysis with specified parallelism."""
    env = os.environ.copy()
    env["LOADER_PARALLELISM"] = str(parallelism)
    env["LOADER_TIMEOUT"] = str(timeout_minutes * 60)
    env["LOCAL_MODE"] = "true"

    print(f"\n{'=' * 70}")
    print(f"Running analyst_sentiment_analysis with LOADER_PARALLELISM={parallelism}")
    print(f"Timeout: {timeout_minutes} minutes")
    print(f"{'=' * 70}\n")

    try:
        result = subprocess.run(
            [sys.executable, "loaders/load_analyst_sentiment_analysis.py"],
            cwd=Path(__file__).parent.parent,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_minutes * 60,
        )

        output = result.stdout + result.stderr
        has_429 = "429" in output or "rate limit" in output.lower() or "rate_limit" in output
        symbols_match = re.search(r"Loaded (\d+)/(\d+)", output)
        symbols_loaded = None
        symbols_total = None

        if symbols_match:
            symbols_loaded = int(symbols_match.group(1))
            symbols_total = int(symbols_match.group(2))

        return {
            "parallelism": parallelism,
            "returncode": result.returncode,
            "has_429_errors": has_429,
            "symbols_loaded": symbols_loaded,
            "symbols_total": symbols_total,
            "output_sample": output[-500:] if len(output) > 500 else output,
            "success": result.returncode == 0 and not has_429,
        }
    except subprocess.TimeoutExpired:
        return {
            "parallelism": parallelism,
            "returncode": -1,
            "timeout": True,
            "has_429_errors": None,
            "symbols_loaded": None,
            "symbols_total": None,
            "output_sample": "TIMEOUT",
            "success": False,
        }
    except Exception as e:
        return {
            "parallelism": parallelism,
            "returncode": -1,
            "error": str(e),
            "has_429_errors": None,
            "symbols_loaded": None,
            "symbols_total": None,
            "output_sample": str(e),
            "success": False,
        }


def main():
    """Test parallelism=2 and determine if it's safe to enable."""
    print("Yfinance Parallelism Optimization Test")
    print("=" * 70)
    print("Testing if parallelism=2 is safe (no 429 rate limit errors)")
    print("Current: parallelism=1 (safe but slow)")
    print("Target:  parallelism=2 (should be safe, ~50% speedup)")
    print()

    # Phase 1: Test with parallelism=2
    result_p2 = run_analyst_loader_with_parallelism(2, timeout_minutes=30)

    print("\nTest Results:")
    print("-" * 70)
    print(f"Parallelism: {result_p2['parallelism']}")
    print(f"Return code: {result_p2['returncode']}")
    print(f"Has 429 errors: {result_p2['has_429_errors']}")
    if result_p2.get("timeout"):
        print("Status: TIMEOUT - loader exceeded 30 min timeout")
    elif result_p2.get("error"):
        print(f"Status: ERROR - {result_p2['error']}")
    else:
        if result_p2["symbols_loaded"] is not None:
            completion = (
                (result_p2["symbols_loaded"] / result_p2["symbols_total"] * 100) if result_p2["symbols_total"] else 0
            )
            print(f"Symbols loaded: {result_p2['symbols_loaded']}/{result_p2['symbols_total']} ({completion:.1f}%)")
        print(f"Status: {'SUCCESS' if result_p2['success'] else 'FAILED'}")

    print("\nLast 500 chars of output:")
    print("-" * 70)
    print(result_p2["output_sample"])
    print("-" * 70)

    # Recommendation
    print("\nRECOMMENDATION:")
    if result_p2["success"]:
        print("[OK] SAFE TO ENABLE: No 429 errors detected with parallelism=2")
        print("   Next steps:")
        print("   1. Update scripts/local_loader_scheduler.py: LOADER_PARALLELISM = '2'")
        print("   2. Update loaders/runner.py default parallelism to 2")
        print("   3. Monitor production for any 429 rate limit errors")
        print("   4. Expected speedup: 50-67% on analyst loaders (6+ hours → 3 hours)")
        return 0
    elif result_p2.get("timeout"):
        print("[WARN]  TIMEOUT: Loader exceeded 30-min timeout")
        print("   This may indicate:")
        print("   - Parallelism=2 still triggers rate limiting")
        print("   - 30 min is insufficient (increase timeout)")
        print("   Recommendation: Keep parallelism=1 for now")
        return 1
    elif result_p2.get("has_429_errors"):
        print("[FAIL] RATE LIMITED: HTTP 429 errors detected")
        print("   Parallelism=2 triggers Yahoo rate limiting")
        print("   Keep parallelism=1 (safe)")
        return 1
    else:
        print("[FAIL] FAILED: Loader execution failed")
        print(f"   Error: {result_p2.get('error', 'Unknown')}")
        print("   Recommendation: Investigate error before enabling parallelism=2")
        return 1


if __name__ == "__main__":
    sys.exit(main())
