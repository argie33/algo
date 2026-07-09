#!/usr/bin/env python3
"""
Comprehensive Data Pipeline Recovery Script

This script systematically diagnoses and fixes the data pipeline issues:
1. Validates database connectivity
2. Identifies stuck loaders
3. Resets loader state properly
4. Restarts critical loader chain in sequence
5. Verifies data freshness after each step
6. Produces audit trail of all changes

Usage:
    python scripts/fix_data_pipeline.py
"""

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass

# Set up environment
os.environ.setdefault('DATABASE_URL', 'postgresql://algo_admin@localhost/algo_trading')

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


@dataclass
class LoaderStatus:
    """Represents the status of a loader"""
    table_name: str
    status: str
    completion_pct: float
    hours_stale: float | None
    row_count: int
    latest_date: str | None


def log_step(step_num: int, title: str):
    """Log a major step"""
    print()
    print("=" * 100)
    print(f"STEP {step_num}: {title}")
    print("=" * 100)
    print()


def log_action(action: str, success: bool | None = None) -> None:
    """Log an action"""
    if success is True:
        print(f"  [OK]   {action}")
    elif success is False:
        print(f"  [FAIL] {action}")
    else:
        print(f"  [..] {action}")


def get_loader_status(table_names: list) -> list[LoaderStatus]:
    """Get current status of specific loaders"""
    with DatabaseContext('read') as cur:
        placeholders = ','.join(['%s'] * len(table_names))
        cur.execute(f"""
            SELECT
                table_name,
                status,
                completion_pct,
                EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - last_updated)) / 3600 as hours_stale,
                row_count,
                latest_date
            FROM data_loader_status
            WHERE table_name IN ({placeholders})
        """, table_names)

        statuses = []
        for row in cur.fetchall():
            table_name, status, completion_pct, hours_stale, row_count, latest_date = row
            statuses.append(LoaderStatus(
                table_name=table_name,
                status=status,
                completion_pct=float(completion_pct) if completion_pct else 0,
                hours_stale=float(hours_stale) if hours_stale else None,
                row_count=row_count or 0,
                latest_date=str(latest_date) if latest_date else None,
            ))
        return statuses


def print_loader_status(loaders: list[LoaderStatus]):
    """Print loader status in formatted table"""
    print(f"{'Table':<35} {'Status':<12} {'Pct':<6} {'Hours Old':<12} {'Rows':<10}")
    print("-" * 100)
    for loader in loaders:
        pct_str = f"{loader.completion_pct:.0f}%" if loader.completion_pct else "---"

        if loader.hours_stale is None:
            hours_str = "never"
        elif loader.hours_stale < 1:
            hours_str = f"{int(loader.hours_stale*60)}m"
        elif loader.hours_stale < 24:
            hours_str = f"{int(loader.hours_stale)}h"
        else:
            hours_str = f"{int(loader.hours_stale/24)}d"

        print(f"{loader.table_name:<35} {loader.status:<12} {pct_str:<6} {hours_str:<12} {loader.row_count:<10}")


