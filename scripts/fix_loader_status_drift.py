#!/usr/bin/env python3
"""Fix loader status drift - resolve PENDING loaders and ensure proper execution.

This script addresses the issue where loaders have fresh data but stuck PENDING status,
or have consecutive failures but no proper error tracking. It:

1. Detects and recovers stale RUNNING loaders (>30 min with no progress)
2. Cleans up stale lock files
3. Resets loaders with fixable failures
4. Ensures PENDING loaders are ready to execute
5. Validates dependencies before allowing loaders to run
"""

import argparse
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"
if "LOADER_PARALLELISM" not in os.environ:
    os.environ["LOADER_PARALLELISM"] = "1"

from utils.db.connection import get_db_connection
from utils.loaders.status_manager import LoaderStatusManager


def fix_stuck_running_loaders(cur: Any, stale_threshold_minutes: int | None = None) -> list[str]:
    """Detect and fix loaders genuinely stuck RUNNING, using each table's own configured
    loader timeout rather than one flat threshold for every table.

    ROOT-CAUSE FIX 2026-08-16: the flat `stale_threshold_minutes` this function used to take
    (5 by default, 30 from this script's own main()) has no relationship to how long a real
    loader run is allowed to take - CLAUDE.md itself documents per-loader timeouts up to
    540 minutes (company_info_sec) and 1440 minutes (prices). Live-confirmed: company_info_sec
    was marked FAILED here after only ~19 minutes of a legitimately still-running, healthy
    ~45-70 minute backfill (process alive, log actively growing, real per-symbol progress the
    whole time) - the exact "genuinely healthy but declared stuck" false positive this
    function's own docstring claimed couldn't happen ("5 minutes is conservative... normal
    slow loaders won't be affected" - false for any of this codebase's many 30+ minute
    loaders). `utils/loaders/status_manager.py`'s `reap_stale_running_loaders()` already solves
    this correctly (per-loader timeout * 1.25 safety margin, via `get_loader_timeout()`) -
    delegate to it instead of maintaining a second, less-safe implementation here.

    `stale_threshold_minutes` is now ignored (kept only for call-site backward compatibility)
    - real per-loader timeouts always take precedence.
    """
    from utils.loaders.status_manager import reap_stale_running_loaders

    return reap_stale_running_loaders()


def clean_stale_locks(max_age_hours: int = 2) -> list[str]:
    """Remove lock files older than max_age_hours (assume process crashed).

    Loader processes create .lock files and should clean them on exit. Files
    older than the max age almost certainly indicate a crashed process.
    """
    cleaned: list[str] = []
    lock_dir = Path(tempfile.gettempdir()) / "algo-locks"
    if not lock_dir.exists():
        return cleaned

    now = datetime.now()
    for lock_file in lock_dir.glob("*.lock"):
        if not lock_file.is_file():
            continue

        mtime = datetime.fromtimestamp(lock_file.stat().st_mtime)
        age_hours = (now - mtime).total_seconds() / 3600

        if age_hours > max_age_hours:
            loader_name = lock_file.stem
            print(f"[LOCK] Removing stale lock for {loader_name} (age: {age_hours:.1f}h)")
            try:
                lock_file.unlink()
                cleaned.append(loader_name)
            except Exception as e:
                print(f"[LOCK] ERROR removing {lock_file}: {e}", file=sys.stderr)

    return cleaned


def validate_dependency_data(
    loader: str,
    dependencies: dict[str, list[str]],
    cur: Any,  # Use existing cursor
) -> tuple[bool, str | None]:
    """Check if a loader's dependencies have fresh data.

    Returns (is_ready, error_message)
    """
    deps = dependencies.get(loader, [])
    if not deps:
        return True, None

    for dep_loader in deps:
        # Get the primary table for this dependency loader
        cur.execute(
            """
            SELECT table_name, status, latest_date, age_days
            FROM data_loader_status
            WHERE table_name = %s
        """,
            (dep_loader,),
        )

        row = cur.fetchone()
        if not row:
            return False, f"Dependency {dep_loader} not found in status table"

        _dep_table, dep_status, _dep_date, age_days = row

        # Dependency must be COMPLETED or HEALTHY, and fresh (<=1 day old for most)
        if dep_status not in ("COMPLETED", "HEALTHY"):
            return False, f"Dependency {dep_loader} status is {dep_status}, need COMPLETED/HEALTHY"

        if age_days and age_days > 2:
            return False, f"Dependency {dep_loader} data is {age_days} days old (max: 2 days)"

    return True, None


