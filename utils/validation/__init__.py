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

# SQL safety functions (prevent SQL injection)
from utils.db.sql_safety import (
    assert_safe_column,
    assert_safe_table,
    safe_execute,
    safe_select_count,
    validate_identifier,
)

from .alpaca import AlpacaResponseValidator
from .api_response import APIResponseValidator
from .domain import create_default_registry
from .external_services import CognitoValidator, DatabaseResultValidator, DynamoDBValidator
from .framework import (  # Validation classes & exceptions; Functional API - numeric; Functional API - temporal; Functional API - strings & JSON; Functional API - helpers
    EASTERN_TZ,
    EnumValidator,
    PhaseValidator,
    StrictValidationError,
    TypeValidator,
    ValidationResult,
    Validator,
    ValidatorRegistry,
    format_decimal_string,
    get_global_registry,
    log_data_issue,
    safe_bool,
    safe_float,
    safe_int,
    safe_json_loads,
    safe_json_parse,
    safe_parse_date,
    safe_parse_datetime_et,
    safe_str,
    validate_field_types,
    validate_required_fields,
)
from .freshness_config import get_freshness_rule
from .parallelism import ParallelismValidator
from .rate_limit import RateLimitValidator
from .response_validation import get_optional_field, get_required_field
from .schema import validate_table_schema

# Import unified data age validator (consolidates watermark + freshness checking)
try:
    from utils.data.age_validator import DataAgeValidator
except ImportError:
    DataAgeValidator = None  # type: ignore # Graceful fallback if not available

__all__ = [
    "APIResponseValidator",
    "AlpacaResponseValidator",
    "CognitoValidator",
    "DataAgeValidator",
    "DatabaseResultValidator",
    "DynamoDBValidator",
    "EASTERN_TZ",
    "EnumValidator",
    "ParallelismValidator",
    "PhaseValidator",
    "RateLimitValidator",
    "StrictValidationError",
    "TypeValidator",
    "ValidationResult",
    "Validator",
    "ValidatorRegistry",
    "assert_safe_column",
    "assert_safe_table",
    "create_default_registry",
    "format_decimal_string",
    "get_freshness_rule",
    "get_global_registry",
    "get_optional_field",
    "get_required_field",
    "log_data_issue",
    "safe_bool",
    "safe_execute",
    "safe_float",
    "safe_int",
    "safe_json_loads",
    "safe_json_parse",
    "safe_parse_date",
    "safe_parse_datetime_et",
    "safe_select_count",
    "safe_str",
    "validate_field_types",
    "validate_identifier",
    "validate_required_fields",
    "validate_table_schema",
]
