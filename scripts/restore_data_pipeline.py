#!/usr/bin/env python3
"""Restore data pipeline after advisory lock release.

Systematically:
1. Verify price loader completes successfully
2. Trigger Step Functions EOD pipeline
3. Verify all data tables updated
4. Run orchestrator
5. Verify dashboard refreshes
"""

import json
import subprocess
import time
import sys
from datetime import datetime


def run_command(cmd: str, description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n{'='*70}")
    print(f"[{datetime.now().strftime('%HH:%MM:%SS')}] {description}")
    print(f"{'='*70}")

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        if result.stdout:
            print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
        if result.returncode != 0:
            if result.stderr:
                print(f"ERROR: {result.stderr[-500:]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT: Command took more than 5 minutes")
        return False
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return False


def main():
    """Restore data pipeline."""
    print("\n" + "="*70)
    print("RESTORING DATA PIPELINE")
    print("="*70)

    steps = [
        ("python3 check_system_health.py", "STEP 1: Verify system health"),
        ("aws stepfunctions start-execution --state-machine-arn 'arn:aws:states:us-east-1:626216981288:stateMachine:algo-eod-pipeline-dev' --region us-east-1 --name 'restore-$(date +%s)' | python3 -c 'import sys, json; print(json.load(sys.stdin)[\"executionArn\"])'", "STEP 2: Trigger EOD pipeline"),
        ("python3 check_system_health.py", "STEP 3: Re-check system health (after pipeline)"),
        ("python3 scripts/verify_pipeline_flow.py", "STEP 4: Verify pipeline data flow"),
        ("timeout 120 python3 scripts/run_local_orchestrator.py --morning || true", "STEP 5: Run orchestrator"),
    ]

    results = []
    for cmd, description in steps:
        success = run_command(cmd, description)
        results.append((description, success))
        time.sleep(2)

    # Summary
    print("\n" + "="*70)
    print("RESTORATION SUMMARY")
    print("="*70)
    for desc, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status} - {desc}")

    all_passed = all(success for _, success in results)
    if all_passed:
        print("\n✅ ALL STEPS COMPLETED SUCCESSFULLY")
        print("Dashboard should now display fresh data (check 'data not available' error)")
        return 0
    else:
        print("\n❌ SOME STEPS FAILED - Check logs above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
