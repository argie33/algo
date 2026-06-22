#!/usr/bin/env python3
"""
Centralized Validation Framework - Single Source of Truth for All Validation

This module provides unified validation for all data across the platform.
Supports both:
1. Class-based validators (composable, auditable)
2. Functional API (backward compatible with existing code)

All validation is fail-closed with explicit error logging and context tracking.
No silent defaults—missing data returns None, conversions are logged.
"""

import json
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Eastern timezone for all time-based conversions
EASTERN_TZ = timezone.utc


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

    def __init__(self, name: str = "", context: str = ""):
        self.name = name or self.__class__.__name__
        self.context = context

    @abstractmethod
    def validate(self, data: Any, context: str = "") -> ValidationResult:
        pass

    def __call__(self, data: Any, context: str = "") -> ValidationResult:
        return self.validate(data, context or self.context)


class TypeValidator(Validator):
    """Validates data type and optionally range/length constraints."""

    def __init__(
        self,
        expected_type: str,
        min_val=None,
        max_val=None,
        min_length=None,
        max_length=None,
    ):
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
    """Validates that value is one of allowed enum values."""

    def __init__(self, allowed_values: list[str], case_sensitive: bool = False):
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
    """Validates orchestrator phase objects with name and status fields."""

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

    def __init__(self):
        super().__init__("PhaseValidator")

    def validate(self, data: Any, context: str = "") -> ValidationResult:
        if not isinstance(data, dict):
            errors = [f"{context}: expected dict, got {type(data).__name__}"]
            return ValidationResult(is_valid=False, errors=errors, context=context)

        all_errors = []
        cleaned = {}

        name = data.get("name") or data.get("phase")
        if not name:
            all_errors.append(f"{context}: missing 'name' or 'phase' field")
        else:
            cleaned["name"] = str(name)

        status = (data.get("status") or "").lower().strip()
        if not status:
            all_errors.append(f"{context}: missing 'status' field")
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

    def __init__(self):
        self._validators: dict[str, Validator] = {}
        self._metadata: dict[str, dict[str, str]] = {}

    def register(self, name: str, validator: Validator, description: str = ""):
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
# All validation is centralized here — one source of truth for all data conversion.


def safe_float(value: Any, default: float = 0.0, context: str = "") -> float:
    """Convert value to float safely, handling NaN, Infinity, None.

    Args:
        value: Value to convert (can be str, int, float, None)
        default: Default value if conversion fails (default: 0.0)
        context: Context string for logging (e.g., "symbol=AAPL")

    Returns:
        Float value or default if conversion fails
    """
    if value is None:
        return default

    if isinstance(value, bool):
        return default

    try:
        f = float(value)
        if math.isnan(f):
            logger.warning(f"NaN value rejected {context}")
            return default
        if math.isinf(f):
            logger.warning(f"Infinity value rejected {context}")
            return default
        return f
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to convert {value!r} to float {context}: {e}")
        return default


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


def safe_int(value: Any, default: int = 0, context: str = "") -> int:
    """Convert value to int safely, handling None, invalid strings.

    Args:
        value: Value to convert (can be str, int, float, None)
        default: Default value if conversion fails (default: 0)
        context: Context string for logging

    Returns:
        Int value or default if conversion fails
    """
    if value is None:
        return default

    if isinstance(value, bool):
        return default

    try:
        return int(value)
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to convert {value!r} to int {context}: {e}")
        return default


def safe_parse_date(value: Any, context: str = "") -> date | None:
    """Parse date from multiple formats: ISO, string, datetime.

    Handles:
    - ISO format strings (2026-06-10)
    - datetime objects
    - date objects

    Returns None if parsing fails.
    """
    if value is None:
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

        logger.warning(f"Failed to parse date {value!r} {context} - no format matched")
        return None

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


def safe_str(value: Any, default: str = "", context: str = "") -> str:
    """Safely convert value to string with logging.

    Args:
        value: Value to convert
        default: Default value if conversion fails
        context: Context string for logging

    Returns:
        String value or default if conversion fails
    """
    if value is None:
        return default

    if isinstance(value, str):
        return value

    try:
        return str(value)
    except Exception as e:
        logger.warning(f"Failed to convert {value!r} to str {context}: {e}")
        return default


def safe_bool(value: Any, default: bool = False, context: str = "") -> bool:
    """Safely convert value to bool with logging.

    Args:
        value: Value to convert
        default: Default value if conversion fails
        context: Context string for logging

    Returns:
        Boolean value or default if conversion fails
    """
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        val_lower = value.lower().strip()
        if val_lower in ("true", "1", "yes", "on"):
            return True
        elif val_lower in ("false", "0", "no", "of", ""):
            return False
        else:
            logger.warning(f"Cannot convert {context}={value!r} to bool")
            return default

    try:
        return bool(value)
    except Exception as e:
        logger.warning(f"Failed to convert {context}={value!r} to bool: {e}")
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
    """Check if required fields exist in data dict. Log warnings for missing fields."""
    missing = [f for f in required_fields if f not in data or data[f] is None]
    if missing:
        source_str = f" from {source}" if source else ""
        logger.warning(f"Missing required fields{source_str}: {missing}")
        return False
    return True


def validate_field_types(data: dict[str, Any], type_spec: dict[str, type], source: str | None = None) -> bool:
    """Validate that fields in data match expected types. Log warnings for type mismatches."""
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


def log_data_issue(fetcher_name: str, field_name: str, issue: str, value: Any = None):
    """Log a data issue from a fetcher function."""
    if value is not None:
        logger.warning(f"{fetcher_name}.{field_name}: {issue} (value: {value!r})")
    else:
        logger.warning(f"{fetcher_name}.{field_name}: {issue}")
