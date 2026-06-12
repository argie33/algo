#!/usr/bin/env python3
"""
Centralized Validation Framework - Single Source of Truth for All Validation

This module provides a unified interface and patterns for all data validation
across the platform. It replaces scattered validate_*() functions with a
composable, auditable validation system.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Structured validation result with error details and cleaned data."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    data: Optional[Any] = None
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

    def __init__(self, expected_type: str, min_val=None, max_val=None, min_length=None, max_length=None):
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
            cleaned, err = self._validate_float(data, context)
            if err:
                errors.append(err)
        elif self.expected_type in ("int", "integer"):
            cleaned, err = self._validate_int(data, context)
            if err:
                errors.append(err)
        elif self.expected_type in ("str", "text", "string", "varchar"):
            if not isinstance(data, str):
                errors.append(f"{context}: expected string, got {type(data).__name__}")
            else:
                cleaned = data
        else:
            errors.append(f"Unknown type: {self.expected_type}")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, data=cleaned, context=context, validator_name=self.name)

    def _validate_float(self, data: Any, context: str) -> tuple:
        try:
            val = float(data)
            if self.min_val is not None and val < self.min_val:
                return None, f"{context}: {val} < min {self.min_val}"
            if self.max_val is not None and val > self.max_val:
                return None, f"{context}: {val} > max {self.max_val}"
            return val, None
        except (ValueError, TypeError):
            return None, f"{context}: cannot convert {data!r} to float"

    def _validate_int(self, data: Any, context: str) -> tuple:
        try:
            val = int(data)
            if self.min_val is not None and val < self.min_val:
                return None, f"{context}: {val} < min {self.min_val}"
            if self.max_val is not None and val > self.max_val:
                return None, f"{context}: {val} > max {self.max_val}"
            return val, None
        except (ValueError, TypeError):
            return None, f"{context}: cannot convert {data!r} to int"


class EnumValidator(Validator):
    """Validates that value is one of allowed enum values."""

    def __init__(self, allowed_values: List[str], case_sensitive: bool = False):
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

    VALID_STATUSES = {"ok", "success", "running", "pending", "halt", "halted", "failed", "completed", "skipped"}

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

        return ValidationResult(is_valid=len(all_errors) == 0, errors=all_errors, data=cleaned if len(all_errors) == 0 else None, context=context, validator_name=self.name)


class ValidatorRegistry:
    """Central registry of all validators."""

    def __init__(self):
        self._validators: Dict[str, Validator] = {}
        self._metadata: Dict[str, Dict[str, str]] = {}

    def register(self, name: str, validator: Validator, description: str = ""):
        self._validators[name] = validator
        self._metadata[name] = {"validator_class": validator.__class__.__name__, "description": description}
        logger.debug(f"Registered validator: {name}")

    def validate(self, validator_name: str, data: Any, context: str = "") -> ValidationResult:
        if validator_name not in self._validators:
            raise ValueError(f"Unknown validator: {validator_name!r}")
        validator = self._validators[validator_name]
        return validator.validate(data, context=context)

    def get_validator(self, name: str) -> Optional[Validator]:
        return self._validators.get(name)


_global_registry = ValidatorRegistry()


def get_global_registry() -> ValidatorRegistry:
    return _global_registry