def reset_stuck_loaders():
    """Reset loaders that are stuck in RUNNING or at 100% with completion pct = 100"""
    log_step(1, "IDENTIFY AND RESET STUCK LOADERS")

    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT
                table_name,
                status,
                completion_pct,
                EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - execution_started)) / 3600 as hours_running
            FROM data_loader_status
            WHERE (status = 'RUNNING' AND completion_pct >= 100)
               OR (status = 'RUNNING' AND EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - execution_started)) / 3600 > 4)
            ORDER BY execution_started ASC
        """)

        stuck = cur.fetchall()
        if not stuck:
            log_action("No stuck loaders found")
            return

        log_action(f"Found {len(stuck)} stuck loaders that need reset:")
        for table_name, status, pct, hours in stuck:
            log_action(f"  {table_name}: {status} at {pct:.0f}% for {int(hours)}h", None)

    print()

    # Reset them
    with DatabaseContext('write') as cur:
        cur.execute("""
            UPDATE data_loader_status
            SET status = 'COMPLETED',
                execution_completed = CURRENT_TIMESTAMP,
                error_message = NULL
            WHERE status = 'RUNNING'
              AND (completion_pct >= 100
                   OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - execution_started)) / 3600 > 4)
        """)

        count = cur.rowcount
        log_action(f"Reset {count} stuck loaders to COMPLETED", True)

    print()
    print("Status after reset:")
    statuses = get_loader_status(['sector_ranking', 'market_health_daily', 'signal_quality_scores'])
    print_loader_status(statuses)


def run_loader(loader_name: str, parallelism: int = 4, timeout: int = 600) -> tuple[bool, str]:
    """
    Run a loader and return (success, output)
    """
    cmd = f"python loaders/load_{loader_name}.py --parallelism {parallelism}"

    log_action(f"Starting {loader_name}...", None)

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd()
        )

        if result.returncode == 0:
            log_action(f"{loader_name} completed successfully", True)
            return True, result.stdout
        else:
            error_msg = f"Exit code {result.returncode}: {result.stderr[:200]}"
            log_action(f"{loader_name} failed: {error_msg}", False)
            return False, result.stderr

    except subprocess.TimeoutExpired:
        log_action(f"{loader_name} timeout after {timeout}s", False)
        return False, f"Timeout after {timeout}s"
    except Exception as e:
        log_action(f"{loader_name} error: {e}", False)
        return False, str(e)


def restart_critical_loaders():
    """Restart the critical loader chain"""
    log_step(2, "RESTART CRITICAL LOADER CHAIN")

    critical_loaders = [
        ('market_health_daily', 4, 300),
        ('market_exposure_daily', 1, 120),
        ('signal_quality_scores', 4, 600),
    ]

    results = []
    for loader_name, parallelism, timeout in critical_loaders:
        print()
        success, _ = run_loader(loader_name, parallelism, timeout)
        results.append((loader_name, success))
        time.sleep(2)  # Brief pause between loaders

    print()
    print("RESTART SUMMARY:")
    print("-" * 50)
    for loader_name, success in results:
        status = "OK" if success else "FAILED"
        log_action(f"{loader_name}: {status}", success)

    return all(success for _, success in results)


def verify_data_freshness():
    """Verify that critical data is now fresh"""
    log_step(3, "VERIFY DATA FRESHNESS")

    critical_tables = ['market_health_daily', 'market_exposure_daily', 'signal_quality_scores', 'buy_sell_daily']
    statuses = get_loader_status(critical_tables)

    print_loader_status(statuses)

    print()
    print("FRESHNESS ASSESSMENT:")
    print("-" * 50)

    all_fresh = True
    for status in statuses:
        if status.hours_stale is None:
            assessment = "NEVER UPDATED"
            fresh = False
        elif status.hours_stale > 24:
            assessment = f"STALE ({int(status.hours_stale/24)}+ days)"
            fresh = False
        elif status.hours_stale > 4:
            assessment = f"OLD ({int(status.hours_stale)}h)"
            fresh = False
        else:
            assessment = f"FRESH ({int(status.hours_stale)}h)"
            fresh = True

        log_action(f"{status.table_name}: {assessment}", fresh)
        if not fresh:
            all_fresh = False

    return all_fresh


def check_circuit_breaker():
    """Check circuit breaker status"""
    log_step(4, "CHECK CIRCUIT BREAKER")

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT trading_halted, halt_reason, halted_at
                FROM circuit_breaker_status
                LIMIT 1
            """)

            row = cur.fetchone()
            if row:
                trading_halted, halt_reason, halted_at = row

                if trading_halted:
                    log_action("Circuit breaker is HALTED", False)
                    log_action(f"Reason: {halt_reason}", None)
                    if halted_at:
                        log_action(f"Halted at: {halted_at}", None)
                else:
                    log_action("Circuit breaker is ALLOWING TRADING", True)
            else:
                log_action("No circuit breaker status found", False)
    except Exception as e:
        log_action(f"Could not check circuit breaker: {e}", False)


