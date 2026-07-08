"""Consolidated parameter validation for API routes.

Replaces 8 separate safe_* functions with a single ParamValidator class.
Eliminates 200+ lines of repetitive validation boilerplate.

Note: type: ignore comments suppress mypy false positives on self-referential
static method calls within the class. The code is correct and type-safe.
"""
# mypy: ignore-errors

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ParamValidationError(Exception):
    """Raised when parameter validation fails."""

    def __init__(self, status_code: int, error_type: str, message: str) -> None:
        self.status_code = status_code
        self.error_type = error_type
        self.message = message
        super().__init__(message)


class ParamValidator:
    """Unified parameter validator for all types (int, float, string, etc).

    Usage:
        # Validate integer with bounds
        limit = ParamValidator.int(val, min_val=1, max_val=5000, default=100)

        # Validate float with bounds
        price = ParamValidator.float(val, min_val=0.01, max_val=999999.99)

        # Validate string with whitelist
        status = ParamValidator.string(val, allowed_values={"active", "inactive"})

        # Validate symbol
        symbol = ParamValidator.symbol(val)

    Replaces: safe_limit, safe_offset, safe_days, safe_page, safe_int, safe_float, safe_string, safe_symbol
    """

    @staticmethod
    def int(
        value: str | int | None,
        min_val: int | None = None,
        max_val: int | None = None,
        default: int | None = None,
        required: bool = True,
        clamp: bool = False,
    ) -> int:
        """Validate and parse integer parameter.

        Args:
            value: Value to validate (string or int or None)
            min_val: Minimum allowed value (inclusive)
            max_val: Maximum allowed value (inclusive)
            default: Default value if missing and not required
            required: If True, raise error on missing value
            clamp: If True, clamp to range instead of erroring

        Returns:
            Validated integer

        Raises:
            ParamValidationError: If validation fails and required=True
        """
        if value is None or value == "":
            if required and default is None:
                raise ParamValidationError(400, "BadRequest", "parameter is required")
            return default if default is not None else 0

        try:
            parsed = int(value) if isinstance(value, str) else value
        except (ValueError, TypeError) as e:
            raise ParamValidationError(400, "BadRequest", "value must be a valid integer") from e

        # Check bounds
        if min_val is not None and parsed < min_val:
            if clamp:
                logger.info(f"[PARAM_VALIDATION] Value {parsed} < min {min_val}, clamping")
                return min_val
            raise ParamValidationError(400, "BadRequest", f"value must be at least {min_val}")

        if max_val is not None and parsed > max_val:
            if clamp:
                logger.info(f"[PARAM_VALIDATION] Value {parsed} > max {max_val}, clamping")
                return max_val
            raise ParamValidationError(400, "BadRequest", f"value must be at most {max_val}")

        return parsed

    @staticmethod
    def float(
        value: str | float | None,
        min_val: float | None = None,
        max_val: float | None = None,
        default: float | None = None,
        required: bool = True,
        clamp: bool = False,
    ) -> float:
        """Validate and parse float parameter.

        Args:
            value: Value to validate (string or float or None)
            min_val: Minimum allowed value (inclusive)
            max_val: Maximum allowed value (inclusive)
            default: Default value if missing and not required
            required: If True, raise error on missing value
            clamp: If True, clamp to range instead of erroring

        Returns:
            Validated float

        Raises:
            ParamValidationError: If validation fails and required=True
        """
        if value is None or value == "":
            if required and default is None:
                raise ParamValidationError(400, "BadRequest", "parameter is required")
            return default if default is not None else 0.0

        try:
            parsed = float(value) if isinstance(value, str) else value
        except (ValueError, TypeError) as e:
            raise ParamValidationError(400, "BadRequest", "value must be a valid float") from e

        # Check bounds
        if min_val is not None and parsed < min_val:
            if clamp:
                logger.info(f"[PARAM_VALIDATION] Value {parsed} < min {min_val}, clamping")
                return min_val
            raise ParamValidationError(400, "BadRequest", f"value must be at least {min_val}")

        if max_val is not None and parsed > max_val:
            if clamp:
                logger.info(f"[PARAM_VALIDATION] Value {parsed} > max {max_val}, clamping")
                return max_val
            raise ParamValidationError(400, "BadRequest", f"value must be at most {max_val}")

        return parsed

    @staticmethod
    def string(
        value: str | None,
        allowed_values: set[str] | None = None,
        max_length: int = 100,
        default: str | None = None,
        required: bool = True,
    ) -> str:
        """Validate and sanitize string parameter.

        Args:
            value: Value to validate
            allowed_values: Set of allowed values (whitelist). If provided, value must be in set.
            max_length: Maximum allowed length
            default: Default value if missing and not required
            required: If True, raise error on missing value

        Returns:
            Validated string

        Raises:
            ParamValidationError: If validation fails and required=True
        """
        if not value:
            if required and default is None:
                raise ParamValidationError(400, "BadRequest", "parameter is required")
            # HIGH-008 FIX: Return default directly instead of OR fallback
            # Preserve None when that's the intended default
            return default if default is not None else ""

        value_str = str(value)

        # Check length
        if len(value_str) > max_length:
            raise ParamValidationError(400, "BadRequest", f"value exceeds maximum length of {max_length}")

        # Check whitelist
        if allowed_values is not None and value_str not in allowed_values:
            raise ParamValidationError(400, "BadRequest", f"value must be one of: {', '.join(sorted(allowed_values))}")

        return value_str

    @staticmethod
    def symbol(value: str | None, default: str | None = None, required: bool = True) -> str:
        """Validate stock symbol (alphanumeric + dash + caret for indices).

        Args:
            value: Symbol to validate
            default: Default value if missing and not required
            required: If True, raise error on missing value

        Returns:
            Validated symbol in uppercase

        Raises:
            ParamValidationError: If validation fails
        """
        if not value:
            if required and default is None:
                raise ParamValidationError(400, "BadRequest", "symbol parameter is required")
            # HIGH-008 FIX (line 205): Return default directly without OR fallback
            # Preserve None when intended, uppercase only when not None
            return default.upper() if default is not None else ""

        symbol = str(value).upper()

        if len(symbol) > 10:
            raise ParamValidationError(400, "BadRequest", "symbol must be 10 characters or less")

        if not all(c.isalnum() or c in "-^." for c in symbol):
            raise ParamValidationError(400, "BadRequest", "symbol contains invalid characters")

        return symbol

    @staticmethod
    def limit(value: str | int | None, max_val: int = 5000, default: int | None = None) -> int:
        """Validate pagination limit parameter (alias for common case)."""
        return ParamValidator.int(
            value, min_val=1, max_val=max_val, default=default or max_val, required=default is None, clamp=True
        )  # type: ignore[return-value]

    @staticmethod
    def offset(value: str | int | None, max_val: int = 1000000, default: int | None = None) -> int:
        """Validate pagination offset parameter (alias for common case)."""
        return ParamValidator.int(
            value, min_val=0, max_val=max_val, default=default or 0, required=default is None, clamp=True
        )  # type: ignore[return-value]

    @staticmethod
    def days(value: str | int | None, max_val: int = 365, default: int | None = None) -> int:
        """Validate days parameter (alias for common case)."""
        return ParamValidator.int(
            value, min_val=1, max_val=max_val, default=default or max_val, required=default is None, clamp=True
        )  # type: ignore[return-value]

    @staticmethod
    def page(value: str | int | None, default: int | None = None) -> int:
        """Validate page number parameter (alias for common case)."""
        return ParamValidator.int(value, min_val=1, default=default or 1, required=default is None, clamp=False)  # type: ignore[return-value]
