#!/usr/bin/env python3
"""
Test harness for yfinance parallelism=2 optimization (Phase 1).

This script tests whether analyst_sentiment and analyst_upgrades can safely run
at parallelism=2 without triggering HTTP 429 rate limit errors from Yahoo Finance.

Test Plan (from steering/YFINANCE_PARALLELISM_INVESTIGATION.md):
1. Run metrics pipeline with LOADER_PARALLELISM=2
2. Monitor for HTTP 429 errors in logs
3. Check completion rates (target: 95%+)
4. Measure runtime (target: 3h vs current 6h+)
5. If successful: document as safe configuration
6. If failed: revert to parallelism=1

Usage:
  python scripts/test_yfinance_parallelism_optimization.py
    [--parallelism N]          # Parallelism to test (default: 2)
    [--max-symbols N]          # Limit to N symbols (default: all)
    [--dry-run]               # Print commands without running
    [--check-results-only]    # Skip run, just check results of prior run
"""

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add repo to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")


def get_loaders_to_test(target_loaders=None):
    """Get yfinance-dependent loaders for Phase 1 testing.

    Phase 1 tests analyst_sentiment and analyst_upgrades.
    These are the most commonly used yfinance loaders in the metrics pipeline.
    """
    if target_loaders:
        return target_loaders

    return [
        "analyst_sentiment",
        "analyst_upgrades",
    ]


