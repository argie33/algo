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

# CRITICAL: Load environment variables from .env.local BEFORE any boto3/AWS calls
from utils.dotenv_loader import load_env_local

load_env_local()

# Load Alpaca credentials from database (persistent storage, not files)
try:
    import sys
    from pathlib import Path
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    from scripts.load_credentials import ensure_credentials_loaded
    ensure_credentials_loaded()
except Exception as e:
    # Log but don't crash - credentials might come from environment
    import logging
    logging.getLogger(__name__).warning(f"[CREDS] Could not load credentials from database: {e}")


def _find_todays_run(run_type: str, run_date) -> dict | None:
    """Return the most recent orchestrator_execution_log row for this run_type/run_date, if any.

    Matches on run_id's "LOCAL-{TYPE}-" prefix (the format this script itself generates) rather
    than a dedicated run_type column, since that's what actually distinguishes morning/afternoon/
    evening runs in this table today.
    """
    try:
        from utils.db import DatabaseContext

        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT run_id, overall_status, started_at
                FROM orchestrator_execution_log
                WHERE run_date = %s AND run_id ILIKE %s
                ORDER BY started_at DESC LIMIT 1
                """,
                (run_date, f"LOCAL-{run_type.upper()}-%"),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {"run_id": row[0], "overall_status": row[1], "started_at": row[2]}
    except Exception as e:
        # Best-effort guard - if the check itself fails (e.g. table missing locally), don't
        # block the run over it; just proceed without the same-day protection this run.
        print(f"  WARNING: same-day run check failed ({type(e).__name__}: {e}) - proceeding without it")
        return None


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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if this run_type already ran today. Nothing guards against running "
        "--morning/--afternoon/--evening multiple times for the same trading day by default - "
        "unlike EventBridge in AWS (which fires each exactly once), so repeated manual re-runs "
        "re-execute entry/exit/reconciliation against the same day's already-processed state, "
        "producing duplicate-looking trades and oscillating portfolio snapshots. Use --force only "
        "for deliberate re-testing after a real code fix, not as a way to retry past a halt/error.",
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
    # CRITICAL: Force paper trading for this local-dev entry point, matching every other
    # local launcher (start_dashboard_dev.py, run_dev_pipeline.py, start_dev.py,
    # dev_environment_setup.py). Without this, ALPACA_PAPER_TRADING falls through to
    # whatever the ambient shell happens to have - algo/infrastructure/config/main.py and
    # executor_strategies.py both default "unset" to paper, but an explicit "false" left
    # over in the shell environment (e.g. from a prior session) would silently flip live,
    # and this script - unlike its siblings - had no override. GOVERNANCE.md states paper
    # trading as a non-negotiable local/dev invariant; this script must enforce it, not
    # merely default to it.
    os.environ["ALPACA_PAPER_TRADING"] = "true"
    # NOTE: SKIP_ORCHESTRATOR_LOCK removed - distributed lock prevents concurrent execution and duplicate trades

    et = ZoneInfo("America/New_York")
    now = datetime.now(et)

    print("=" * 70)
    print("LOCAL ORCHESTRATOR RUNNER")
    print("=" * 70)
    print(f"Current time (ET): {now}")
    print(f"Runs to execute: {', '.join(runs)}\n")

    for run_type in runs:
        if not args.force:
            prior_run = _find_todays_run(run_type, now.date())
            if prior_run is not None:
                print(f"Skipping {run_type.upper()}: already ran today.")
                print(f"  Prior run: {prior_run['run_id']} (status={prior_run['overall_status']}, "
                      f"started {prior_run['started_at']})")
                print("  Re-running the same trading day re-executes entry/exit/reconciliation "
                      "against already-processed state and produces confusing duplicate-looking "
                      "trades and oscillating portfolio snapshots. Pass --force to override.")
                continue

        print(f"Starting {run_type.upper()} orchestrator run...")

        # Import and run orchestrator module
        try:
            from algo.infrastructure.config import get_config
            from algo.orchestration.orchestrator import Orchestrator

            # Generate run_id with microseconds to ensure uniqueness across rapid runs
            run_id = f"LOCAL-{run_type.upper()}-{now.strftime('%Y%m%d-%H%M%S')}-{now.microsecond:06d}"

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