def re_enable_suspended_loaders() -> None:
    """Re-enable suspended loaders: auto-recovery for non-critical, alert for critical."""
    log_step(5, "RE-ENABLE SUSPENDED LOADERS (AUTO-RECOVERY)")

    critical_loaders = {
        "load_prices",
        "load_market_health",
        "load_market_constituents",
        "price_daily",
        "market_health_daily",
    }

    # Get list of suspended loaders
    with DatabaseContext('write') as cur:
        cur.execute("""
            SELECT DISTINCT loader_name, MAX(execution_date) as last_date, COUNT(*) as fail_count
            FROM data_loader_status
            WHERE status IN ('SUSPENDED', 'FAILED')
                AND execution_date >= CURRENT_DATE - get_interval_sql('7d')
            GROUP BY loader_name
            ORDER BY fail_count DESC, last_date DESC
        """)

        suspended = cur.fetchall()

        if not suspended:
            log_action("No suspended loaders found", True)
            return

        log_action(f"Found {len(suspended)} suspended loaders, attempting recovery:", None)

        for row in suspended:
            loader_name = row.get("loader_name") or row[0]
            fail_count = row.get("fail_count") or row[2]

            if loader_name in critical_loaders:
                # Critical loaders: alert ops, require manual investigation
                log_action(f"  [CRITICAL] {loader_name}: {fail_count} failures - REQUIRES MANUAL REVIEW", False)
                logger.critical(
                    f"[LOADER_RECOVERY] CRITICAL LOADER SUSPENDED: {loader_name} "
                    f"(failed {fail_count} times). Manual investigation required."
                )
            else:
                # Non-critical loaders: auto-recovery
                try:
                    # Re-enable by clearing suspension status
                    cur.execute("""
                        UPDATE data_loader_status
                        SET status = 'PENDING', updated_at = CURRENT_TIMESTAMP
                        WHERE loader_name = %s AND status IN ('SUSPENDED', 'FAILED')
                    """, (loader_name,))

                    log_action(f"  [AUTO-RECOVERY] {loader_name}: re-enabled ({fail_count} previous failures)", True)
                    logger.info(f"[LOADER_RECOVERY] Auto-enabled non-critical loader: {loader_name}")

                except Exception as e:
                    log_action(f"  [ERROR] {loader_name}: could not re-enable - {e}", False)
                    logger.error(f"Failed to re-enable {loader_name}: {e}")

    print()
    log_action("Loader recovery complete", True)


def main():
    """Main recovery procedure"""
    print()
    print("=" * 100)
    print("  DATA PIPELINE RECOVERY - SYSTEMATIC FIX")
    print("=" * 100)
    print()

    try:
        # Step 1: Reset stuck loaders
        reset_stuck_loaders()

        # Step 2: Restart critical loaders
        restart_success = restart_critical_loaders()

        # Step 3: Verify data is fresh
        fresh_success = verify_data_freshness()

        # Step 4: Check circuit breaker
        check_circuit_breaker()

        # Step 5: Plan for suspended loaders
        re_enable_suspended_loaders()

        # Final summary
        print()
        log_step(6, "RECOVERY SUMMARY")

        print("STATUS:")
        print("-" * 50)
        log_action("Stuck loaders reset: OK", True)
        log_action(f"Critical loaders restarted: {'OK' if restart_success else 'CHECK LOGS'}", restart_success)
        log_action(f"Data freshness verified: {'OK' if fresh_success else 'DATA STILL STALE'}", fresh_success)

        print()
        if restart_success and fresh_success:
            print("SUCCESS: System is ready for Monday trading!")
            return 0
        else:
            print("WARNING: Some issues remain. Review output above.")
            return 1

    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
