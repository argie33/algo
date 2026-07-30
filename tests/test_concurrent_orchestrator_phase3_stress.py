#!/usr/bin/env python3
"""Stress test: Run multiple orchestrators concurrently to find race conditions."""

import sys
import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.db.connection import get_db_connection


def run_orchestrator_subprocess(run_num: int, verbose: bool = False) -> dict:
    """Run orchestrator in subprocess and return results."""
    cmd = [
        sys.executable,
        str(project_root / "scripts" / "run_local_orchestrator.py"),
        "--afternoon",
        "--force",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(project_root),
        )
        return {
            "run_num": run_num,
            "exit_code": result.returncode,
            "stdout": result.stdout[-500:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "run_num": run_num,
            "exit_code": -1,
            "error": "TIMEOUT",
            "success": False,
        }
    except Exception as e:
        return {
            "run_num": run_num,
            "exit_code": -1,
            "error": str(e),
            "success": False,
        }


def test_concurrent_orchestrator_stress():
    """Run 5 orchestrators concurrently to stress test the system."""
    print("=" * 80)
    print("CONCURRENT ORCHESTRATOR STRESS TEST")
    print("=" * 80)
    print()

    # Start 5 orchestrator runs concurrently
    print("Starting 5 concurrent orchestrator runs...")
    start_time = datetime.now()

    results = []
    threads = []

    def run_thread(run_num):
        print(f"[{run_num}] Starting...")
        result = run_orchestrator_subprocess(run_num)
        results.append(result)
        status = "OK" if result['success'] else "FAILED"
        print(f"[{run_num}] {status}")

    # Start all threads at roughly the same time
    for i in range(5):
        t = threading.Thread(target=run_thread, args=(i+1,))
        t.start()
        threads.append(t)
        time.sleep(0.5)  # Slight stagger to avoid thundering herd

    # Wait for all to complete
    for t in threads:
        t.join()

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)

    passed = sum(1 for r in results if r['success'])
    failed = sum(1 for r in results if not r['success'])

    for result in sorted(results, key=lambda x: x['run_num']):
        status = "PASS" if result['success'] else "FAIL"
        print(f"  Run {result['run_num']}: {status}")
        if not result['success']:
            if 'error' in result:
                print(f"    Error: {result['error']}")
            if result.get('stderr'):
                print(f"    Stderr: {result['stderr'][:100]}")

    print()
    print(f"Total: {passed} passed, {failed} failed")
    print(f"Duration: {duration:.1f}s")
    print()

    # Check database for halted runs
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) as halted_count
            FROM orchestrator_execution_log
            WHERE run_date = CURRENT_DATE
                AND phases_halted > 0
                AND started_at > %s
        """, (start_time.replace(tzinfo=None),))

        result = cur.fetchone()
        if result:
            halted_in_test = result.get('halted_count', result[0]) if isinstance(result, dict) else result[0]
        else:
            halted_in_test = 0
        conn.close()

        print(f"Halted runs in database during this test: {halted_in_test}")
    except Exception as e:
        print(f"Warning: Could not check halted runs: {e}")

    # PASS if all runs completed (even if some are degraded)
    # FAIL if any run errored out
    assert passed == 5, f"Expected 5 successful runs, got {passed}/{5}"
    print("\n[PASS] STRESS TEST PASSED\n")


if __name__ == "__main__":
    test_concurrent_orchestrator_stress()
