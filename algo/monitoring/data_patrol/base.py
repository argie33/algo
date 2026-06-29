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
        self.details = details or {}

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
        from psycopg2.extras import DictCursor

        from utils.db.connection import get_db_connection

        from .checks import (
            AlignmentChecker,
            CoverageChecker,
            PriceSanityChecker,
            QualityChecker,
            SpecializedChecker,
            StalenessChecker,
        )
        from .config import CRIT, ERROR

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
            ]

            for checker in checkers:
                try:
                    results = checker.run(cur)
                    self.results.extend(results)
                except Exception as e:
                    logger.error(f"Checker {checker.__class__.__name__} failed: {e}", exc_info=True)
                    self.results.append(CheckResult(
                        check_name="checker_execution",
                        severity=ERROR,
                        target_table="patrol",
                        message=f"{checker.__class__.__name__} failed: {e}",
                    ))

            cur.close()
        except Exception as e:
            logger.error(f"Data patrol execution failed: {e}", exc_info=True)
            self.results.append(CheckResult(
                check_name="patrol_execution",
                severity=ERROR,
                target_table="patrol",
                message=f"Patrol execution failed: {e}",
            ))
        finally:
            if conn:
                conn.close()

        # Aggregate findings by severity
        errors = sum(1 for r in self.results if r.severity == ERROR or r.severity == CRIT)
        warnings = sum(1 for r in self.results if r.severity == "warn")

        # Ready if no critical errors (ERROR or CRIT)
        ready = errors == 0

        return {
            "ready": ready,
            "findings": [r.to_dict() for r in self.results],
            "errors": errors,
            "warnings": warnings,
            "total_checks": len(self.results),
        }

    def run_checks(self) -> None:
        """Run all data patrol checks."""

    def get_issues(self) -> list[CheckResult]:
        """Get all issues found by patrol."""
        return self.results
