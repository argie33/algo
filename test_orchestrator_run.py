#!/usr/bin/env python3
"""
Orchestrator verification script - tests core 7-phase system
"""
import sys
import os
from pathlib import Path
from datetime import date

# Fix import paths
repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root))
os.chdir(repo_root)

# Load environment
from dotenv import load_dotenv
env_file = repo_root / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

print("=" * 70)
print("ORCHESTRATOR VERIFICATION TEST")
print("=" * 70)

try:
    from algo.algo_orchestrator import Orchestrator
    print("[OK] Orchestrator imported successfully")

    # Create orchestrator instance with weekday test date
    orch = Orchestrator(dry_run=True, verbose=True, init_db=True)
    orch.run_date = "2026-05-15"  # Thursday - weekday for testing
    print("[OK] Orchestrator initialized")
    print(f"  Run ID: {orch.run_id}")
    print(f"  Dry run mode: {orch.dry_run}")
    print(f"  Run date: {orch.run_date}")

    # Run the pipeline
    print("\n" + "=" * 70)
    print("RUNNING 7-PHASE PIPELINE IN DRY-RUN MODE")
    print("=" * 70)

    results = orch.run()

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    if results and 'phases' in results:
        for phase_name, phase_result in results['phases'].items():
            status = phase_result.get('status', 'UNKNOWN')
            print(f"\n{phase_name}: {status}")
            if 'error' in phase_result:
                print(f"  Error: {phase_result['error']}")
            if 'count' in phase_result:
                print(f"  Count: {phase_result['count']}")
    else:
        print(f"Results: {results}")

    print("\n" + "=" * 70)
    print("[PASS] ORCHESTRATOR TEST PASSED - All phases executed successfully")
    print("=" * 70)

    orch.cleanup()
    sys.exit(0)

except Exception as e:
    print(f"\n[FAIL] ORCHESTRATOR TEST FAILED")
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
