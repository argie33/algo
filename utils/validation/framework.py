#!/usr/bin/env python3
"""
Centralized Validation Framework - Single Source of Truth for All Validation

This module provides unified validation for all data across the platform.
Supports both:
1. Class-based validators (composable, auditable)
2. Functional API (backward compatible with existing code)

All validation is fail-closed with explicit error logging and context tracking.
No silent defaults-missing data returns None, conversions are logged.
"""

import json
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Eastern timezone for all time-based conversions (CRITICAL: Must be America/New_York, not UTC)
EASTERN_TZ = ZoneInfo("America/New_York")


class StrictValidationError(Exception):
    """Raised when data conversion fails in strict mode."""


@dataclass
class ValidationResult:
    """Structured validation result with error details and cleaned data."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    data: Any | None = None
    context: str = ""
    validator_name: str = ""

    @property
    def valid(self) -> bool:
        """Alias for is_valid (backward compatibility)."""
        return self.is_valid

    def __repr__(self) -> str:
        status = "✓ VALID" if self.is_valid else "✗ INVALID"
        detail = f" ({len(self.errors)} error{'s' if len(self.errors) != 1 else ''})"
        ctx = f" [{self.context}]" if self.context else ""
        return f"{status}{detail}{ctx}"


class Validator(ABC):
    """Base class for all validators."""

    def __init__(self, name: str = "", context: str = "") -> None:
        self.name = name or self.__class__.__name__
        self.context = context

    @abstractmethod
    def validate(self, data: Any, context: str = "") -> ValidationResult:
        pass

    def __call__(self, data: Any, context: str = "") -> ValidationResult:
        return self.validate(data, context or self.context)


class TypeValidator(Validator):
    def __init__(
        self,
        expected_type: str,
        min_val: Any = None,
        max_val: Any = None,
        min_length: Any = None,
        max_length: Any = None,
    ) -> None:
        super().__init__()
        self.expected_type = expected_type.lower()
        self.min_val = min_val
        self.max_val = max_val
        self.min_length = min_length
        self.max_length = max_length

    def validate(self, data: Any, context: str = "") -> ValidationResult:
        errors = []
        cleaned = data

        if data is None:
            return ValidationResult(is_valid=True, data=None, context=context, validator_name=self.name)

        if self.expected_type in ("float", "numeric"):
            try:
                cleaned = self._validate_float(data, context)
            except ValueError as e:
                errors.append(str(e))
        elif self.expected_type in ("int", "integer"):
            try:
                cleaned = self._validate_int(data, context)
            except ValueError as e:
                errors.append(str(e))
        elif self.expected_type in ("str", "text", "string", "varchar"):
            if not isinstance(data, str):
                errors.append(f"{context}: expected string, got {type(data).__name__}")
            else:
                cleaned = data
        else:
            errors.append(f"Unknown type: {self.expected_type}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            data=cleaned,
            context=context,
            validator_name=self.name,
        )

    def _validate_float(self, data: Any, context: str) -> float:
        try:
            val = float(data)
            if self.min_val is not None and val < self.min_val:
                raise ValueError(f"{context}: {val} < min {self.min_val}")
            if self.max_val is not None and val > self.max_val:
                raise ValueError(f"{context}: {val} > max {self.max_val}")
            return val
        except (ValueError, TypeError) as e:
            raise ValueError(f"{context}: cannot convert {data!r} to float") from e

    def _validate_int(self, data: Any, context: str) -> int:
        try:
            val = int(data)
            if self.min_val is not None and val < self.min_val:
                raise ValueError(f"{context}: {val} < min {self.min_val}")
            if self.max_val is not None and val > self.max_val:
                raise ValueError(f"{context}: {val} > max {self.max_val}")
            return val
        except (ValueError, TypeError) as e:
            raise ValueError(f"{context}: cannot convert {data!r} to int") from e


class EnumValidator(Validator):
    def __init__(self, allowed_values: list[str], case_sensitive: bool = False) -> None:
        super().__init__()
        self.allowed_values = [str(v) for v in allowed_values]
        self.case_sensitive = case_sensitive

    def validate(self, data: Any, context: str = "") -> ValidationResult:
        if data is None:
            return ValidationResult(is_valid=True, data=None, context=context)

        data_str = str(data)
        values_to_check = self.allowed_values
        if not self.case_sensitive:
            data_str = data_str.lower()
            values_to_check = [v.lower() for v in self.allowed_values]

        if data_str in values_to_check:
            return ValidationResult(is_valid=True, data=data, context=context)

        errors = [f"{context}: value {data!r} not in {self.allowed_values}"]
        return ValidationResult(is_valid=False, errors=errors, data=data, context=context)


class PhaseValidator(Validator):
    VALID_STATUSES = {
        "ok",
        "success",
        "running",
        "pending",
        "halt",
        "halted",
        "failed",
        "completed",
        "skipped",
    }

    def __init__(self) -> None:
        super().__init__("PhaseValidator")

    def validate(self, data: Any, context: str = "") -> ValidationResult:
        if not isinstance(data, dict):
            errors = [f"{context}: expected dict, got {type(data).__name__}"]
            return ValidationResult(is_valid=False, errors=errors, context=context)

        all_errors = []
        cleaned = {}

        name = data.get("name")
        if not name:
            name = data.get("phase")
        if not name:
            all_errors.append(f"{context}: missing 'name' or 'phase' field")
        else:
            cleaned["name"] = str(name)

        status_raw = data.get("status")
        if not status_raw:
            all_errors.append(f"{context}: missing 'status' field")
        else:
            status = str(status_raw).lower().strip()
            if not status:
                all_errors.append(f"{context}: status field is empty after stripping whitespace")
            elif status not in self.VALID_STATUSES:
                all_errors.append(f"{context}: invalid status {status!r} (valid: {sorted(self.VALID_STATUSES)})")
            else:
                cleaned["status"] = status

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            data=cleaned if len(all_errors) == 0 else None,
            context=context,
            validator_name=self.name,
        )


class ValidatorRegistry:
    """Central registry of all validators."""

    def __init__(self) -> None:
        self._validators: dict[str, Validator] = {}
        self._metadata: dict[str, dict[str, str]] = {}

    def register(self, name: str, validator: Validator, description: str = "") -> None:
        self._validators[name] = validator
        self._metadata[name] = {
            "validator_class": validator.__class__.__name__,
            "description": description,
        }
        logger.debug(f"Registered validator: {name}")

    def validate(self, validator_name: str, data: Any, context: str = "") -> ValidationResult:
        if validator_name not in self._validators:
            raise ValueError(f"Unknown validator: {validator_name!r}")
        validator = self._validators[validator_name]
        return validator.validate(data, context=context)

    def get_validator(self, name: str) -> Validator | None:
        return self._validators.get(name)


_global_registry = ValidatorRegistry()


def get_global_registry() -> ValidatorRegistry:
    return _global_registry


# ──────────────────────────────────────────────────────────────────────────────
# UNIFIED FUNCTIONAL API - FOR BACKWARD COMPATIBILITY & EASE OF USE
# ──────────────────────────────────────────────────────────────────────────────
# These wrap the class-based system with a simpler functional interface.
# All validation is centralized here - one source of truth for all data conversion.


def safe_float(
    value: Any,
    default: float | None = None,
    *,
    context: str = "",
    strict: bool = False,
    field_name: str | None = None,
) -> float | None:
    """Convert value to float safely, handling NaN, Infinity, None.

    Args:
        value: Value to convert (can be str, int, float, None)
        default: Default value if conversion fails (None to require explicit handling; use strict=True for finance)
        context: Context string for logging (e.g., "symbol=AAPL")
        strict: If True, raise StrictValidationError instead of returning default (REQUIRED for all finance paths)
        field_name: Field name for error logging (preferred over context for new code)

    Returns:
        Float value or default if conversion fails

    Raises:
        ValueError: If value is NaN or Infinity (always fails fast - required for calculations)
        StrictValidationError: If strict=True and conversion fails
    """
    error_ctx = f"for {field_name}" if field_name else context

    if value is None:
        if strict:
            raise StrictValidationError(f"Cannot convert None to float {error_ctx}")
        if default is None:
            logger.warning(f"None value in float conversion {error_ctx} - returning None (must be handled by caller)")
        else:
            logger.warning(f"Converting None to {default} {error_ctx} - explicitly requested default")
        return default

    if isinstance(value, bool):
        if strict:
            raise StrictValidationError(f"Cannot convert bool to float {error_ctx}")
        return default

    try:
        f = float(value)
    except (ValueError, TypeError) as e:
        if strict:
            raise StrictValidationError(
                f"Cannot convert {field_name or 'value'}={value!r} to float {error_ctx}: {e}"
            ) from e
        if default is None:
            logger.warning(
                f"Failed to convert {value!r} to float {error_ctx} (returning None-caller must handle missing data): {e}"
            )
        else:
            logger.warning(f"Failed to convert {value!r} to float {error_ctx} (returning {default}): {e}")
        return default

    # Reject NaN and Infinity explicitly - fail fast instead of silently returning 0.0.
    # Position sizing, risk calculations, and other critical paths require valid data.
    # Silent degradation to 0.0 masks data errors that should be fixed, not ignored.
    if math.isnan(f):
        msg = f"NaN value in critical calculation {error_ctx} - data error must be fixed"
        logger.error(msg)
        raise ValueError(msg)
    if math.isinf(f):
        msg = f"Infinity value in critical calculation {error_ctx} - data error must be fixed"
        logger.error(msg)
        raise ValueError(msg)

    return f


def format_decimal_string(value: Any, precision: int = 2, allow_none: bool = True) -> str | None:
    """Convert financial value to string with fixed precision to prevent JSON float precision loss.

    Serializes as string (not float) to preserve penny-level accuracy across JSON boundaries.
    IEEE 754 floats lose precision on financial numbers; strings preserve exact values.

    Args:
        value: Value to convert (can be Decimal, float, int, str, None)
        precision: Number of decimal places (default 2 for dollars/percentages)
        allow_none: If True, return None for None values; if False, raise

    Returns:
        String representation with fixed precision, or None if allow_none=True and value is None

    Example:
        format_decimal_string(Decimal("123.456"), precision=2) → "123.46"
        format_decimal_string(1.23456789, precision=3) → "1.235"
        format_decimal_string(None, allow_none=True) → None
    """
    if value is None:
        if allow_none:
            logger.debug("Value is None - returning None as specified by allow_none=True")
            return None
        raise ValueError("Cannot convert None to decimal string")

    if isinstance(value, bool):
        raise ValueError("Cannot convert bool to decimal string")

    try:
        f = float(value)
        if math.isnan(f):
            raise ValueError("NaN value rejected")
        if math.isinf(f):
            raise ValueError("Infinity value rejected")
        return f"{f:.{precision}f}"
    except (ValueError, TypeError) as e:
        raise ValueError(f"Cannot convert {value!r} to decimal string") from e


def safe_int(
    value: Any, default: int | None = None, context: str = "", strict: bool = False, field_name: str | None = None
) -> int | None:
    """Convert value to int safely, handling None, invalid strings.

    PERMISSIVE MODE (default): Returns default value on failure, logs WARNING.
    STRICT MODE: Raises StrictValidationError on failure (pass strict=True to enable).

    Args:
        value: Value to convert (can be str, int, float, None)
        default: Default value if conversion fails (default: None for strict)
        context: Context string for logging
        strict: If True, raise StrictValidationError on failure; if False, return default
        field_name: Field name for error logging (preferred over context for new code)

    Returns:
        Int value or None (strict with error) / default (permissive) if conversion fails

    Raises:
        StrictValidationError: If strict=True and conversion fails
    """
    error_ctx = f"for {field_name}" if field_name else context

    if value is None:
        if strict:
            raise StrictValidationError(f"Cannot convert None to int {error_ctx}")
        return default

    if isinstance(value, bool):
        if strict:
            raise StrictValidationError(f"Cannot convert bool to int (ambiguous: {value!r}) {error_ctx}")
        return default

    try:
        return int(value)
    except (ValueError, TypeError) as e:
        if strict:
            raise StrictValidationError(f"Cannot convert {value!r} to int {error_ctx}: {e}") from e
        logger.warning(f"Cannot convert {value!r} to int {error_ctx}: {e}")
        return default


def safe_parse_date(value: Any, context: str = "", strict: bool = True) -> date | None:
    """Parse date from multiple formats: ISO, string, datetime.

    STRICT MODE (default): Logs ERROR on failure, returns None. Caller must handle.
    PERMISSIVE MODE: Logs WARNING on failure, returns None.

    Handles:
    - ISO format strings (2026-06-10)
    - datetime objects
    - date objects

    Returns None if parsing fails (logged as ERROR for visibility in strict mode).
    """
    if value is None:
        if strict:
            logger.error(f"Value is None in safe_parse_date {context}")
        else:
            logger.debug(f"Value is None in safe_parse_date {context} - returning None")
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except (ValueError, TypeError):
            pass

        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass

        if strict:
            logger.error(f"Failed to parse date {value!r} {context} - no format matched")
        else:
            logger.warning(f"Failed to parse date {value!r} {context} - no format matched")
        return None

    if strict:
        logger.error(f"Cannot parse {type(value).__name__} as date {context}")
    else:
        logger.warning(f"Cannot parse {type(value).__name__} as date {context}")
    return None


def safe_parse_datetime_et(value: Any, context: str = "") -> datetime:
    """Parse datetime string with timezone awareness (ET).

    Returns timezone-aware datetime in ET.

    Raises:
        ValueError: If value is None or parsing fails
    """
    if value is None:
        raise ValueError(f"{context}: cannot parse None as datetime")

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=EASTERN_TZ)
        return value

    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=EASTERN_TZ)
            return dt
        except (ValueError, TypeError) as e:
            raise ValueError(f"{context}: cannot parse datetime {value!r}") from e

    raise ValueError(f"{context}: cannot parse {type(value).__name__} as datetime")


def safe_json_loads(json_str: Any, default: Any = None, context: str = "") -> Any:
    """Parse JSON string safely with proper error logging.

    Args:
        json_str: JSON string or already-parsed object
        default: Default value if parsing fails
        context: Context string for logging

    Returns:
        Parsed object or default value
    """
    if isinstance(json_str, (dict, list)):
        return json_str

    if not isinstance(json_str, str):
        logger.warning(f"JSON parse: expected string, got {type(json_str).__name__} {context}")
        return default

    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"JSON parse failed {context}: {e}")
        return default


def safe_str(
    value: Any, default: str | None = None, context: str = "", strict: bool = True, field_name: str | None = None
) -> str | None:
    """Safely convert value to string with logging.

    STRICT MODE (default): Raises StrictValidationError on failure. No silent defaults.
    PERMISSIVE MODE: Returns default value on failure, logs WARNING.

    Args:
        value: Value to convert
        default: Default value if conversion fails (default: None for strict)
        context: Context string for logging
        strict: If True, raise StrictValidationError on failure; if False, return default
        field_name: Field name for error logging (preferred over context for new code)

    Returns:
        String value or None (strict with error) / default (permissive) if conversion fails

    Raises:
        StrictValidationError: If strict=True and conversion fails
    """
    error_ctx = f"for {field_name}" if field_name else context

    if value is None:
        if strict:
            raise StrictValidationError(f"Cannot convert None to str {error_ctx}")
        return default

    if isinstance(value, str):
        return value

    try:
        return str(value)
    except Exception as e:
        if strict:
            raise StrictValidationError(f"Failed to convert {value!r} to str {error_ctx}: {e}") from e
        logger.warning(f"Failed to convert {value!r} to str {error_ctx}: {e}")
        return default


def safe_bool(
    value: Any, default: bool | None = None, context: str = "", strict: bool = True, field_name: str | None = None
) -> bool | None:
    """Safely convert value to bool with logging.

    STRICT MODE (default): Raises StrictValidationError on failure. No silent defaults.
    PERMISSIVE MODE: Returns default value on failure, logs WARNING.

    Args:
        value: Value to convert
        default: Default value if conversion fails (default: None for strict)
        context: Context string for logging
        strict: If True, raise StrictValidationError on failure; if False, return default
        field_name: Field name for error logging (preferred over context for new code)

    Returns:
        Boolean value or None (strict with error) / default (permissive) if conversion fails

    Raises:
        StrictValidationError: If strict=True and conversion fails
    """
    error_ctx = f"for {field_name}" if field_name else context

    if value is None:
        if strict:
            raise StrictValidationError(f"Cannot convert None to bool {error_ctx}")
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        val_lower = value.lower().strip()
        if val_lower in ("true", "1", "yes", "on"):
            return True
        elif val_lower in ("false", "0", "no", "off", ""):
            return False
        else:
            if strict:
                raise StrictValidationError(f"Cannot convert {error_ctx}={value!r} to bool (unrecognized value)")
            logger.warning(f"Cannot convert {error_ctx}={value!r} to bool")
            return default

    if strict:
        raise StrictValidationError(f"Cannot convert {type(value).__name__} {error_ctx}={value!r} to bool")
    logger.warning(f"Cannot convert {type(value).__name__} {error_ctx}={value!r} to bool")
    return default


def safe_json_parse(
    value: Any,
    *,
    default: Any = None,
    strict: bool = False,
    field_name: str | None = None,
) -> Any:
    """Parse JSON string with configurable failure behavior (dashboard API variant).

    Args:
        value: Value to parse (string, dict, list, or None)
        default: Value to return on parse failure (default: None = strict mode)
        strict: If True, raise StrictValidationError instead of returning default
        field_name: Field name for error logging

    Returns:
        Parsed object, or default value
    """
    if value is None:
        if strict:
            raise ValueError(f"Cannot parse None as JSON{f' for {field_name}' if field_name else ''}")
        return default if default is not None else {}

    if isinstance(value, (dict, list)):
        return value

    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            if strict:
                raise ValueError(
                    f"Cannot parse JSON{f' for {field_name}' if field_name else ''}: {e}. Value: {value[:100]}"
                ) from e
            logger.warning(
                f"Failed to parse JSON{f' for {field_name}' if field_name else ''}: {e}. Value: {value[:100]}"
            )
            return default if default is not None else {}

    if strict:
        raise ValueError(
            f"Expected string or dict{f' for {field_name}' if field_name else ''}, got {type(value).__name__}: {value!r}"
        )
    logger.warning(
        f"Expected string or dict{f' for {field_name}' if field_name else ''}, got {type(value).__name__}: {value!r}"
    )
    return default if default is not None else {}


def validate_required_fields(data: dict[str, Any], required_fields: list[str], source: str | None = None) -> bool:
    missing = [f for f in required_fields if f not in data or data[f] is None]
    if missing:
        source_str = f" from {source}" if source else ""
        logger.warning(f"Missing required fields{source_str}: {missing}")
        return False
    return True


def validate_field_types(data: dict[str, Any], type_spec: dict[str, type], source: str | None = None) -> bool:
    issues = []
    for field_name, expected_type in type_spec.items():
        if field_name not in data:
            continue
        value = data[field_name]
        if value is None:
            continue
        if not isinstance(value, expected_type):
            issues.append(f"{field_name}: expected {expected_type.__name__}, got {type(value).__name__}")

    if issues:
        source_str = f" from {source}" if source else ""
        logger.warning(f"Type mismatches{source_str}: {'; '.join(issues)}")
        return False
    return True


def log_data_issue(fetcher_name: str, field_name: str, issue: str, value: Any = None) -> None:
    """Log a data issue from a fetcher function."""
    if value is not None:
        logger.warning(f"{fetcher_name}.{field_name}: {issue} (value: {value!r})")
    else:
        logger.warning(f"{fetcher_name}.{field_name}: {issue}")


# ──────────────────────────────────────────────────────────────────────────────
# UNIFIED DATA UNAVAILABILITY MARKER
# ──────────────────────────────────────────────────────────────────────────────
# Standard format for all "data not available" responses across the platform.
# Prevents inconsistent formats: _data_unavailable vs data_unavailable, with/without reason.


def data_unavailable(
    reason: str,
    message: str | None = None,
    log_level: str = "debug",
    log_context: str | None = None,
) -> dict[str, Any]:
    """Create standardized data unavailability marker.

    REQUIRED: All code returning optional/unavailable data must use this format.
    Ensures dashboard and downstream consumers have consistent schema.

    Args:
        reason: Error code (e.g., "symbol_not_found", "data_loading", "insufficient_history")
        message: Human-readable message (optional, for logging context)
        log_level: Logging level if log_context provided ("debug", "info", "warning", "error")
        log_context: Context string to log (e.g., "fetcher=market_data")

    Returns:
        Dict with standardized shape: {"data_unavailable": True, "reason": "code", "message": "..."}

    Example:
        # Instead of: {"data_unavailable": True}
        # Or:         {"_data_unavailable": True, "reason": "..."}
        # Use:        data_unavailable("data_loading", "Market data not yet available")

        return data_unavailable(
            "insufficient_history",
            message="Need at least 90 trading days",
            log_context="symbol=AAPL"
        )
    """
    result: dict[str, Any] = {"data_unavailable": True, "reason": reason}
    if message:
        result["message"] = message

    if log_context:
        msg = f"[DATA_UNAVAILABLE] {reason}"
        if message:
            msg += f": {message}"
        if log_context:
            msg += f" ({log_context})"

        if log_level == "error":
            logger.error(msg)
        elif log_level == "warning":
            logger.warning(msg)
        elif log_level == "info":
            logger.info(msg)
        else:  # default to debug
            logger.debug(msg)

    return result


def is_data_unavailable(value: Any) -> bool:
    """Check if value is a data_unavailable marker (new standard format or legacy underscore format).

    Returns True for:
    - {"data_unavailable": True, ...}
    - {"_data_unavailable": True, ...} (legacy, for backward compatibility)

    Allows optional consumer code to handle both formats during transition period.
    """
    if not isinstance(value, dict):
        return False
    return bool(value.get("data_unavailable")) or bool(value.get("_data_unavailable"))