def reset_fixable_pending_loaders(
    dependencies: dict[str, list[str]],
    cur: Any,  # Use existing cursor instead of creating new connection
) -> list[str]:
    """Reset PENDING loaders with 0-1 failures that can be retried.

    Loaders with 3+ consecutive failures need manual investigation.
    """
    reset = []

    # Get PENDING loaders with 0-1 failures
    cur.execute("""
        SELECT table_name, consecutive_failures
        FROM data_loader_status
        WHERE status = 'PENDING'
        AND (consecutive_failures IS NULL OR consecutive_failures < 3)
        ORDER BY table_name
    """)

    for table_name, consec_fail in cur.fetchall():
        # Check if dependencies are ready
        is_ready, dep_error = validate_dependency_data(table_name, dependencies, cur)

        if not is_ready:
            print(f"[RESET] SKIP {table_name}: dependencies not ready - {dep_error}")
            continue

        # Reset to FAILED so next run can retry it
        error_msg = f"[FIX_SCRIPT] Reset from PENDING: Ready to retry. Previous consecutive_failures={consec_fail}."
        print(f"[RESET] Enabling {table_name} for retry...")
        try:
            # Mark as FAILED (not PENDING) so it will retry on next pipeline run
            LoaderStatusManager(table_name).mark_failed(error_msg)
            reset.append(table_name)
        except Exception as e:
            print(f"[RESET] ERROR resetting {table_name}: {e}", file=sys.stderr)

    return reset


def main() -> int:
    # BUG FIX 2026-08-17: this script had zero argument parsing, so `--help` (or any typo'd
    # flag) was silently ignored and fell straight through to the real repair below - an
    # operator checking usage before running it against prod-adjacent data_loader_status would
    # instead reap RUNNING loaders and reset PENDING ones for real. argparse's own -h/--help
    # exits before any of that runs.
    argparse.ArgumentParser(
        description="Detect and repair loader status drift: reap stale RUNNING rows, "
        "clean stale lock files, and reset fixable PENDING loaders in data_loader_status. "
        "Always performs the repair live - there is no dry-run mode."
    ).parse_args()

    print("=" * 80)
    print("LOADER STATUS DRIFT FIX")
    print("=" * 80)

    # Dependency map from local_loader_scheduler.py
    loader_dependencies = {
        "value_quality_growth": ["financial_statements", "valuations", "analyst_earnings_estimates"],
        "enhanced_quality_growth": ["value_quality_growth"],
        "segment_metrics": ["segment_info"],
        "buy_sell_daily": ["prices", "technical"],
        "stock_scores": ["value_quality_growth", "enhanced_quality_growth", "stability_metrics"],
        "signal_quality": ["buy_sell_daily"],
        "algo": ["signal_quality", "stock_scores"],
    }

    with get_db_connection() as conn:
        cur = conn.cursor()

        print("\n1. Detecting stuck RUNNING loaders...")
        stuck = fix_stuck_running_loaders(cur, stale_threshold_minutes=30)
        if stuck:
            print(f"   Fixed: {', '.join(stuck)}")
        else:
            print("   None found")

        print("\n2. Cleaning stale lock files...")
        locks = clean_stale_locks(max_age_hours=2)
        if locks:
            print(f"   Removed: {', '.join(locks)}")
        else:
            print("   None found")

        print("\n" + "=" * 80)
        print("STATUS SUMMARY")
        print("=" * 80)

        print("\n3. Resetting fixable PENDING loaders...")
        reset = reset_fixable_pending_loaders(loader_dependencies, cur)
        if reset:
            print(f"   Reset: {', '.join(reset)}")
        else:
            print("   None reset (all have blocking dependencies or 3+ failures)")

        # Show status of the key loaders
        loaders_to_check = [
            "buy_sell_daily",
            "company_info_sec",
            "company_profile",
            "growth_metrics",
            "quality_metrics",
            "sec_valuations",
            "value_quality_growth",
            "enhanced_quality_growth",
        ]

        cur.execute(
            """
            SELECT table_name, status, consecutive_failures, latest_date, age_days
            FROM data_loader_status
            WHERE table_name = ANY(%s)
            ORDER BY table_name
        """,
            (loaders_to_check,),
        )

        print(f"\n{'Loader':<35} {'Status':<12} {'Fail#':>5} {'Data Age':>8}")
        print("-" * 70)

        for row in cur.fetchall():
            if row:
                table_name, status, consec_fail, latest_date, age_days = row
                date_str = latest_date.strftime("%m-%d") if latest_date else "N/A"
                age_str = f"{age_days}d" if age_days else "N/A"
                print(f"{table_name:<35} {status:<12} {consec_fail or 0:>5} {age_str:>8} ({date_str})")

        print("\nFix complete. Ready to run next pipeline.\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
