"""Base validator class for unified validation framework."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DataValidator:
    """Base class for all validators. Defines validation contract."""

    def __init__(self, fail_fast: bool = True) -> None:
        """Initialize validator.

        Args:
            fail_fast: If True, raise exception on first error. If False, collect all errors.
        """
        self.fail_fast = fail_fast
        self.errors: list[str] = []

    def check(self, data: dict[str, Any] | Any, context: str = "") -> bool:
        """Check if data is valid. Override in subclasses.

        Args:
            data: Data to validate (usually a dict row from database)
            context: Optional context for error messages (e.g., symbol, date)

        Returns:
            True if valid, False otherwise (when fail_fast=False)

        Raises:
            ValueError: If validation fails and fail_fast=True
        """
        raise NotImplementedError("Subclasses must implement check()")

    def get_errors(self) -> list[str]:
        """Return all collected errors (when fail_fast=False)."""
        return self.errors

    def clear_errors(self) -> None:
        """Clear collected errors."""
        self.errors = []

    def _raise_or_collect(self, message: str) -> None:
        """Raise error immediately or collect it based on fail_fast setting."""
        if self.fail_fast:
            raise ValueError(message)
        else:
            self.errors.append(message)
            logger.warning(message)