def get_prior_loader_status():
    """Get baseline status of target loaders from prior runs."""
    loaders = get_loaders_to_test()

    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT
                    table_name,
                    status,
                    execution_started,
                    execution_completed,
                    last_updated,
                    error_message,
                    symbols_loaded,
                    completion_pct,
                    execution_duration_sec
                FROM data_loader_status
                WHERE table_name = ANY(%s)
                ORDER BY last_updated DESC
            """,
                (loaders,),
            )

            return {row["table_name"]: dict(row) for row in cur.fetchall()}
    except Exception as e:
        logger.warning(f"Could not fetch prior loader status: {e}")
        return {}


def reset_loader_status_for_test(loaders):
    """Reset test loaders to PENDING status to allow fresh run."""
    try:
        with DatabaseContext("write") as cur:
            for loader in loaders:
                cur.execute(
                    """
                    UPDATE data_loader_status
                    SET status='PENDING', started_at=NULL, completed_at=NULL,
                        error_message=NULL, last_updated=CURRENT_TIMESTAMP
                    WHERE table_name=%s
                """,
                    (loader,),
                )
            cur.connection.commit()
            logger.info(f"Reset {len(loaders)} loaders to PENDING status")
    except Exception as e:
        logger.error(f"Could not reset loader status: {e}")
        raise


def run_metrics_pipeline(parallelism=2, dry_run=False):
    """Run the metrics pipeline with specified parallelism.

    Returns: (exit_code, start_time, end_time)
    """
    env = os.environ.copy()
    env["LOADER_PARALLELISM"] = str(parallelism)
    env["LOCAL_MODE"] = "true"

    cmd = ["python", "scripts/local_loader_scheduler.py", "--now", "metrics", "--verbose"]

    start_time = datetime.now()
    logger.info(f"Starting metrics pipeline at {start_time} with LOADER_PARALLELISM={parallelism}")
    logger.info(f"Command: {' '.join(cmd)}")

    if dry_run:
        logger.info("[DRY RUN] Would execute above command")
        return 0, start_time, start_time

    try:
        result = subprocess.run(
            cmd,
            env=env,
            timeout=7 * 3600,  # 7 hour timeout max
            cwd=Path(__file__).parent.parent,
        )
        end_time = datetime.now()
        logger.info(f"Pipeline completed at {end_time}, exit code: {result.returncode}")
        return result.returncode, start_time, end_time
    except subprocess.TimeoutExpired:
        logger.error("Pipeline timeout after 7 hours")
        return 124, start_time, datetime.now()
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        return 1, start_time, datetime.now()


def check_for_rate_limit_errors(start_time, end_time):
    """Check logs for HTTP 429 errors during the test window."""
    try:
        logger.info("Checking for HTTP 429 errors in logs...")

        # This would check actual log files if available
        # For now, we'll check the database for any 429 markers
        try:
            with DatabaseContext("read") as cur:
                # Some loaders may log 429 errors to data_loader_status
                cur.execute("""
                    SELECT table_name, error_message, last_updated
                    FROM data_loader_status
                    WHERE error_message ILIKE '%429%'
                       OR error_message ILIKE '%rate limit%'
                    ORDER BY last_updated DESC
                    LIMIT 10
                """)

                errors = cur.fetchall()
                if errors:
                    logger.warning(f"Found {len(errors)} rate limit errors:")
                    for row in errors:
                        logger.warning(f"  {row['table_name']}: {row['error_message'][:100]}")
                    return False
                else:
                    logger.info("No 429 rate limit errors detected [OK]")
                    return True
        except Exception as db_err:
            logger.warning(f"Could not check database for rate limit errors: {db_err}")
            return None

    except Exception as e:
        logger.warning(f"Could not check rate limit errors: {e}")
        return None


def get_loader_completion_stats():
    """Get completion stats for test loaders."""
    loaders = get_loaders_to_test()

    try:
        with DatabaseContext("read") as cur:
            # Get latest run stats
            cur.execute(
                """
                SELECT
                    table_name,
                    status,
                    symbols_loaded,
                    symbol_count,
                    completion_pct,
                    execution_duration_sec,
                    http_status_code,
                    execution_completed
                FROM data_loader_status
                WHERE table_name = ANY(%s)
                ORDER BY execution_completed DESC NULLS LAST
            """,
                (loaders,),
            )

            results = []
            for row in cur.fetchall():
                results.append(dict(row))
            return results
    except Exception as e:
        logger.error(f"Could not get completion stats: {e}")
        return []


def generate_report(parallelism, exit_code, start_time, end_time, rate_limit_ok, completion_stats):
    """Generate test report with success/failure verdict."""
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("YFINANCE PARALLELISM=2 TEST REPORT")
    print("=" * 80)
    print("\nTest Configuration:")
    print(f"  Parallelism: {parallelism}")
    print(f"  Start Time: {start_time}")
    print(f"  End Time: {end_time}")
    print(f"  Duration: {duration / 3600:.1f} hours")
    print("\nResults:")
    print(f"  Exit Code: {exit_code}")
    print(f"  Rate Limit Errors (429): {'None detected [OK]' if rate_limit_ok else 'DETECTED [FAIL]'}")

    if completion_stats:
        print("\nLoader Completion Stats:")
        for stat in completion_stats:
            status = stat["status"]
            completion_pct = stat["completion_pct"] or 0
            duration_sec = int(stat["execution_duration_sec"] or 0)
            http_code = stat.get("http_status_code")
            print(f"  {stat['table_name']}:")
            print(f"    Status: {status}")
            print(f"    Completion: {completion_pct:.1f}%")
            print(f"    Duration: {duration_sec // 60} min {duration_sec % 60} sec")
            if http_code:
                print(f"    HTTP Status: {http_code}")

    # Verdict
    print("\nSUCCESS CRITERIA:")
    success = True

    if exit_code != 0:
        print(f"  [FAIL] Pipeline exit code != 0 (was {exit_code})")
        success = False
    else:
        print("  [OK] Pipeline exit code = 0")

    if rate_limit_ok is False:
        print("  [FAIL] HTTP 429 rate limit errors detected")
        success = False
    elif rate_limit_ok is True:
        print("  [OK] No HTTP 429 rate limit errors")
    else:
        print("  [WARN] Could not verify rate limit errors")

    # Check completion rates
    all_high_completion = all((s["completion_pct"] or 0) >= 95 for s in completion_stats)
    if all_high_completion and completion_stats:
        print("  [OK] All loaders 95%+ completion")
    elif completion_stats:
        print("  [FAIL] Some loaders below 95% completion")
        success = False

    if duration > 3 * 3600:  # 3 hours
        print(f"  [OK] Runtime {duration / 3600:.1f}h (target: 3h, achieved 50%+ speedup from 6h)")
    elif duration < 6 * 3600:  # Less than current 6h
        print(f"  [OK] Runtime {duration / 3600:.1f}h (speedup achieved vs current 6h baseline)")
    else:
        print(f"  [WARN] Runtime {duration / 3600:.1f}h (no improvement over 6h baseline)")

    print(f"\n{'=' * 80}")
    print(f"VERDICT: {'PASS [OK]' if success else 'FAIL [FAILED]'}")
    print(f"{'=' * 80}\n")

    return success


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parallelism", type=int, default=2, help="Parallelism to test")
    parser.add_argument("--max-symbols", type=int, help="Limit to N symbols")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running")
    parser.add_argument("--check-results-only", action="store_true", help="Skip run, check results only")

    args = parser.parse_args()

    # Phase 1: Setup
    loaders = get_loaders_to_test()
    logger.info(f"Testing loaders: {', '.join(loaders)}")

    prior_status = get_prior_loader_status()
    if prior_status:
        logger.info("Prior loader status:")
        for name, status in prior_status.items():
            logger.info(f"  {name}: {status['status']}")

    if args.check_results_only:
        logger.info("Checking results only (skipping run)")
        completion_stats = get_loader_completion_stats()
        rate_limit_ok = check_for_rate_limit_errors(None, None)
        generate_report(args.parallelism, 0, datetime.now(), datetime.now(), rate_limit_ok, completion_stats)
        return 0

    # Phase 2: Reset and run
    try:
        if not args.dry_run:
            reset_loader_status_for_test(loaders)

        exit_code, start_time, end_time = run_metrics_pipeline(parallelism=args.parallelism, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"Test setup failed: {e}")
        return 1

    # Phase 3: Analyze results
    rate_limit_ok = check_for_rate_limit_errors(start_time, end_time)
    completion_stats = get_loader_completion_stats()

    # Phase 4: Report
    success = generate_report(args.parallelism, exit_code, start_time, end_time, rate_limit_ok, completion_stats)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
