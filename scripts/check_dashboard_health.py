#!/usr/bin/env python3
"""
Dashboard Health Checker - Diagnoses why orchestrator halts and data is stale

Usage:
  python3 check_dashboard_health.py                # Basic health check
  python3 check_dashboard_health.py --verbose      # Detailed diagnostics
  python3 check_dashboard_health.py --clear-halt   # Clear halt flag (use cautiously)
"""

import argparse
import json
import sys
from datetime import date, timedelta
from typing import Any

import psycopg2

from algo.infrastructure import MarketCalendar
from utils.db import DatabaseContext


def check_table_freshness() -> dict[str, Any]:
    """Check if critical halt tables are stale."""
    critical_tables = {
        "price_daily": ("date", "HALT"),
        "market_health_daily": ("date", "HALT"),
        "market_exposure_daily": ("date", "HALT"),
        "earnings_calendar": ("earnings_date", "HALT"),
        "trend_template_data": ("date", "WARN"),
    }

    freshness = {}
    try:
        with DatabaseContext("read") as cur:
            for table_name, (date_col, severity) in critical_tables.items():
                try:
                    cur.execute(f"""
                        SELECT
                            COUNT(*) as row_count,
                            MAX({date_col}) as latest_date
                        FROM {table_name}
                    """)
                    row = cur.fetchone()
                    if row is None or row["row_count"] == 0:
                        freshness[table_name] = {
                            "status": "EMPTY",
                            "severity": severity,
                            "row_count": 0,
                            "latest_date": None,
                            "days_behind": None,
                        }
                    else:
                        latest_date = row["latest_date"]
                        row_count = row["row_count"]
                        today = date.today()

                        # Find last trading day
                        last_trading_day = today - timedelta(days=1)
                        for _ in range(10):
                            if MarketCalendar.is_trading_day(last_trading_day):
                                break
                            last_trading_day -= timedelta(days=1)

                        days_behind = (last_trading_day - latest_date).days if latest_date else None
                        is_stale = days_behind > 1 if days_behind is not None else True

                        freshness[table_name] = {
                            "status": "STALE" if is_stale else "FRESH",
                            "severity": severity,
                            "row_count": row_count,
                            "latest_date": str(latest_date) if latest_date else None,
                            "last_trading_day": str(last_trading_day),
                            "days_behind": days_behind,
                        }
                except psycopg2.Error as e:
                    freshness[table_name] = {
                        "status": "ERROR",
                        "severity": severity,
                        "error": str(e)[:100],
                    }
    except psycopg2.Error as e:
        print(f"ERROR: Cannot connect to database: {e}")
        sys.exit(1)

    return freshness


def check_halt_flag() -> bool:
    """Check if orchestrator halt flag is set."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SELECT value FROM algo_orchestrator_state WHERE key = 'orchestrator_halt'")
            row = cur.fetchone()
            return row is not None and row["value"] == "true"
    except psycopg2.Error:
        return False


def check_last_run() -> dict[str, Any]:
    """Get the last orchestrator run result."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    run_id,
                    overall_status,
                    halt_reason,
                    phases_completed,
                    created_at,
                    phase_results
                FROM orchestrator_execution_log
                ORDER BY created_at DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if row is None:
                return {"status": "NO_RUNS", "message": "No orchestrator runs yet"}
            return {
                "run_id": row["run_id"],
                "status": row["overall_status"],
                "halt_reason": row["halt_reason"],
                "phases_completed": row["phases_completed"],
                "timestamp": str(row["created_at"]),
                "phase_results": row["phase_results"],
            }
    except psycopg2.Error as e:
        return {"status": "ERROR", "error": str(e)[:100]}


def clear_halt_flag() -> bool:
    """Clear the orchestrator halt flag."""
    try:
        with DatabaseContext("write") as cur:
            cur.execute("DELETE FROM algo_orchestrator_state WHERE key = 'orchestrator_halt'")
            return True
    except psycopg2.Error as e:
        print(f"ERROR: Could not clear halt flag: {e}")
        return False


def print_freshness_check(freshness: dict[str, Any], verbose: bool) -> tuple[bool, bool]:
    """Print freshness check results and return (halt_ok, warn_ok)."""
    halt_tables_ok = True
    warn_tables_ok = True

    for table_name, info in freshness.items():
        status = info["status"]
        severity = info.get("severity", "UNKNOWN")

        if severity == "HALT":
            icon = "🔴" if status != "FRESH" else "🟢"
            if status != "FRESH":
                halt_tables_ok = False
        else:
            icon = "🟡" if status != "FRESH" else "🟢"
            if status != "FRESH":
                warn_tables_ok = False

        latest = info.get("latest_date", "N/A")
        behind = info.get("days_behind")

        if behind is not None:
            print(f"{icon} {table_name:30s} {status:6s} ({behind} days behind, max: {latest})")
        else:
            print(f"{icon} {table_name:30s} {status:6s}")

        if verbose and "error" in info:
            print(f"   ERROR: {info['error']}")

    return halt_tables_ok, warn_tables_ok


