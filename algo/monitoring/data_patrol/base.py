#!/usr/bin/env python3
"""Base check class for data patrol checks."""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import PatrolConfig

logger = logging.getLogger(__name__)


class CheckResult:
    """Unified result format for a patrol check."""

    def __init__(
        self,
        check_name: str,
        severity: str,
        target_table: str,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        self.check_name = check_name
        self.severity = severity
        self.target_table = target_table
        self.message = message
        # Preserve None to distinguish "no details provided" from "details intentionally empty"
        self.details = details if details is not None else {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check_name,
            "severity": self.severity,
            "target": self.target_table,
            "message": self.message,
            "details": self.details,
        }


class BaseCheck(ABC):
    """Base class for all data patrol checks.

    Subclasses implement specific data quality/integrity checks.
    """

    def __init__(self, config: "PatrolConfig | None" = None):
        if config is None:
            raise ValueError(
                "BaseCheck requires explicit PatrolConfig. "
                "Silent fallback to empty dict would run data quality checks with no configured thresholds. "
                "Cannot execute patrol checks without knowing which values are acceptable. "
                "Pass config from DataPatrol or provide explicit PatrolConfig instance."
            )
        self.config: PatrolConfig = config
        self.results: list[CheckResult] = []

    @abstractmethod
    def run(self, cur: Any) -> list[CheckResult]:
        """Execute the check and return results.

        Args:
            cur: Database cursor

        Returns:
            List of CheckResult objects
        """

    def log(
        self,
        check_name: str,
        severity: str,
        target: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> CheckResult:
        """Create and store a result."""
        result = CheckResult(check_name, severity, target, message, details)
        self.results.append(result)
        return result


class DataPatrol:
    """Data patrol orchestrator - runs all data quality checks."""

    def __init__(self, config: "PatrolConfig | None" = None) -> None:
        """Initialize data patrol.

        Raises:
            ValueError: If config is None (patrol checks require configured thresholds)
        """
        if config is None:
            raise ValueError(
                "DataPatrol requires explicit PatrolConfig. "
                "Silent fallback to empty PatrolConfig() would run data quality checks with no configured thresholds. "
                "Cannot execute patrol checks without knowing which values are acceptable. "
                "Pass PatrolConfig instance with loaded thresholds from database."
            )
        self.config: PatrolConfig = config
        self.results: list[CheckResult] = []
        self.run_id = ""

    def run(self, quick: bool = False, validate_alpaca: bool = False) -> dict[str, Any]:
        """Run all data patrol checks and return summary.

        Args:
            quick: Run only critical checks if True
            validate_alpaca: Cross-validate against Alpaca if True

        Returns:
            dict with keys: ready (bool), findings (list), errors (int), warnings (int)
        """
        import time
        import uuid

        from psycopg2.extras import DictCursor

        from utils.db.connection import get_db_connection

        from .checks import (
            AlignmentChecker,
            CompositeScoreReconciliationChecker,
            CoverageChecker,
            FinancialStatementFlagDriftChecker,
            NewXbrlConceptChecker,
            PillarScoreReconciliationChecker,
            PriceSanityChecker,
            QualityChecker,
            ScoreRatioOutlierChecker,
            SpecializedChecker,
            StalenessChecker,
            StatisticalAnomalyChecker,
            TieOutChecker,
            XbrlConceptContinuityChecker,
        )
        from .config import CRIT, ERROR

        self.run_id = uuid.uuid4().hex
        run_started = time.monotonic()
        conn = None
        try:
            conn = get_db_connection(max_retries=2, timeout=30)
            cur = conn.cursor(cursor_factory=DictCursor)

            # Run all checks
            checkers: list[BaseCheck] = [
                StalenessChecker(self.config),
                CoverageChecker(self.config),
                QualityChecker(self.config),
                PriceSanityChecker(self.config),
                AlignmentChecker(self.config),
                SpecializedChecker(self.config),
                TieOutChecker(self.config),
                FinancialStatementFlagDriftChecker(self.config),
                NewXbrlConceptChecker(self.config),
                XbrlConceptContinuityChecker(self.config),
                StatisticalAnomalyChecker(self.config),
                ScoreRatioOutlierChecker(self.config),
                CompositeScoreReconciliationChecker(self.config),
                PillarScoreReconciliationChecker(self.config),
            ]

            for checker in checkers:
                try:
                    results = checker.run(cur)
                    self.results.extend(results)
                except Exception as e:
                    logger.error(f"Checker {checker.__class__.__name__} failed: {e}", exc_info=True)
                    self.results.append(
                        CheckResult(
                            check_name="checker_execution",
                            severity=ERROR,
                            target_table="patrol",
                            message=f"{checker.__class__.__name__} failed: {e}",
                        )
                    )

            # BUG FOUND 2026-09-07 (goal: stock_scores/tie-out CI sanity audit): PatrolLogger
            # (this module's own logger.py, INSERT INTO data_patrol_log fully implemented and
            # unit-tested) was never actually called from here - self.run_id above sat as a
            # permanent "" placeholder, and data_patrol_log's last row was 2026-07-05 despite
            # this run() executing on every scheduled ECS invocation since. The 2026-09-01 fix
            # in this same function wired up notify() (a text summary in algo_notifications)
            # but not this - the lambda API's own data-quality dashboard endpoints
            # (lambda/api/routes/algo_handlers/market/data_quality.py, monitoring.py) read
            # data_patrol_log directly and were silently showing a 2-month-stale snapshot.
            # Wired here, in the same cur/conn this run already holds, fail-safe (a logging
            # failure must never crash or fail the patrol run itself - same fail-safe posture
            # already used for notify() below).
            try:
                from .logger import PatrolLogger

                patrol_logger = PatrolLogger(self.run_id)
                patrol_logger.log_results(cur, self.results)
                patrol_logger.log_performance(cur, time.monotonic() - run_started, "OK")
                conn.commit()
            except Exception as log_err:
                logger.error(f"[DataPatrol] Failed to persist findings to data_patrol_log: {log_err}")

            cur.close()
        except Exception as e:
            logger.error(f"Data patrol execution failed: {e}", exc_info=True)
            self.results.append(
                CheckResult(
                    check_name="patrol_execution",
                    severity=ERROR,
                    target_table="patrol",
                    message=f"Patrol execution failed: {e}",
                )
            )
        finally:
            if conn:
                conn.close()

        # Aggregate findings by severity
        errors = sum(1 for r in self.results if r.severity == ERROR or r.severity == CRIT)
        warnings = sum(1 for r in self.results if r.severity == "warn")

        # Ready if no critical errors (ERROR or CRIT)
        ready = errors == 0

        # BUG FOUND 2026-09-01 (/goal session): DataPatrol is the codebase's central data-
        # integrity monitor (staleness/coverage/quality/price-sanity/alignment/specialized
        # checks across 6 checkers), but this run() - the only place results get aggregated -
        # never called notify() anywhere. Findings only ever reached a human via the CLI
        # entrypoint's (algo_data_patrol.py) process exit code and log output - if nobody is
        # watching the ECS task's exit status/CloudWatch logs, a genuine data-integrity failure
        # (e.g. a stale price_daily table, or - live-confirmed 2026-09-01 - aaii_sentiment
        # sitting 12 days stale against this checker's own 7-day threshold after AAII's
        # anti-bot protection started blocking every fetch attempt) goes completely unnoticed.
        # Same "computed but never delivered" alert gap already found and fixed today in
        # load_market_constituents.py, Phase 9's risk-alert path, and AlgoConfig's partial-DB-
        # load-failure warning. Wired here (not only in the CLI entrypoint) so any caller -
        # not just the scheduled ECS task - gets the alert. Fail-safe: swallows notify()
        # failures so alerting can never crash the patrol run itself.
        if errors > 0 or warnings > 0:
            severity = "critical" if errors > 0 else "warning"
            failing = [r for r in self.results if r.severity in (ERROR, CRIT, "warn")]
            summary_lines = [
                f"[{r.severity.upper()}] {r.check_name} ({r.target_table}): {r.message}" for r in failing[:10]
            ]
            more = f" ...and {len(failing) - 10} more" if len(failing) > 10 else ""
            try:
                from algo.reporting import notify

                notify(
                    severity=severity,
                    title="Data Patrol Findings" if errors > 0 else "Data Patrol Warnings",
                    message=(
                        f"Data patrol found {errors} error(s) and {warnings} warning(s) across "
                        f"{len(self.results)} checks. ready={ready}.\n" + "\n".join(summary_lines) + more
                    ),
                    details={"errors": errors, "warnings": warnings, "ready": ready},
                )
            except (ValueError, TypeError, RuntimeError) as notify_err:
                logger.error(f"[DataPatrol] Failed to send data-patrol-findings alert: {notify_err}")

        return {
            "ready": ready,
            "findings": [r.to_dict() for r in self.results],
            "errors": errors,
            "warnings": warnings,
            "total_checks": len(self.results),
        }

    def get_issues(self) -> list[CheckResult]:
        return self.results
