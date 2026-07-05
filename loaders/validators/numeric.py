"""Validate numeric fields (not NaN, Infinity, within range)."""

import math
from typing import Any

from .base import DataValidator


class NumericValidator(DataValidator):
    """Check that numeric fields are valid (not NaN, Infinity, within optional range)."""

    def __init__(
        self,
        fields: dict[str, dict[str, Any]] | None = None,
        fail_fast: bool = True,
    ) -> None:
        """Initialize with field specs.

        Args:
            fields: Dict mapping field_name -> {"min": val, "max": val} for range checks (optional).
                   Example: {"price": {"min": 0, "max": 10000}, "volume": {"min": 0}}
            fail_fast: If True, raise on first error. If False, collect all.
        """
        super().__init__(fail_fast=fail_fast)
        self.fields = fields or {}

    def check(self, data: dict[str, Any] | Any, context: str = "") -> bool:
        """Check numeric fields are valid (not NaN, not Infinity, in range).

        Args:
            data: Dict row to validate
            context: Optional context for error (e.g., symbol='AAPL')

        Returns:
            True if all fields valid

        Raises:
            ValueError: If field is NaN, Infinity, or out of range (when fail_fast=True)
        """
        if not isinstance(data, dict):
            self._raise_or_collect(f"[VALIDATE_NUMERIC] {context}: Expected dict, got {type(data).__name__}")
            return False

        valid = True

        for field_name, spec in self.fields.items():
            if field_name not in data:
                continue

            value = data[field_name]
            if value is None:
                continue

            # Check if numeric
            try:
                num_val = float(value)
            except (ValueError, TypeError):
                msg = (
                    f"[VALIDATE_NUMERIC] {context} [{field_name}]: "
                    f"Cannot convert to float: {value} (type: {type(value).__name__})"
                )
                self._raise_or_collect(msg)
                valid = False
                continue

            # Check for NaN or Infinity
            if math.isnan(num_val):
                msg = f"[VALIDATE_NUMERIC] {context} [{field_name}]: Value is NaN (data corruption indicator)"
                self._raise_or_collect(msg)
                valid = False
                continue

            if math.isinf(num_val):
                msg = f"[VALIDATE_NUMERIC] {context} [{field_name}]: Value is Infinity (data corruption indicator)"
                self._raise_or_collect(msg)
                valid = False
                continue

            # Check range if specified
            if "min" in spec and num_val < spec["min"]:
                msg = f"[VALIDATE_NUMERIC] {context} [{field_name}]: Value {num_val} below minimum {spec['min']}"
                self._raise_or_collect(msg)
                valid = False

            if "max" in spec and num_val > spec["max"]:
                msg = f"[VALIDATE_NUMERIC] {context} [{field_name}]: Value {num_val} above maximum {spec['max']}"
                self._raise_or_collect(msg)
                valid = False

        return valid
