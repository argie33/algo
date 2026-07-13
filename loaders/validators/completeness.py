"""Validate that required fields are present and not None."""

from typing import Any

from .base import DataValidator


class CompletenessValidator(DataValidator):

    def __init__(self, required_fields: list[str], fail_fast: bool = True) -> None:
        """Initialize with list of required field names.

        Args:
            required_fields: List of field names that must be present and non-None
            fail_fast: If True, raise on first missing field. If False, collect all.
        """
        super().__init__(fail_fast=fail_fast)
        self.required_fields = required_fields

    def check(self, data: dict[str, Any] | Any, context: str = "") -> bool:
        """Check all required fields are present and not None.

        Args:
            data: Dict row to validate
            context: Optional context for error (e.g., symbol='AAPL')

        Returns:
            True if all required fields present and non-None

        Raises:
            ValueError: If required field missing (when fail_fast=True)
        """
        if not isinstance(data, dict):
            self._raise_or_collect(f"[VALIDATE_COMPLETENESS] {context}: Expected dict, got {type(data).__name__}")
            return False

        missing = []
        for field in self.required_fields:
            if field not in data or data[field] is None:
                missing.append(field)

        if missing:
            msg = (
                f"[VALIDATE_COMPLETENESS] {context}: Missing required fields: {', '.join(missing)}. "
                f"Expected all of: {', '.join(self.required_fields)}"
            )
            self._raise_or_collect(msg)
            return False

        return True
