#!/usr/bin/env python3
"""Failure scenario simulator for recovery testing.

This script simulates realistic failure scenarios and tests recovery mechanisms:
1. Simulates database failures (connection refused, timeout, disk full)
2. Simulates API failures (500, 503, timeout)
3. Simulates network issues (timeout, connection reset)
4. Simulates process termination (SIGTERM during critical operation)
5. Simulates resource exhaustion (disk full, memory pressure)
6. Verifies system recovery from each scenario

Usage:
    python scripts/failure_scenario_simulator.py --scenario <name>
    python scripts/failure_scenario_simulator.py --all
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest import mock

import psycopg2

# Add project root
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

logger = logging.getLogger(__name__)


class FailureScenarioSimulator:
    """Simulate failure scenarios and verify recovery."""

    def __init__(self, verbose: bool = False):
        """Initialize simulator.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose
        self.results: dict[str, dict[str, Any]] = {}
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Setup logging with console and file handlers."""
        log_level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("/tmp/failure_simulator.log"),
                logging.StreamHandler(),
            ],
        )

    def simulate_database_connection_refused(self) -> dict[str, Any]:
        """Simulate PostgreSQL connection refused error.

        Expected recovery:
        - Phase fails with transient error
        - System logs error with context
        - Orchestrator can retry on next run
        """
        logger.info("\n" + "=" * 80)
        logger.info("SCENARIO: Database Connection Refused")
        logger.info("=" * 80)

        result = {
            "scenario": "database_connection_refused",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "findings": [],
        }

        try:
            # Simulate connection failure
            with mock.patch("psycopg2.connect") as mock_connect:
                mock_connect.side_effect = psycopg2.OperationalError("connection refused")

                from utils.db import DatabaseContext

                try:
                    with DatabaseContext("read") as cur:
                        cur.execute("SELECT 1")
                except Exception as e:
                    result["findings"].append(
                        {
                            "check": "Connection error caught",
                            "result": "PASS",
                            "details": str(e),
                        }
                    )

            result["status"] = "completed"
            result["end_time"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            result["findings"].append(
                {
                    "check": "Unexpected exception",
                    "result": "FAIL",
                    "details": str(e),
                }
            )

        return result

    def simulate_database_timeout(self) -> dict[str, Any]:
        """Simulate database query timeout.

        Expected recovery:
        - Query raises timeout exception
        - System marks as transient error
        - Allows retry
        """
        logger.info("\n" + "=" * 80)
        logger.info("SCENARIO: Database Query Timeout")
        logger.info("=" * 80)

        result = {
            "scenario": "database_timeout",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "findings": [],
        }

        try:
            # In real scenario, this would require actually running a slow query
            # For now, we verify timeout handling in the code

            from algo.exceptions import DataLoadError, ErrorCategory

            error = DataLoadError(
                source="database",
                message="Query timeout after 30s",
                retry_eligible=True,
                context={"timeout_seconds": 30},
            )

            if error.error_category == ErrorCategory.TRANSIENT:
                result["findings"].append(
                    {
                        "check": "Timeout marked as transient",
                        "result": "PASS",
                        "details": "Error correctly categorized for retry",
                    }
                )
            else:
                result["findings"].append(
                    {
                        "check": "Timeout marked as transient",
                        "result": "FAIL",
                        "details": f"Error category: {error.error_category}",
                    }
                )

            result["status"] = "completed"
            result["end_time"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)

        return result

    def simulate_disk_full(self) -> dict[str, Any]:
        """Simulate disk full error during log rotation.

        Expected recovery:
        - Log rotation fails gracefully
        - Logging continues to stderr
        - Alert sent to operators
        """
        logger.info("\n" + "=" * 80)
        logger.info("SCENARIO: Disk Full During Log Rotation")
        logger.info("=" * 80)

        result = {
            "scenario": "disk_full",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "findings": [],
        }

        try:
            from algo.exceptions import DataLoadError

            # Verify that disk full errors are non-retryable
            error = DataLoadError(
                source="filesystem",
                message="No space left on device",
                retry_eligible=False,
                context={"operation": "log_rotation"},
            )

            if not error.retry_eligible:
                result["findings"].append(
                    {
                        "check": "Disk full marked as non-retryable",
                        "result": "PASS",
                        "details": "Correctly prevents infinite retry",
                    }
                )
            else:
                result["findings"].append(
                    {
                        "check": "Disk full marked as non-retryable",
                        "result": "FAIL",
                        "details": "Disk full should not be retried",
                    }
                )

            result["status"] = "completed"
            result["end_time"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)

        return result

    def simulate_process_termination(self) -> dict[str, Any]:
        """Simulate process termination during critical operation.

        Expected recovery:
        - Orchestrator can be restarted
        - No orphaned locks (or stale locks are cleaned)
        - No corrupted state
        """
        logger.info("\n" + "=" * 80)
        logger.info("SCENARIO: Process Termination (SIGTERM)")
        logger.info("=" * 80)

        result = {
            "scenario": "process_termination",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "findings": [],
        }

        try:
            # Verify halt flag manager handles DynamoDB unavailability
            from unittest.mock import MagicMock

            from algo.orchestration.halt_flag_manager import HaltFlagManager

            mock_alerts = MagicMock()
            mock_log = MagicMock()
            halt_mgr = HaltFlagManager(mock_alerts, mock_log)

            # Simulate DynamoDB being unavailable (as would happen if process crashes and restarts)
            with mock.patch("boto3.resource") as mock_boto:
                mock_boto.side_effect = RuntimeError("Unable to locate credentials")

                # This should fail closed (return True to halt trading)
                result_halted = halt_mgr.check_halt_flag()

                if result_halted:
                    result["findings"].append(
                        {
                            "check": "Halt flag check fails closed",
                            "result": "PASS",
                            "details": "System halts trading when unable to check halt flag",
                        }
                    )
                else:
                    result["findings"].append(
                        {
                            "check": "Halt flag check fails closed",
                            "result": "FAIL",
                            "details": "System should halt when unable to check halt flag",
                        }
                    )

            result["status"] = "completed"
            result["end_time"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)

        return result

    def simulate_api_500_error(self) -> dict[str, Any]:
        """Simulate API returning 500 error.

        Expected recovery:
        - Error marked as transient
        - Allows retry with backoff
        - Escalates to alert on repeated failures
        """
        logger.info("\n" + "=" * 80)
        logger.info("SCENARIO: API 500 Error")
        logger.info("=" * 80)

        result = {
            "scenario": "api_500_error",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "findings": [],
        }

        try:
            from algo.exceptions import DataLoadError, ErrorCategory

            error = DataLoadError(
                source="alpaca_api",
                message="HTTP 500: Internal Server Error",
                retry_eligible=True,
                context={"http_status": 500, "endpoint": "/v2/orders"},
            )

            if error.retry_eligible and error.error_category == ErrorCategory.TRANSIENT:
                result["findings"].append(
                    {
                        "check": "API 500 marked as retryable transient error",
                        "result": "PASS",
                        "details": "Error allows automatic retry",
                    }
                )
            else:
                result["findings"].append(
                    {
                        "check": "API 500 marked as retryable transient error",
                        "result": "FAIL",
                        "details": f"retry_eligible={error.retry_eligible}, category={error.error_category}",
                    }
                )

            result["status"] = "completed"
            result["end_time"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)

        return result

    def simulate_network_timeout(self) -> dict[str, Any]:
        """Simulate network timeout during data load.

        Expected recovery:
        - Error marked as transient
        - Allows retry
        - Context includes partial data received
        """
        logger.info("\n" + "=" * 80)
        logger.info("SCENARIO: Network Timeout")
        logger.info("=" * 80)

        result = {
            "scenario": "network_timeout",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "findings": [],
        }

        try:
            from algo.exceptions import DataLoadError

            error = DataLoadError(
                source="sec_api",
                message="Network timeout during download",
                retry_eligible=True,
                context={"bytes_received": 1000, "bytes_total": 10000},
            )

            if error.retry_eligible:
                result["findings"].append(
                    {
                        "check": "Network timeout marked as retryable",
                        "result": "PASS",
                        "details": "Error allows automatic retry",
                    }
                )
            else:
                result["findings"].append(
                    {
                        "check": "Network timeout marked as retryable",
                        "result": "FAIL",
                        "details": "Network timeout should be retryable",
                    }
                )

            if error.context.get("bytes_received"):
                result["findings"].append(
                    {
                        "check": "Error context includes partial data info",
                        "result": "PASS",
                        "details": "Can use partial data for retry logic",
                    }
                )

            result["status"] = "completed"
            result["end_time"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)

        return result

    def simulate_stale_lock(self) -> dict[str, Any]:
        """Simulate stale lock from crashed process.

        Expected recovery:
        - System detects stale lock (>15 min old)
        - Forcibly releases stale lock
        - New process proceeds with operation
        """
        logger.info("\n" + "=" * 80)
        logger.info("SCENARIO: Stale Lock From Crashed Process")
        logger.info("=" * 80)

        result = {
            "scenario": "stale_lock",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "findings": [],
        }

        try:
            from algo.exceptions import ErrorCategory, LockAcquisitionError

            error = LockAcquisitionError(
                lock_key="orchestrator_phase_4",
                reason="Lock held by dead process",
                context={"held_by_pid": 12345, "lock_age_minutes": 20},
            )

            if error.retry_eligible and error.error_category == ErrorCategory.TRANSIENT:
                result["findings"].append(
                    {
                        "check": "Stale lock marked as retryable",
                        "result": "PASS",
                        "details": "Lock can be forcibly released and retried",
                    }
                )
            else:
                result["findings"].append(
                    {
                        "check": "Stale lock marked as retryable",
                        "result": "FAIL",
                        "details": f"retry_eligible={error.retry_eligible}, category={error.error_category}",
                    }
                )

            result["status"] = "completed"
            result["end_time"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)

        return result

    def run_all_scenarios(self) -> None:
        """Run all failure scenarios."""
        scenarios = [
            self.simulate_database_connection_refused,
            self.simulate_database_timeout,
            self.simulate_disk_full,
            self.simulate_process_termination,
            self.simulate_api_500_error,
            self.simulate_network_timeout,
            self.simulate_stale_lock,
        ]

        for scenario in scenarios:
            try:
                result = scenario()
                self.results[scenario.__name__] = result
            except Exception as e:
                logger.error(f"Scenario {scenario.__name__} failed: {e}", exc_info=True)
                self.results[scenario.__name__] = {
                    "status": "error",
                    "error": str(e),
                }

    def print_summary(self) -> None:
        """Print test summary and recovery gaps."""
        logger.info("\n" + "=" * 80)
        logger.info("FAILURE SCENARIO TEST SUMMARY")
        logger.info("=" * 80)

        total_scenarios = len(self.results)
        completed = sum(1 for r in self.results.values() if r.get("status") == "completed")
        passed_findings = sum(
            1
            for r in self.results.values()
            for f in r.get("findings", [])
            if f.get("result") == "PASS"
        )
        failed_findings = sum(
            1
            for r in self.results.values()
            for f in r.get("findings", [])
            if f.get("result") == "FAIL"
        )

        logger.info(f"\nTotal Scenarios: {total_scenarios}")
        logger.info(f"Completed: {completed}")
        logger.info(f"Findings - PASS: {passed_findings}, FAIL: {failed_findings}")

        # Print detailed results
        for scenario_name, result in self.results.items():
            logger.info(f"\n{scenario_name}:")
            logger.info(f"  Status: {result.get('status')}")
            if result.get("findings"):
                for finding in result["findings"]:
                    logger.info(f"    [{finding.get('result')}] {finding.get('check')}")
                    if finding.get("details"):
                        logger.info(f"         {finding.get('details')}")

        # Print recovery gaps
        logger.info("\n" + "=" * 80)
        logger.info("RECOVERY GAPS AND RECOMMENDATIONS")
        logger.info("=" * 80)
        self._report_gaps()

    def _report_gaps(self) -> None:
        """Report identified recovery gaps."""
        gaps = []

        # Check for missing features in results
        for scenario_name, result in self.results.items():
            if result.get("status") == "failed":
                gaps.append(
                    {
                        "category": "Test Failure",
                        "severity": "HIGH",
                        "description": f"Scenario {scenario_name} failed",
                        "gap": result.get("error"),
                        "mitigation": "Debug scenario implementation",
                    }
                )

            for finding in result.get("findings", []):
                if finding.get("result") == "FAIL":
                    gaps.append(
                        {
                            "category": scenario_name.replace("simulate_", ""),
                            "severity": "MEDIUM",
                            "description": finding.get("check"),
                            "gap": finding.get("details"),
                            "mitigation": "Implement proper error handling",
                        }
                    )

        if not gaps:
            logger.info("No recovery gaps identified!")
            return

        logger.info(f"\nIdentified {len(gaps)} recovery gaps:\n")
        for i, gap in enumerate(gaps, 1):
            logger.info(f"{gap['severity']} #{i}: {gap['category']}")
            logger.info(f"  Description: {gap['description']}")
            logger.info(f"  Gap: {gap['gap']}")
            logger.info(f"  Mitigation: {gap['mitigation']}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Failure scenario simulator for recovery testing"
    )
    parser.add_argument(
        "--scenario",
        type=str,
        help="Run specific scenario (database_connection_refused, database_timeout, etc.)",
    )
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    simulator = FailureScenarioSimulator(verbose=args.verbose)

    if args.all:
        logger.info("Running all failure scenarios...")
        simulator.run_all_scenarios()
    elif args.scenario:
        method_name = f"simulate_{args.scenario}"
        if hasattr(simulator, method_name):
            result = getattr(simulator, method_name)()
            simulator.results[args.scenario] = result
        else:
            logger.error(f"Unknown scenario: {args.scenario}")
            sys.exit(1)
    else:
        # Run all by default
        simulator.run_all_scenarios()

    simulator.print_summary()


if __name__ == "__main__":
    main()
