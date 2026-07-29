#!/usr/bin/env python3
"""
Orchestrator stability test - run multiple times to catch hangs/deadlocks.
"""

import subprocess
import time
import sys

def run_orchestrator_test(run_num: int, timeout_secs: int = 300) -> tuple[bool, float]:
    """Run orchestrator in dry-run mode, return (success, elapsed_time)."""
    print(f"\n{'='*70}")
    print(f"RUN {run_num}: Starting orchestrator test (timeout: {timeout_secs}s)")
    print(f"{'='*70}")

    start = time.time()
    try:
        result = subprocess.run(
            ["python", "scripts/run_local_orchestrator.py", "--evening", "--force"],
            env={**dict(os.environ), "ORCHESTRATOR_DRY_RUN": "true"},
            timeout=timeout_secs,
            capture_output=True,
            text=True,
        )
        elapsed = time.time() - start

        # Check for success markers in output
        success_markers = [
            "Orchestrator execution complete",
            "Phase 9 success",
        ]

        has_markers = all(m in result.stdout + result.stderr for m in success_markers)

        if result.returncode == 0 and has_markers:
            print(f"[PASS] in {elapsed:.1f}s")
            return True, elapsed
        else:
            print(f"[FAIL] in {elapsed:.1f}s (exit code: {result.returncode})")
            print("STDOUT:", result.stdout[-500:] if result.stdout else "(empty)")
            print("STDERR:", result.stderr[-500:] if result.stderr else "(empty)")
            return False, elapsed
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - start
        print(f"[TIMEOUT] after {elapsed:.1f}s (orchestrator hung)")
        return False, elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"[ERROR] after {elapsed:.1f}s: {e}")
        return False, elapsed

if __name__ == "__main__":
    import os

    num_runs = 3
    timeout = 300

    results = []
    for i in range(1, num_runs + 1):
        success, elapsed = run_orchestrator_test(i, timeout)
        results.append((success, elapsed))
        time.sleep(2)  # Brief pause between runs

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    passed = sum(1 for s, _ in results if s)
    print(f"Passed: {passed}/{num_runs}")
    for i, (success, elapsed) in enumerate(results, 1):
        status = "[PASS]" if success else "[FAIL]"
        print(f"  Run {i}: {status} ({elapsed:.1f}s)")

    # Check for hangs
    hangs = sum(1 for s, e in results if not s and e >= timeout - 5)
    if hangs > 0:
        print(f"\n[WARN] {hangs} run(s) timed out - orchestrator may be hanging!")
        sys.exit(1)
    elif passed == num_runs:
        print(f"\n[SUCCESS] All {num_runs} runs passed - orchestrator is stable")
        sys.exit(0)
    else:
        print(f"\n[WARN] {num_runs - passed} run(s) failed")
        sys.exit(1)
