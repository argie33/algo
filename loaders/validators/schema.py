"""Validate row schema matches expected columns."""

from typing import Any

from .base import DataValidator


class SchemaValidator(DataValidator):

    def __init__(
        self,
        expected_columns: list[str],
        allow_extra: bool = True,
        fail_fast: bool = True,
    ) -> None:
        """Initialize with expected column spec.

        Args:
            expected_columns: List of column names that must exist
            allow_extra: If True, extra columns are allowed. If False, raise on extra columns.
            fail_fast: If True, raise on first error. If False, collect all.
        """
        super().__init__(fail_fast=fail_fast)
        self.expected_columns = expected_columns
        self.allow_extra = allow_extra

    def check(self, data: dict[str, Any] | Any, context: str = "") -> bool:
        """Check row schema matches expected columns.

        Args:
            data: Dict row to validate
            context: Optional context for error

        Returns:
            True if schema valid

        Raises:
            ValueError: If schema doesn't match (when fail_fast=True)
        """
        if not isinstance(data, dict):
            self._raise_or_collect(f"[VALIDATE_SCHEMA] {context}: Expected dict, got {type(data).__name__}")
            return False

        # Check for missing columns
        row_columns = set(data.keys())
        expected_set = set(self.expected_columns)
        missing = expected_set - row_columns

        if missing:
            msg = (
                f"[VALIDATE_SCHEMA] {context}: Missing columns: {', '.join(sorted(missing))}. "
                f"Expected: {', '.join(sorted(expected_set))}"
            )
            self._raise_or_collect(msg)
            return False

        # Check for extra columns if not allowed
        if not self.allow_extra:
            extra = row_columns - expected_set
            if extra:
                msg = (
                    f"[VALIDATE_SCHEMA] {context}: Unexpected columns: {', '.join(sorted(extra))}. "
                    f"Expected only: {', '.join(sorted(expected_set))}"
                )
                self._raise_or_collect(msg)
                return False

        return True
