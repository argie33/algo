#!/usr/bin/env python3
"""
Comprehensive system diagnostics for algo trading system.

Validates:
- Database connection pool health
- Lock status and health
- Loader performance and recent runs
- Data consistency checks
- Configuration validation
- Recent errors (last 24h)

Usage:
    python comprehensive_diagnostics.py                    # Run all checks
    python comprehensive_diagnostics.py --focus database   # Database only
    python comprehensive_diagnostics.py --focus locks      # Locks only
    python comprehensive_diagnostics.py --verbose          # Detailed output
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add repo root (parent of this script's scripts/ directory) to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.db.context import DatabaseContext


class DiagnosticResult:
    """Result of a diagnostic check."""

    def __init__(self, name: str, status: str, message: str = "", details: dict[str, Any] | None = None):
        self.name = name
        self.status = status  # OK, WARNING, ERROR, CRITICAL
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class SystemDiagnostics:
    """Complete system health check."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: list[DiagnosticResult] = []

    def run_all(self) -> bool:
        """Run all diagnostics and return True if all pass."""
        try:
            # Run all checks
            self.check_database_connection()
            self.check_locks_health()
            self.check_loader_performance()
            self.check_data_freshness()
            self.check_configuration()
            self.check_recent_errors()

            return self.print_results()
        except Exception as e:
            print(f"CRITICAL: Diagnostics initialization failed: {e}")
            return False

    def run_focus(self, focus: str) -> bool:
        """Run diagnostics focused on a specific area."""
        try:
            focus_map = {
                "database": [self.check_database_connection],
                "locks": [self.check_locks_health],
                "loaders": [self.check_loader_performance],
                "consistency": [self.check_data_freshness],
                "config": [self.check_configuration],
                "errors": [self.check_recent_errors],
            }

            if focus not in focus_map:
                print(f"Unknown focus: {focus}")
                print(f"Available: {', '.join(focus_map.keys())}")
                return False

            for check in focus_map[focus]:
                check()

            return self.print_results()
        except Exception as e:
            print(f"CRITICAL: Diagnostics initialization failed: {e}")
            return False

    def check_database_connection(self) -> None:
        """Verify database connection works."""
        try:
            with DatabaseContext("read", timeout=10, enable_correlation_tracking=False) as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()

            if result:
                self.results.append(DiagnosticResult("Database Connection", "OK", "Database connection successful"))
            else:
                self.results.append(
                    DiagnosticResult("Database Connection", "CRITICAL", "Database connection returned no result")
                )
        except Exception as e:
            self.results.append(
                DiagnosticResult("Database Connection", "CRITICAL", f"Database connection failed: {e!s}")
            )

    def check_locks_health(self) -> None:
        """Check for stale and orphaned locks."""
        try:
            with DatabaseContext("read", timeout=10, enable_correlation_tracking=False) as cur:
                # Check for stale locks (>2 hours old).
                #
                # BUG FOUND 2026-08-10: this used to query data_loader_runs for
                # status='running' - but every writer of that table (load_prices.py,
                # load_technical_indicators.py, loader_success_logger.py, provenance.py)
                # does a single INSERT after a run finishes, with status in
                # ('success','failed','completed') - never 'running'. No row in that table
                # can ever match this WHERE clause, so this check vacuously always reported
                # "No stale loader locks found" regardless of real state. The table that
                # actually tracks in-progress loaders is data_loader_status
                # (utils/loaders/status_manager.py's mark_running() sets
                # status=LoaderStatus.RUNNING.value == 'RUNNING', uppercase - confirmed via
                # `SELECT DISTINCT status FROM data_loader_status`), which is exactly what
                # this check needs. Live-reproduced the same day: a crashed metrics-pipeline
                # run left quality_metrics/growth_metrics genuinely stuck at status='RUNNING'
                # for hours - this diagnostic would have reported "OK" throughout.
                query = """
                SELECT
                    table_name AS loader_name,
                    execution_started AS started_at,
                    EXTRACT(EPOCH FROM (NOW() - execution_started)) as age_seconds
                FROM data_loader_status
                WHERE execution_started < NOW() - INTERVAL '2 hours'
                  AND status = 'RUNNING'
                ORDER BY execution_started DESC
                LIMIT 20
                """

                try:
                    cur.execute(query)
                    stale_locks = cur.fetchall()

                    if not stale_locks:
                        self.results.append(DiagnosticResult("Stale Locks", "OK", "No stale loader locks found"))
                    else:
                        stale_details = []
                        for row in stale_locks:
                            age_hours = row["age_seconds"] / 3600
                            stale_details.append(f"{row['loader_name']} (age={age_hours:.1f}h)")

                        severity = "WARNING" if len(stale_locks) < 5 else "ERROR"
                        self.results.append(
                            DiagnosticResult(
                                "Stale Locks",
                                severity,
                                f"Found {len(stale_locks)} stale loader locks",
                                {"stale_locks": stale_details[:5]},
                            )
                        )
                except Exception as table_error:
                    # Table might not exist
                    if "does not exist" in str(table_error).lower():
                        self.results.append(DiagnosticResult("Stale Locks", "OK", "data_loader_status table not found"))
                    else:
                        raise
        except Exception as e:
            self.results.append(DiagnosticResult("Stale Locks", "WARNING", f"Lock health check failed: {e!s}"))

    def check_loader_performance(self) -> None:
        """Check recent loader execution performance."""
        try:
            with DatabaseContext("read", timeout=10, enable_correlation_tracking=False) as cur:
                # Check recent loader runs (last 24 hours)
                query = """
                SELECT
                    loader_name,
                    status,
                    COUNT(*) as count,
                    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_sec,
                    MAX(completed_at) as last_run
                FROM data_loader_runs
                WHERE started_at > NOW() - INTERVAL '24 hours'
                GROUP BY loader_name, status
                ORDER BY loader_name, last_run DESC
                """

                try:
                    cur.execute(query)
                    runs = cur.fetchall()

                    if not runs:
                        self.results.append(
                            DiagnosticResult("Loader Performance", "WARNING", "No loader runs in last 24 hours")
                        )
                    else:
                        # Summarize by status
                        status_counts: dict[str, int] = {}
                        for row in runs:
                            status = row["status"]
                            status_counts[status] = status_counts.get(status, 0) + row["count"]

                        failed = status_counts.get("failed", 0)
                        error = status_counts.get("error", 0)
                        completed = status_counts.get("completed", 0)

                        overall_status = "OK"
                        if failed > 0 or error > 0:
                            overall_status = "WARNING" if failed < 3 else "ERROR"

                        self.results.append(
                            DiagnosticResult(
                                "Loader Performance",
                                overall_status,
                                f"Runs: {completed} completed, {failed} failed, {error} error (24h)",
                                {
                                    "completed_count": completed,
                                    "failed_count": failed,
                                    "error_count": error,
                                    "status_breakdown": status_counts,
                                },
                            )
                        )
                except Exception as table_error:
                    if "does not exist" in str(table_error).lower():
                        self.results.append(
                            DiagnosticResult("Loader Performance", "OK", "data_loader_runs table not found")
                        )
                    else:
                        raise
        except Exception as e:
            self.results.append(
                DiagnosticResult("Loader Performance", "WARNING", f"Loader performance check failed: {e!s}")
            )

    def check_data_freshness(self) -> None:
        """Check how recent the data is across key tables."""
        try:
            with DatabaseContext("read", timeout=10, enable_correlation_tracking=False) as cur:
                tables_to_check = [
                    ("price_daily", "date"),
                    ("buy_sell_daily", "date"),
                    ("quality_metrics", "updated_at"),
                ]

                freshness_results = {}
                for table, date_col in tables_to_check:
                    try:
                        query = f"SELECT MAX({date_col}) as max_date FROM {table}"
                        cur.execute(query)
                        row = cur.fetchone()

                        if row and row["max_date"]:
                            max_date = row["max_date"]
                            today = datetime.utcnow()

                            # Handle both DATE and TIMESTAMP types
                            if hasattr(max_date, "date"):  # datetime/timestamp object
                                max_date_only = max_date.date()
                            else:  # string
                                max_date_dt = datetime.fromisoformat(str(max_date))
                                max_date_only = max_date_dt.date()

                            age_days = (today.date() - max_date_only).days
                            freshness_results[table] = {"max_date": str(max_date_only), "age_days": age_days}
                        else:
                            freshness_results[table] = {"max_date": "no data", "age_days": None}
                    except Exception as table_error:
                        if "does not exist" in str(table_error).lower():
                            freshness_results[table] = {"error": "table not found"}
                        else:
                            freshness_results[table] = {"error": str(table_error)}

                # Determine overall status
                ages = [v.get("age_days", 0) for v in freshness_results.values() if v.get("age_days") is not None]
                max_age = max(ages) if ages else 0

                if max_age > 2:
                    status = "WARNING"
                    message = f"Some data is {max_age} days old"
                elif max_age > 0:
                    status = "OK"
                    message = f"Data up to {max_age} days old"
                else:
                    status = "OK"
                    message = "All data current (today or yesterday)"

                self.results.append(DiagnosticResult("Data Freshness", status, message, freshness_results))
        except Exception as e:
            self.results.append(DiagnosticResult("Data Freshness", "WARNING", f"Data freshness check failed: {e!s}"))

    def check_configuration(self) -> None:
        """Check critical configuration values."""
        try:
            with DatabaseContext("read", timeout=10, enable_correlation_tracking=False) as cur:
                query = """
                SELECT key, value
                FROM algo_config
                WHERE key IN ('execution_mode', 'alert_email_to', 'alerts_sns_topic')
                """

                try:
                    cur.execute(query)
                    config_rows = cur.fetchall()

                    config = {row["key"]: row["value"] for row in config_rows}

                    # Verify execution mode is 'paper' (unless this is prod)
                    exec_mode = config.get("execution_mode", "unknown")
                    status = "OK" if exec_mode == "paper" else "WARNING"
                    message = f"Execution mode: {exec_mode}"

                    self.results.append(
                        DiagnosticResult(
                            "Configuration",
                            status,
                            message,
                            {
                                "execution_mode": exec_mode,
                                "alert_email_configured": bool(config.get("alert_email_to")),
                                "sns_configured": bool(config.get("alerts_sns_topic")),
                            },
                        )
                    )
                except Exception as table_error:
                    if "does not exist" in str(table_error).lower():
                        self.results.append(DiagnosticResult("Configuration", "WARNING", "algo_config table not found"))
                    else:
                        raise
        except Exception as e:
            self.results.append(DiagnosticResult("Configuration", "WARNING", f"Configuration check failed: {e!s}"))

    def check_recent_errors(self) -> None:
        """Check for recent errors in logs."""
        try:
            with DatabaseContext("read", timeout=10, enable_correlation_tracking=False) as cur:
                # Check for recent errors in orchestrator logs
                query = """
                SELECT
                    COUNT(*) as error_count,
                    MAX(created_at) as last_error
                FROM orchestrator_execution_log
                WHERE overall_status = 'halted'
                  AND created_at > NOW() - INTERVAL '24 hours'
                """

                try:
                    cur.execute(query)
                    row = cur.fetchone()

                    if row:
                        error_count = row["error_count"]
                        last_error = row["last_error"]

                        if error_count == 0:
                            self.results.append(
                                DiagnosticResult("Recent Errors", "OK", "No orchestrator errors in last 24 hours")
                            )
                        else:
                            status = "WARNING" if error_count < 3 else "ERROR"
                            self.results.append(
                                DiagnosticResult(
                                    "Recent Errors",
                                    status,
                                    f"{error_count} orchestrator errors (last 24h)",
                                    {"error_count": error_count, "last_error": str(last_error)},
                                )
                            )
                except Exception as table_error:
                    # Table might not exist, which is OK
                    if "does not exist" in str(table_error).lower():
                        self.results.append(
                            DiagnosticResult(
                                "Recent Errors", "OK", "Error log table not found (expected for some configurations)"
                            )
                        )
                    else:
                        raise
        except Exception as e:
            self.results.append(DiagnosticResult("Recent Errors", "WARNING", f"Error check failed: {e!s}"))

    def print_results(self) -> bool:
        """Print diagnostic results and return True if all are OK/WARNING."""
        if not self.results:
            print("No diagnostics were run")
            return False

        # Color codes
        colors = {
            "OK": "\033[92m",  # Green
            "WARNING": "\033[93m",  # Yellow
            "ERROR": "\033[91m",  # Red
            "CRITICAL": "\033[95m",  # Magenta
            "RESET": "\033[0m",
        }

        print("\n" + "=" * 70)
        print("SYSTEM DIAGNOSTICS REPORT")
        print("=" * 70)
        print(f"Generated: {datetime.utcnow().isoformat()}Z")
        print()

        # Group results by status
        status_groups: dict[str, list[DiagnosticResult]] = {}
        for result in self.results:
            if result.status not in status_groups:
                status_groups[result.status] = []
            status_groups[result.status].append(result)

        # Print by status (OK first, CRITICAL last)
        status_order = ["OK", "WARNING", "ERROR", "CRITICAL"]
        for status in status_order:
            if status not in status_groups:
                continue

            results_for_status = status_groups[status]
            color = colors.get(status, "")

            print(f"{color}[{status}]{colors['RESET']} ({len(results_for_status)} checks)")

            for result in results_for_status:
                print(f"  - {result.name}")
                if result.message:
                    print(f"    {result.message}")
                if self.verbose and result.details:
                    for key, value in result.details.items():
                        print(f"    {key}: {value}")
            print()

        # Summary
        critical = len(status_groups.get("CRITICAL", []))
        errors = len(status_groups.get("ERROR", []))
        warnings = len(status_groups.get("WARNING", []))
        ok = len(status_groups.get("OK", []))

        print("=" * 70)
        print(f"SUMMARY: {ok} OK, {warnings} WARNING, {errors} ERROR, {critical} CRITICAL")

        if critical > 0:
            print(f"{colors['CRITICAL']}[CRITICAL ISSUES FOUND] - DO NOT LAUNCH{colors['RESET']}")
            return False
        elif errors > 0:
            print(f"{colors['ERROR']}[ERRORS FOUND] - REVIEW BEFORE LAUNCH{colors['RESET']}")
            return False
        else:
            print(f"{colors['OK']}[SYSTEM HEALTHY] - OK TO LAUNCH{colors['RESET']}")
            return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run system diagnostics")
    parser.add_argument(
        "--focus",
        choices=["database", "locks", "loaders", "consistency", "config", "errors"],
        help="Run only specific diagnostic",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    diagnostics = SystemDiagnostics(verbose=args.verbose)

    if args.focus:
        success = diagnostics.run_focus(args.focus)
    else:
        success = diagnostics.run_all()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
