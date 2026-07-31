#!/usr/bin/env python3
"""Stress test orchestrator - run multiple times to find issues."""

import subprocess
import sys
import json
from datetime import datetime

def run_orchestrator(iteration):
    """Run orchestrator and capture results."""
    print(f"\n[RUN {iteration}] Starting orchestrator...")
    result = subprocess.run(
        [sys.executable, "scripts/run_local_orchestrator.py", "--force"],
        capture_output=True,
        text=True,
        timeout=300
    )

    # Parse output for phase results
    output = result.stdout + result.stderr

    # Look for errors
    errors = []
    if "ERROR" in output:
        errors.append("ERROR in output")
    if "CRITICAL" in output and "SAFETY" not in output:
        errors.append("CRITICAL error found")
    if "FAIL" in output:
        errors.append("FAIL in output")
    if "Exception" in output:
        errors.append("Exception occurred")

    # Look for success indicators
    phases_completed = output.count("Phase ")

    # Check for market hours block
    if "outside market hours" in output:
        status = "SKIPPED (market hours guard)"
    elif "ORCHESTRATOR EXECUTOR COMPLETE" in output and "9/9 phases" in output:
        status = "OK - All 9 phases"
    elif errors:
        status = f"FAILED - {', '.join(errors)}"
    else:
        status = "UNKNOWN"

    return {
        "iteration": iteration,
        "status": status,
        "phases_found": phases_completed,
        "errors": errors
    }

if __name__ == "__main__":
    print("="*70)
    print("ORCHESTRATOR STRESS TEST")
    print("="*70)

    results = []
    for i in range(1, 4):
        try:
            result = run_orchestrator(i)
            results.append(result)
            print(f"  Result: {result['status']}")
        except subprocess.TimeoutExpired:
            print(f"  Result: TIMEOUT")
            results.append({
                "iteration": i,
                "status": "TIMEOUT",
                "phases_found": 0,
                "errors": ["timeout"]
            })
        except Exception as e:
            print(f"  Result: ERROR - {e}")
            results.append({
                "iteration": i,
                "status": f"ERROR: {e}",
                "phases_found": 0,
                "errors": [str(e)]
            })

    # Summary
    print("\n" + "="*70)
    print("STRESS TEST SUMMARY")
    print("="*70)

    all_errors = []
    for r in results:
        print(f"Run {r['iteration']}: {r['status']}")
        all_errors.extend(r['errors'])

    if all_errors:
        print(f"\nISSUES FOUND: {len(set(all_errors))} unique issues")
        for error in set(all_errors):
            print(f"  - {error}")
    else:
        print("\nNo errors found in stress test")

    print("\n" + "="*70)
