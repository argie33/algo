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

    def __init__(self, config: "PatrolConfig"):
        self.config = config
        self.results: list[CheckResult] = []

    @abstractmethod
    def run(self, cur) -> list[CheckResult]:
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
