#!/usr/bin/env python3
"""Run orchestrator locally (for development without AWS Lambda/EventBridge).

This script runs the orchestrator directly in LOCAL_MODE, bypassing AWS Lambda.
Useful when developing locally with --local flag on the dashboard.

Usage:
  python scripts/run_local_orchestrator.py              # runs morning orchestrator
  python scripts/run_local_orchestrator.py --afternoon   # runs afternoon orchestrator
  python scripts/run_local_orchestrator.py --evening     # runs evening orchestrator
"""

import argparse
import os
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
            from algo.infrastructure.config import get_config
            from algo.orchestration.orchestrator import Orchestrator

            # Generate run_id
            run_id = f"LOCAL-{run_type.upper()}-{now.strftime('%Y%m%d-%H%M%S')}"

            print(f"  Run ID: {run_id}")
            print("  Mode: paper (local development)")

            # Get AlgoConfig singleton (required for WeightOptimizer.get/set methods)
            config = get_config()
            config.set("execution_mode", "paper", "string")  # Always use paper trading for local dev

            # Create and run orchestrator instance
            # Support ORCHESTRATOR_DRY_RUN env var for local development/testing
            # Bypasses Phase 1 staleness checks when data is being loaded
            dry_run = os.getenv("ORCHESTRATOR_DRY_RUN", "").lower() in ("1", "true", "yes")

            orchestrator_instance = Orchestrator(
                config=config,
                run_id=run_id,
                dry_run=dry_run,
            )
            result = orchestrator_instance.run()

            # run() returns {success, halted, skipped, reason, phases, run_date} - there is no
            # "overall_status" key (that's a separate local variable inside run(), only used for
            # the DB execution log). Checking for it here always evaluated to None == "success",
            # so this printed "FAILED or HALTED" on every run regardless of actual outcome.
            # Check "halted" before "success": a run can halt (e.g. circuit breakers) without any
            # phase erroring, so success=True and halted=True can both be set simultaneously -
            # halted is the more specific, more important state to surface.
            if result and result.get("halted"):
                print("  Status: HALTED")
                print(f"  Reason: {result.get('reason')}")
            elif result and result.get("success"):
                print("  Status: OK - COMPLETED")
            else:
                print("  Status: FAILED")
                if result:
                    print(f"  Details: {result}")

        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 70)
    print("Orchestrator execution complete. Check database for updated data.")
    print("=" * 70)


if __name__ == "__main__":
    main()
