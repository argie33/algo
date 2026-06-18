#!/usr/bin/env python3
"""
Unified Data Validation System - Single Source of Truth for All Validation

This module consolidates all validation across the platform:
- Functional API (safe_float, safe_int, safe_str, etc.) for backward compatibility
- Class-based validators (Validator, ValidationResult) for composable validation
- Specialized validators (AlpacaResponseValidator, APIResponseValidator)
- Registry system for centralized validator management

PRINCIPLE: All data validation must go through this module. Never use
inline try/except or silent defaults elsewhere in the codebase.
"""

from .alpaca import AlpacaResponseValidator
from .api_response import APIResponseValidator
from .domain import create_default_registry
from .framework import (
    EASTERN_TZ,
    EnumValidator,
    PhaseValidator,
    StrictValidationError,
    TypeValidator,
    # Validation classes & exceptions
    ValidationResult,
    Validator,
    ValidatorRegistry,
    get_global_registry,
    log_data_issue,
    safe_bool,
    # Functional API - numeric
    safe_float,
    safe_float_strict,
    safe_int,
    safe_int_strict,
    safe_json_loads,
    safe_json_parse,
    # Functional API - temporal
    safe_parse_date,
    safe_parse_datetime_et,
    # Functional API - strings & JSON
    safe_str,
    validate_field_types,
    # Functional API - helpers
    validate_required_fields,
)
from .freshness_config import get_freshness_rule
from .parallelism import ParallelismValidator
from .rate_limit import RateLimitValidator
from .schema import validate_table_schema


# Import unified data age validator (consolidates watermark + freshness checking)
try:
    from utils.data.age_validator import DataAgeValidator
except ImportError:
    DataAgeValidator = None  # type: ignore # Graceful fallback if not available

__all__ = [
    # Core validation classes & exceptions
    "ValidationResult",
    "Validator",
    "TypeValidator",
    "EnumValidator",
    "PhaseValidator",
    "ValidatorRegistry",
    "get_global_registry",
    "StrictValidationError",
    # Registry factories
    "create_default_registry",
    # Numeric conversions
    "safe_float",
    "safe_float_strict",
    "safe_int",
    "safe_int_strict",
    # Temporal conversions
    "safe_parse_date",
    "safe_parse_datetime_et",
    # String & JSON conversions
    "safe_str",
    "safe_bool",
    "safe_json_loads",
    "safe_json_parse",
    # Helper functions
    "validate_required_fields",
    "validate_field_types",
    "log_data_issue",
    # Constants
    "EASTERN_TZ",
    # Specialized validators
    "get_freshness_rule",
    "AlpacaResponseValidator",
    "APIResponseValidator",
    "validate_table_schema",
    "RateLimitValidator",
    "ParallelismValidator",
    # Data freshness (unified)
    "DataAgeValidator",
]
