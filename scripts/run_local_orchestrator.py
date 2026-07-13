#!/usr/bin/env python3
"""Run orchestrator locally (for development without AWS Lambda/EventBridge).

This script runs the orchestrator directly in LOCAL_MODE, bypassing AWS Lambda.
Useful when developing locally with --local flag on the dashboard.

Usage:
  python scripts/run_local_orchestrator.py              # runs morning orchestrator
  python scripts/run_local_orchestrator.py --afternoon   # runs afternoon orchestrator
  python scripts/run_local_orchestrator.py --evening     # runs evening orchestrator
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run orchestrator locally (development mode)",
    )
    parser.add_argument(
        "--morning",
        action="store_true",
        help="Run morning orchestrator (9:30 AM ET)",
    )
    parser.add_argument(
        "--afternoon",
        action="store_true",
        help="Run afternoon orchestrator (1:00 PM ET)",
    )
    parser.add_argument(
        "--evening",
        action="store_true",
        help="Run evening orchestrator (5:30 PM ET)",
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help="Run all orchestrator times (morning + afternoon + evening)",
    )

    args = parser.parse_args()

    # Default to morning if no specific time requested
    runs = []
    if args.run_all:
        runs = ["morning", "afternoon", "evening"]
    elif args.afternoon:
        runs = ["afternoon"]
    elif args.evening:
        runs = ["evening"]
    else:
        runs = ["morning"]  # default

    # Set LOCAL_MODE for direct database access
    os.environ["LOCAL_MODE"] = "true"
    os.environ["ENVIRONMENT"] = "development"

    et = ZoneInfo("America/New_York")
    now = datetime.now(et)

    print("=" * 70)
    print("LOCAL ORCHESTRATOR RUNNER")
    print("=" * 70)
    print(f"Current time (ET): {now}")
    print(f"Runs to execute: {', '.join(runs)}\n")

    for run_type in runs:
        print(f"Starting {run_type.upper()} orchestrator run...")

        # Import and run orchestrator module
        try:
            from algo.orchestration.orchestrator import Orchestrator
            from algo.config.orchestrator_config import OrchestratorConfig

            # Generate run_id
            run_id = f"LOCAL-{run_type.upper()}-{now.strftime('%Y%m%d-%H%M%S')}"

            print(f"  Run ID: {run_id}")
            print(f"  Mode: paper (local development)")

            # Create and run orchestrator instance
            orchestrator_instance = Orchestrator(
                config=OrchestratorConfig,
                run_id=run_id,
                dry_run=False,
            )
            result = orchestrator_instance.run()

            if result and result.get("overall_status") == "success":
                print(f"  Status: ✓ COMPLETED")
            else:
                print(f"  Status: ✗ FAILED or HALTED")
                if result:
                    print(f"  Details: {result.get('overall_status')}")

        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print("Orchestrator execution complete. Check database for updated data.")
    print("=" * 70)

if __name__ == "__main__":
    main()
