#!/usr/bin/env python3
"""
Comprehensive pipeline diagnostic to identify actual runtime issues.
Exercises all 7 phases without executing trades (dry-run mode).
"""

import sys
from pathlib import Path
from datetime import datetime, date as _date
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

sys.path.insert(0, str(Path(__file__).parent))

from algo_config import get_config
from algo_orchestrator import Orchestrator

def run_diagnostics():
    """Run full pipeline with diagnostics enabled."""
    print("\n" + "=" * 70)
    print("ALGO PIPELINE COMPREHENSIVE DIAGNOSTICS")
    print("=" * 70 + "\n")

    config = get_config()
    orchestrator = Orchestrator(config=config, run_date=_date.today(), dry_run=True, verbose=True)

    try:
        # Run all 7 phases
        print("Starting full orchestration...")
        orchestrator.run()

        # Print phase results
        print("\n" + "=" * 70)
        print("PHASE RESULTS")
        print("=" * 70)
        for phase_name, result in orchestrator.phase_results.items():
            print(f"\n{phase_name}:")
            if isinstance(result, dict):
                for k, v in result.items():
                    if k != 'details':
                        print(f"  {k}: {v}")
            else:
                print(f"  {result}")

        print("\n" + "=" * 70)
        print("PIPELINE STATUS: SUCCESS - All phases completed")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\nERROR: Pipeline failed with: {e}")
        import traceback
        traceback.print_exc()
        print("\n" + "=" * 70)
        print("PIPELINE STATUS: FAILED")
        print("=" * 70 + "\n")
        return False

if __name__ == '__main__':
    success = run_diagnostics()
    sys.exit(0 if success else 1)