def print_halt_flag_status(halt_set: bool) -> None:
    """Print halt flag status."""
    if halt_set:
        print("🔴 HALT FLAG IS SET - This blocks all subsequent runs from proceeding!")
        print("   Last run detected stale data and set this flag.")
        print("   It persists throughout the trading day (expires at market open tomorrow)")
    else:
        print("🟢 Halt flag is clear - Orchestrator can proceed")


def print_last_run(last_run: dict[str, Any], verbose: bool) -> None:
    """Print last orchestrator run info."""
    if last_run.get("status") == "NO_RUNS":
        print("⚠️  No orchestrator runs yet")
    elif last_run.get("status") == "ERROR":
        print(f"❌ Error querying run history: {last_run.get('error')}")
    else:
        print(f"Run ID: {last_run['run_id']}")
        print(f"Status: {last_run['status'].upper()}")
        print(f"Phases: {last_run['phases_completed']}")
        print(f"Time: {last_run['timestamp']}")
        if last_run["halt_reason"]:
            print(f"Halt Reason: {last_run['halt_reason']}")

        if verbose and last_run.get("phase_results"):
            print("\nPhase Results:")
            try:
                phases = json.loads(last_run["phase_results"])
                for p in phases:
                    print(f"  - Phase {p.get('phase')}: {p.get('status')}")
                    if p.get("summary"):
                        print(f"    {p.get('summary')[:80]}")
            except (json.JSONDecodeError, TypeError):
                print(f"  {last_run['phase_results'][:200]}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check dashboard health and diagnose orchestrator issues"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Show detailed diagnostics"
    )
    parser.add_argument(
        "--clear-halt",
        action="store_true",
        help="Clear the orchestrator halt flag (caution: unblocks stale data)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("DASHBOARD HEALTH CHECK")
    print("=" * 70)

    # Check table freshness
    print("\n[1] CRITICAL TABLE FRESHNESS")
    print("-" * 70)
    freshness = check_table_freshness()
    halt_tables_ok, warn_tables_ok = print_freshness_check(freshness, args.verbose)

    # Check halt flag
    print("\n[2] ORCHESTRATOR HALT FLAG")
    print("-" * 70)
    halt_set = check_halt_flag()
    print_halt_flag_status(halt_set)

    # Check last run
    print("\n[3] LAST ORCHESTRATOR RUN")
    print("-" * 70)
    last_run = check_last_run()
    print_last_run(last_run, args.verbose)

    # Diagnostic summary
    print("\n[4] DIAGNOSIS")
    print("-" * 70)

    if halt_tables_ok and not halt_set:
        print("✅ SYSTEM OK - Data is fresh, no halt flag set")
        print("   Dashboard should show successful runs and fresh data")
        return 0
    elif not halt_tables_ok:
        print("❌ CRITICAL - Halt tables are stale")
        print("   Phase 1 will detect this and halt the orchestrator")
        print("\nTO FIX:")
        print("  1. Run critical loaders: load-prices, load-market-health, load-market-exposure")
        print("  2. Use AWS CLI: aws ecs run-task --cluster <> --task-definition load-prices:latest")
        print("  3. Wait for loaders to complete (5-10 minutes)")
        print("  4. Run: python3 scripts/check_dashboard_health.py  (to verify)")
        print("  5. Run orchestrator: python3 algo_orchestrator.py --dry-run")
        if halt_set:
            print("  6. Clear halt flag: python3 scripts/check_dashboard_health.py --clear-halt")
        return 1
    elif halt_set:
        print("⚠️  BLOCKED - Halt flag prevents runs from proceeding")
        print("   Even if data is fresh, orchestrator won't run until flag is cleared")
        print("\nTO FIX:")
        if warn_tables_ok and not halt_tables_ok:
            print("  ⚠️  Only warning tables are stale (trading can continue)")
        print("  1. Verify fresh data exists using: python3 scripts/check_dashboard_health.py")
        if halt_tables_ok:
            print("  2. Data IS fresh - safe to clear the halt flag")
            print("  3. Clear with: python3 scripts/check_dashboard_health.py --clear-halt")
        else:
            print("  2. FIX HALT TABLES FIRST (see above)")
            print("  3. Then clear halt flag")
        return 1

    return 0


if __name__ == "__main__":
    # Handle --clear-halt flag separately
    if "--clear-halt" in sys.argv:
        print("🔧 Attempting to clear orchestrator halt flag...")
        if clear_halt_flag():
            print("✅ Halt flag cleared successfully")
            print("   Orchestrator can now proceed on next scheduled run")
        else:
            print("❌ Failed to clear halt flag")
            sys.exit(1)
    else:
        sys.exit(main())
