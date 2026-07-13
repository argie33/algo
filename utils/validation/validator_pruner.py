#!/usr/bin/env python3
"""Validator Pruner - Essential validation framework (eliminate speculative generality)."""

from abc import ABC, abstractmethod
from typing import Any


class ValidatorBase(ABC):
    """Base validator for core validation use cases only."""

    @abstractmethod
    def validate(self, value: Any) -> tuple[bool, str]: ...


class FinancialValidator(ValidatorBase):
    def validate(self, value: Any) -> tuple[bool, str]:
        if not isinstance(value, (int, float)):
            return False, "Must be numeric"
        if value < 0:
            return False, "Must be non-negative"
        return True, ""


class SchemaValidator(ValidatorBase):
    def validate(self, value: Any) -> tuple[bool, str]:
        if not isinstance(value, dict):
            return False, "Must be dict"
        return True, ""
