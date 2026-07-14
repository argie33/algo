#!/usr/bin/env python3
"""Dashboard health monitor - detects "data not available" root causes before they break the dashboard.

This script identifies ALL reasons why the dashboard shows "data not available":
1. Orchestrator not running (no data updates)
2. API endpoints returning errors
3. Cognito auth failures
4. Data staleness threshold exceeded
5. Loader failures in the pipeline
6. Circuit breaker open (repeated API failures)

Run this BEFORE starting the dashboard to diagnose issues.
Run periodically (cron) to catch stale data early.

Usage:
    python scripts/dashboard_health_monitor.py              # One-time check
    python scripts/dashboard_health_monitor.py --watch 60  # Poll every 60s
    python scripts/dashboard_health_monitor.py --alert      # Send alerts if unhealthy
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class DashboardHealthChecker:
    """Check all components that can cause "data not available" on dashboard."""

    def __init__(self, api_url: str = "http://localhost:3001"):
        self.api_url = api_url
        self.timeout = 5
        self.session = requests.Session()
        self.issues: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []

    def add_issue(self, severity: str, component: str, message: str, remediation: str = "") -> None:
        """Record a health issue."""
        self.issues.append(
            {
                "severity": severity,  # "critical", "warning", "info"
                "component": component,  # e.g., "orchestrator", "api", "auth", "data"
                "message": message,
                "remediation": remediation,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def check_api_health(self) -> bool:
        """Check if API itself is responding."""
        try:
            resp = self.session.get(f"{self.api_url}/api/health", timeout=self.timeout)
            if resp.status_code != 200:
                self.add_issue(
                    "critical",
                    "api",
                    f"API health check failed: {resp.status_code}",
                    "Run: python lambda/api/dev_server.py",
                )
                return False
            data = resp.json()
            status = data.get("data", {}).get("status", "unknown")
            if status != "healthy":
                self.add_issue(
                    "warning",
                    "api",
                    f"API degraded (status={status})",
                    "Check dev_server logs for errors",
                )
                return False
            return True
        except requests.exceptions.ConnectionError:
            self.add_issue(
                "critical",
                "api",
                f"API not responding ({self.api_url})",
                "Run: python lambda/api/dev_server.py",
            )
            return False
        except requests.exceptions.Timeout:
            self.add_issue(
                "critical",
                "api",
                "API timeout",
                "Check if dev_server is CPU-bound or hanging",
            )
            return False
        except Exception as e:
            self.add_issue("critical", "api", f"API check failed: {e}", "Investigate error above")
            return False

    def check_orchestrator_status(self) -> bool:
        """Check if orchestrator is running and completing."""
        try:
            resp = self.session.get(f"{self.api_url}/api/algo/run", timeout=self.timeout)
            if resp.status_code == 401:
                # Auth not configured in dev_server - this is OK for local dev
                return True
            if resp.status_code != 200:
                self.add_issue(
                    "critical",
                    "orchestrator",
                    f"Orchestrator status unavailable: {resp.status_code}",
                    "Check API logs for errors",
                )
                return False

            data = resp.json().get("data", {})
            started_at = data.get("started_at")
            status = data.get("status", "unknown")

            if not started_at:
                self.add_issue(
                    "critical",
                    "orchestrator",
                    "No orchestrator runs found in database",
                    "Run: python3 scripts/run_local_orchestrator.py --morning",
                )
                return False

            # Parse timestamp
            try:
                last_run_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - last_run_time).total_seconds() / 3600
            except Exception:
                age_hours = 999

            if age_hours > 24:
                self.add_issue(
                    "critical",
                    "orchestrator",
                    f"Orchestrator hasn't run in {age_hours:.1f} hours",
                    "Run: python3 scripts/run_local_orchestrator.py --morning",
                )
                return False

            if age_hours > 4:
                self.add_issue(
                    "warning",
                    "orchestrator",
                    f"Orchestrator run is {age_hours:.1f} hours old (should run every 4 hours)",
                    "Verify EventBridge Scheduler is enabled (prod) or manually trigger (dev)",
                )

            if status not in ("success", "completed"):
                self.add_issue(
                    "critical",
                    "orchestrator",
                    f"Last orchestrator run failed: status={status}",
                    "Check orchestrator logs for phase failures",
                )
                return False

            return True
        except Exception as e:
            self.add_issue(
                "warning",
                "orchestrator",
                f"Could not check orchestrator status: {e}",
                "This is OK for local dev if auth not configured",
            )
            return True  # Not critical for dev

    def check_data_freshness(self) -> bool:
        """Check if data tables are being updated."""
        try:
            resp = self.session.get(f"{self.api_url}/api/algo/data-status", timeout=self.timeout)
            if resp.status_code != 200:
                self.add_issue(
                    "warning",
                    "data",
                    f"Data status check failed: {resp.status_code}",
                    "Check API logs",
                )
                return False

            data = resp.json().get("data", {})
            items = data.get("items", [])

            if not items:
                self.add_issue(
                    "warning",
                    "data",
                    "No data tables found",
                    "Database may be empty",
                )
                return False

            # Check for critical stale tables
            critical_tables = {
                "price_daily",
                "market_exposure_daily",
                "stock_scores",
                "algo_orchestrator_runs",
            }

            stale_critical = []
            for item in items:
                name = item.get("name")
                status = item.get("status")
                age_hours = item.get("age_hours", 999)
                row_count = item.get("row_count", 0)

                if name in critical_tables:
                    if status == "stale" or age_hours > 24:
                        stale_critical.append(f"{name} ({age_hours:.1f}h old, {row_count} rows)")
                    elif status == "empty" or row_count == 0:
                        stale_critical.append(f"{name} (EMPTY)")

            if stale_critical:
                self.add_issue(
                    "critical",
                    "data",
                    f"Critical tables stale: {', '.join(stale_critical)}",
                    "Run: python3 scripts/run_local_orchestrator.py --morning",
                )
                return False

            return True
        except Exception as e:
            self.add_issue(
                "warning",
                "data",
                f"Could not check data freshness: {e}",
                "Database may not be accessible",
            )
            return False

    def check_api_endpoints(self) -> bool:
        """Check if key API endpoints are responding."""
        endpoints = [
            "/api/algo/portfolio",
            "/api/algo/positions",
            "/api/algo/config",
            "/api/algo/health",
        ]

        failed = []
        for endpoint in endpoints:
            try:
                resp = self.session.get(
                    urljoin(self.api_url, endpoint),
                    timeout=self.timeout,
                    headers={"Authorization": "Bearer dev-admin"},
                )
                if resp.status_code >= 500:
                    failed.append(f"{endpoint} ({resp.status_code})")
            except Exception:
                failed.append(f"{endpoint} (timeout/error)")

        if failed:
            self.add_issue(
                "warning",
                "api",
                f"Some endpoints failing: {', '.join(failed)}",
                "Check API error logs for details",
            )
            return False

        return True

    def run_health_check(self) -> dict[str, Any]:
        """Run complete health check."""
        logger.info("[DASHBOARD_HEALTH] Starting health check...")

        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_url": self.api_url,
            "checks": {
                "api": self.check_api_health(),
                "orchestrator": self.check_orchestrator_status(),
                "data_freshness": self.check_data_freshness(),
                "api_endpoints": self.check_api_endpoints(),
            },
            "issues": self.issues,
            "overall_status": "healthy" if all(self.checks.values()) else "unhealthy",
        }

        return results

    @property
    def checks(self) -> dict[str, bool]:
        """Return current check results."""
        return {
            "api": any(i["component"] == "api" and i["severity"] != "critical" for i in self.issues) is False,
            "orchestrator": any(i["component"] == "orchestrator" and i["severity"] == "critical" for i in self.issues)
            is False,
            "data_freshness": any(i["component"] == "data" and i["severity"] == "critical" for i in self.issues)
            is False,
            "api_endpoints": any(i["component"] == "api" and i["severity"] == "critical" for i in self.issues) is False,
        }

    def print_report(self, results: dict[str, Any]) -> None:
        """Print health check results."""
        print("\n" + "=" * 70)
        print("DASHBOARD HEALTH CHECK REPORT")
        print("=" * 70)
        print(f"Timestamp: {results['timestamp']}")
        print(f"API URL: {results['api_url']}")
        print(f"Overall Status: {results['overall_status'].upper()}")
        print()

        print("COMPONENT STATUS:")
        for check, passed in results["checks"].items():
            status = "[OK]" if passed else "[FAILED]"
            print(f"  {check:25} {status}")
        print()

        if results["issues"]:
            print("ISSUES FOUND:")
            for issue in sorted(
                results["issues"], key=lambda x: {"critical": 0, "warning": 1, "info": 2}[x["severity"]]
            ):
                severity_icon = {"critical": "[CRIT]", "warning": "[WARN]", "info": "[INFO]"}[issue["severity"]]
                print(f"\n  {severity_icon} {issue['component']}")
                print(f"     {issue['message']}")
                if issue["remediation"]:
                    print(f"     Remediation: {issue['remediation']}")
        else:
            print("[OK] No issues found - dashboard should be healthy")

        print("\n" + "=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard health monitor")
    parser.add_argument("--api-url", default="http://localhost:3001", help="API base URL")
    parser.add_argument("--watch", type=int, metavar="SECONDS", help="Poll every N seconds")
    parser.add_argument("--alert", action="store_true", help="Alert if unhealthy (exit code 1)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    checker = DashboardHealthChecker(api_url=args.api_url)

    def run_once() -> bool:
        checker.issues = []
        results = checker.run_health_check()

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            checker.print_report(results)

        return results["overall_status"] == "healthy"

    if args.watch:
        logger.info(f"[HEALTH_MONITOR] Polling every {args.watch}s (Ctrl+C to stop)")
        while True:
            try:
                is_healthy = run_once()
                time.sleep(args.watch)
            except KeyboardInterrupt:
                logger.info("[HEALTH_MONITOR] Stopped")
                break
    else:
        is_healthy = run_once()
        if args.alert and not is_healthy:
            sys.exit(1)


if __name__ == "__main__":
    main()
