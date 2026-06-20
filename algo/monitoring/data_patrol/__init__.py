#!/usr/bin/env python3
"""Modular data patrol orchestrator.

This module coordinates multiple data quality checks and logs results.
"""

import argparse
import json
import logging
import socket
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils.db import DatabaseContext
from utils.infrastructure.timeout import ExecutionTimeout

from .base import CheckResult
from .checks import (
    AlignmentChecker,
    CoverageChecker,
    PriceSanityChecker,
    QualityChecker,
    SpecializedChecker,
    StalenessChecker,
)
from .config import CRIT, ERROR, INFO, WARN, PatrolConfig
from .logger import PatrolLogger


logger = logging.getLogger(__name__)


class DataPatrol:
    """Orchestrate data patrol checks and coordinate results."""

    def __init__(self):
        self.results: list[CheckResult] = []
        self.run_id: str = ""
        self.config: PatrolConfig = None
        self.logger: PatrolLogger = None
        self.check_timings: dict[str, float] = {}

    def run(self, quick: bool = False, validate_alpaca: bool = False) -> dict[str, Any]:
        """Run all data patrol checks.

        Args:
            quick: Run only critical checks
            validate_alpaca: Cross-validate against Alpaca

        Returns:
            Summary dict with results and metadata
        """
        socket.setdefaulttimeout(30.0)

        self.run_id = f"PATROL-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        start_time = time.time()

        with DatabaseContext("write") as cur:
            logger.info(f"DATA PATROL — {self.run_id}")

            # Load configuration
            self.config = PatrolConfig(cur)
            self.logger = PatrolLogger(self.run_id)

            # Log configuration snapshot
            try:
                self.logger.log_configuration(cur, self.config.as_dict())
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"Failed to log configuration: {e}")

            # Run checks
            self._run_checks(cur, quick)

            # Log all results
            try:
                self.logger.log_results(cur, self.results)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"Failed to log results: {e}")

            elapsed = time.time() - start_time
            return self.summarize(cur, elapsed)

    def _run_checks(self, cur, quick: bool) -> None:
        """Execute all configured checks."""
        checks = [
            ("staleness", StalenessChecker(self.config)),
            ("quality", QualityChecker(self.config)),
            ("price_sanity", PriceSanityChecker(self.config)),
            ("coverage", CoverageChecker(self.config)),
        ]

        if not quick:
            checks.extend([
                ("alignment", AlignmentChecker(self.config)),
                ("specialized", SpecializedChecker(self.config)),
            ])

        for check_name, checker in checks:
            start = time.time()
            try:
                results = checker.run(cur)
                self.results.extend(results)
                elapsed = time.time() - start
                self.check_timings[check_name] = elapsed
                if elapsed > 10:
                    logger.warning(f"[patrol_perf] {check_name} took {elapsed:.1f}s (slow)")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                elapsed = time.time() - start
                self.check_timings[check_name] = elapsed
                logger.error(f"Check {check_name} failed: {e}", exc_info=True)

    def summarize(self, cur, elapsed_seconds: float | None = None) -> dict[str, Any]:
        """Summarize patrol results."""
        counts = {INFO: 0, WARN: 0, ERROR: 0, CRIT: 0}
        for result in self.results:
            counts[result.severity] = counts.get(result.severity, 0) + 1

        logger.info(f"PATROL RESULTS — {self.run_id}")
        logger.info(f"  INFO:     {counts.get(INFO, 0)}")
        logger.info(f"  WARN:     {counts.get(WARN, 0)}")
        logger.info(f"  ERROR:    {counts.get(ERROR, 0)}")
        logger.info(f"  CRITICAL: {counts.get(CRIT, 0)}")
        if elapsed_seconds:
            perf_status = "OK" if elapsed_seconds < 120 else "SLOW"
            logger.info(f"  TIME:     {elapsed_seconds:.1f}s [{perf_status}]")

        # Show flagged findings
        flagged = [r for r in self.results if r.severity != INFO]
        if flagged:
            logger.info("FLAGGED:")
            for r in flagged:
                sev_pad = r.severity.upper().rjust(8)
                logger.info(
                    f"  [{sev_pad}] {r.check_name:20s} {r.target_table:28s} : {r.message}"
                )
        else:
            logger.info("No issues — all checks clean.")

        ready = counts.get(CRIT, 0) == 0 and counts.get(ERROR, 0) == 0
        logger.info(f"ALGO READY TO TRADE: {'YES' if ready else 'NO'}")

        # Update DynamoDB completion status
        try:
            self.logger.update_completion_status(ready, elapsed_seconds)
        except Exception as e:
            logger.warning(f"Could not update DynamoDB: {e}")

        # Log performance
        if elapsed_seconds:
            try:
                self.logger.log_performance(cur, elapsed_seconds, "OK" if ready else "FINDINGS")
            except Exception as e:
                logger.error(f"Failed to log performance: {e}")

        return {
            "run_id": self.run_id,
            "counts": counts,
            "ready": ready,
            "flagged": [r.to_dict() for r in flagged],
            "all_results": [r.to_dict() for r in self.results],
            "elapsed_seconds": elapsed_seconds,
        }


if __name__ == "__main__":
    try:
        with ExecutionTimeout(max_seconds=600, label="data_patrol"):
            parser = argparse.ArgumentParser(description="Data integrity patrol")
            parser.add_argument("--quick", action="store_true", help="Critical checks only")
            parser.add_argument(
                "--validate-alpaca", action="store_true", help="Cross-validate vs Alpaca"
            )
            parser.add_argument("--json", action="store_true", help="JSON output")
            args = parser.parse_args()

            p = DataPatrol()
            summary = p.run(quick=args.quick, validate_alpaca=args.validate_alpaca)

            if args.json:
                logger.info(json.dumps(summary, default=str, indent=2))

            import sys
            sys.exit(0 if summary["ready"] else 1)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Data patrol execution failed: {e}", exc_info=True)
        import sys
        sys.exit(1)
