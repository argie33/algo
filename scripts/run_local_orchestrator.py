#!/usr/bin/env python3
"""Run orchestrator locally (for development without AWS Lambda/EventBridge).

This script runs the orchestrator directly in LOCAL_MODE, bypassing AWS Lambda.
Useful when developing locally with --local flag on the dashboard.

Usage:
  python scripts/run_local_orchestrator.py              # runs morning orchestrator
  python scripts/run_local_orchestrator.py --afternoon   # runs afternoon orchestrator
  python scripts/run_local_orchestrator.py --preclose    # runs pre-close orchestrator
  python scripts/run_local_orchestrator.py --evening     # runs evening orchestrator

Production actually schedules 4 sessions (terraform/modules/services/2x-daily-orchestrator.tf):
morning 9:30 AM ET, afternoon 1:00 PM ET, preclose 3:00 PM ET, evening 5:30 PM ET. Per
lambda/algo_orchestrator/lambda_function.py's LIVE_TRADING_RUN_IDENTIFIERS/
MONITOR_ONLY_RUN_IDENTIFIERS, morning/afternoon/preclose submit real (paper or live) orders;
evening is monitor-only (dry_run=True) - it doesn't place new entries. This script mirrors
that mapping below so --evening locally behaves like the real evening run, not like another
live-trading session with a different label.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# CRITICAL: Load environment variables from .env.local BEFORE any boto3/AWS calls
from utils.dotenv_loader import load_env_local

load_env_local()

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load Alpaca credentials from database (persistent storage, not files)
try:
    from scripts.load_credentials import ensure_credentials_loaded

    ensure_credentials_loaded()
except Exception as e:
    # Log but don't crash - credentials might come from environment
    import logging

    logging.getLogger(__name__).warning(f"[CREDS] Could not load credentials from database: {e}")

# `lambda` is a Python reserved word, so `lambda.algo_orchestrator.lambda_function` can't be
# imported as a dotted package path - add the directory to sys.path and import the bare module
# name instead (same trick lambda/api/dev_server.py uses for its own lambda_function.py).
# Reuses the real production run_identifier -> dry_run mapping rather than keeping a second,
# driftable copy here.
sys.path.insert(0, str(project_root / "lambda" / "algo_orchestrator"))
from lambda_function import (  # noqa: E402
    LIVE_TRADING_RUN_IDENTIFIERS,
    MONITOR_ONLY_RUN_IDENTIFIERS,
)


def _check_loader_freshness(run_type: str, now) -> None:
    """Check if required loaders have run today and warn if not.

    SESSION 107 FIX: Extracted from main() to reduce complexity (C901).
    """
    if run_type != "morning":
        return

    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext("read") as cur:
            # Check if morning pipeline loaders have run today (prices, technical, market_status, etc.)
            cur.execute(
                """
                SELECT COUNT(*) FROM data_loader_status
                WHERE table_name IN ('price_daily', 'technical_data_daily', 'market_health_daily')
                  AND DATE(last_updated) = %s
                  AND status = 'COMPLETED'
                """,
                (now.date(),),
            )
            morning_loaders_count = cur.fetchone()[0]

            # Check if metrics pipeline has run today (value_metrics, quality_metrics, etc.)
            cur.execute(
                """
                SELECT COUNT(*) FROM data_loader_status
                WHERE table_name IN ('value_metrics', 'quality_metrics', 'growth_metrics', 'stability_metrics')
                  AND DATE(last_updated) = %s
                  AND status = 'COMPLETED'
                """,
                (now.date(),),
            )
            metrics_loaders_count = cur.fetchone()[0]

            # Check if signals pipeline has run today (stock_scores, buy_sell_daily)
            cur.execute(
                """
                SELECT COUNT(*) FROM data_loader_status
                WHERE table_name IN ('stock_scores', 'buy_sell_daily')
                  AND DATE(last_updated) = %s
                  AND status = 'COMPLETED'
                """,
                (now.date(),),
            )
            signals_loaders_count = cur.fetchone()[0]

        if morning_loaders_count < 3:
            print(f"  ⚠️  WARNING: MORNING pipeline incomplete ({morning_loaders_count}/3 loaders ran today)")
            print("     Run before orchestrator: python scripts/local_loader_scheduler.py --now morning")
        if metrics_loaders_count < 4:
            print(f"  ⚠️  WARNING: METRICS pipeline incomplete ({metrics_loaders_count}/4 loaders ran today)")
            print("     Run before orchestrator: python scripts/local_loader_scheduler.py --now metrics")
        if signals_loaders_count < 2:
            print(f"  ⚠️  WARNING: SIGNALS pipeline incomplete ({signals_loaders_count}/2 loaders ran today)")
            print("     Run before orchestrator: python scripts/local_loader_scheduler.py --now signals")
    except Exception as loader_check_err:
        # Non-critical check - don't block orchestrator on check failure
        print(
            f"  Note: Could not check loader freshness ({type(loader_check_err).__name__}). Proceeding with orchestrator."
        )


def _find_todays_run(run_type: str, run_date) -> dict | None:
    """Return the most recent orchestrator_execution_log row for this run_type/run_date, if any.

    CRITICAL FIX: Check DATE(started_at) instead of run_date. Runs that start late on one
    calendar day (e.g. 22:00 ET) have run_date from the PREVIOUS trading day but actually
    execute into the next calendar day. Without this fix, the deduplication check fails
    and allows re-runs of the same session (causing the 67+ duplicate afternoon runs issue).

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
                WHERE DATE(started_at) = %s AND run_id ILIKE %s
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
        "--preclose",
        action="store_true",
        help="Run pre-close orchestrator (3:00 PM ET, live-trading, SLA: finish by 3:15 PM ET)",
    )
    parser.add_argument(
        "--evening",
        action="store_true",
        help="Run evening orchestrator (5:30 PM ET, monitor-only - does not place new entries)",
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help="Run all orchestrator times (morning + afternoon + preclose + evening)",
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
    parser.add_argument(
        "--date",
        type=str,
        help="Simulate orchestrator run for a specific date (YYYY-MM-DD). Useful for testing fixes on trading days. "
        "Example: --date 2026-08-07 --morning",
    )

    args = parser.parse_args()

    # Default to morning if no specific time requested
    runs = []
    if args.run_all:
        runs = ["morning", "afternoon", "preclose", "evening"]
    elif args.afternoon:
        runs = ["afternoon"]
    elif args.preclose:
        runs = ["preclose"]
    elif args.evening:
        runs = ["evening"]
    else:
        runs = ["morning"]  # default

    # Set LOCAL_MODE for direct database access
    os.environ["LOCAL_MODE"] = "true"
    os.environ["ENVIRONMENT"] = "development"
    # CRITICAL: Force paper trading for this local-dev entry point, matching every other
    # local launcher (lambda/api/dev_server.py, python -m dashboard --local). Without this,
    # ALPACA_PAPER_TRADING falls through to
    # whatever the ambient shell happens to have - algo/infrastructure/config/main.py and
    # executor_strategies.py both default "unset" to paper, but an explicit "false" left
    # over in the shell environment (e.g. from a prior session) would silently flip live,
    # and this script - unlike its siblings - had no override. GOVERNANCE.md states paper
    # trading as a non-negotiable local/dev invariant; this script must enforce it, not
    # merely default to it.
    os.environ["ALPACA_PAPER_TRADING"] = "true"
    # NOTE: SKIP_ORCHESTRATOR_LOCK removed - distributed lock prevents concurrent execution and duplicate trades

    et = ZoneInfo("America/New_York")

    # Parse --date if provided (for testing historical/simulated runs)
    if args.date:
        from datetime import datetime as dt_cls

        try:
            test_date = dt_cls.strptime(args.date, "%Y-%m-%d").date()
            # Create a datetime at 12:00 PM ET on the specified date for run_id consistency
            now = datetime(test_date.year, test_date.month, test_date.day, 12, 0, 0, tzinfo=et)
            print(f"[TEST MODE] Using simulated date: {test_date} (run_id will show this date)")
        except ValueError:
            print(f"ERROR: Invalid date format '{args.date}'. Use YYYY-MM-DD (e.g., 2026-08-07)")
            sys.exit(1)
    else:
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
                print(
                    f"  Prior run: {prior_run['run_id']} (status={prior_run['overall_status']}, "
                    f"started {prior_run['started_at']})"
                )
                print(
                    "  Re-running the same trading day re-executes entry/exit/reconciliation "
                    "against already-processed state and produces confusing duplicate-looking "
                    "trades and oscillating portfolio snapshots. Pass --force to override."
                )
                continue

        print(f"Starting {run_type.upper()} orchestrator run...")
        _check_loader_freshness(run_type, now)

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
            dry_run_override = os.environ.get("ORCHESTRATOR_DRY_RUN")
            if run_type in MONITOR_ONLY_RUN_IDENTIFIERS:
                # CRITICAL SAFETY: --evening/monitor-only MUST always be dry_run=True.
                # ORCHESTRATOR_DRY_RUN env var can only override to enable dry_run, never to disable it.
                # An ambient ORCHESTRATOR_DRY_RUN=false (leftover from testing) must not silently
                # override --evening's documented "always monitor-only" guarantee.
                # Previously (2026-07-28): shell with ORCHESTRATOR_DRY_RUN=false caused --evening to submit
                # real (paper) orders instead of monitor-only. FIXED: now dry_run=True is enforced.
                # WARNING: If ORCHESTRATOR_DRY_RUN defeats the monitor-only guarantee, log it
                if dry_run_override is not None and dry_run_override.lower() not in ("1", "true", "yes"):
                    print(
                        f"  WARNING: ORCHESTRATOR_DRY_RUN env var '{dry_run_override}' would disable monitor-only "
                        f"for --{run_type}, but safety override forces dry_run=True.",
                        file=sys.stderr,
                    )
                dry_run = True
            elif dry_run_override is not None:
                # For LIVE_TRADING runs, respect explicit ORCHESTRATOR_DRY_RUN override
                dry_run = dry_run_override.lower() in ("1", "true", "yes")
                if dry_run:
                    # WARNING: An ambient ORCHESTRATOR_DRY_RUN=true (e.g. left over in the shell
                    # from earlier manual testing, or from tests/conftest.py's os.environ set)
                    # silently turns a --morning/--afternoon/--preclose run into a no-op: Phase 6
                    # reports "DRY-RUN: execution skipped" and no real stop-raise/exit executes,
                    # with no other signal that this run type wasn't supposed to be dry-run.
                    # 2026-08-03: this happened repeatedly across a day's runs, discovered only
                    # by manually diffing orchestrator_execution_log after the fact.
                    print(
                        f"  WARNING: ORCHESTRATOR_DRY_RUN env var '{dry_run_override}' is forcing "
                        f"dry-run for --{run_type}, a live-trading run type. No real orders will "
                        f"execute this run. Unset ORCHESTRATOR_DRY_RUN if this is unintended.",
                        file=sys.stderr,
                    )
            elif run_type in LIVE_TRADING_RUN_IDENTIFIERS:
                dry_run = False
            else:
                raise ValueError(
                    f"run_type '{run_type}' is in neither LIVE_TRADING_RUN_IDENTIFIERS nor "
                    "MONITOR_ONLY_RUN_IDENTIFIERS - add it to one in lambda_function.py."
                )

            orchestrator_instance = Orchestrator(
                config=config,
                run_id=run_id,
                run_date=now.date(),
                dry_run=dry_run,
            )
            result = orchestrator_instance.run()

            # run() returns {success, halted, skipped, reason, phases, run_date}
            # Status hierarchy: HALTED > DEGRADED > OK > FAILED
            # - HALTED: Circuit breaker or error occurred
            # - DEGRADED: Some phases skipped/degraded but run continued (e.g., dry_run, market hours)
            # - OK: All phases succeeded
            # - FAILED: Unknown error
            if result and result.get("halted"):
                print("  Status: HALTED")
                print(f"  Reason: {result.get('reason')}")
            elif result and result.get("success"):
                print("  Status: OK")
            elif result and result.get("skipped") and not result.get("halted"):
                # Skipped but not halted = degraded (graceful skip like market hours or dry_run)
                print("  Status: DEGRADED")
                print(f"  Reason: {result.get('reason')}")
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
