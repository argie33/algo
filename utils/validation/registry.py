#!/usr/bin/env python3
"""
Centralized Data Validation Registry - Single Source of Truth for All Validation

This module provides the official patterns and decision tree for all data validation
in the platform. Use these utilities instead of inline try/except blocks.

PRINCIPLES:
1. One validation utility per data type (safe_float, safe_int, safe_date, etc.)
2. Explicit handling of edge cases (None, NaN, Infinity, empty string)
3. Logging for every validation failure (aids debugging and audit)
4. Context parameter on all utilities (where, why, which record)
5. Two modes: permissive (default value) or strict (None value)

VALIDATION DECISION TREE:
├─ NUMERIC VALUES
│  ├─ float: safe_float() [default=0.0] or safe_float_strict() [default=None]
│  └─ int: safe_int() [default=0] or safe_int_strict() [default=None]
├─ DATES/TIMES
│  ├─ date: safe_parse_date()
│  └─ datetime: safe_parse_datetime_et()
├─ STRINGS
│  ├─ JSON: safe_json_loads()
│  ├─ URL: use utils.url_validator for URL validation
│  └─ CSV: use utils.csv_sanitizer for CSV data
├─ STRUCTURAL
│  ├─ Schema validation: use utils.schema_validator.validate_row()
│  └─ Alpaca responses: use utils.alpaca_response_validator
└─ COMPLEX OBJECTS
   └─ Use type hints + pydantic if strict validation needed

MIGRATION GUIDE:
If you have inline try/except for numeric parsing, replace with:

    # OLD (inline try/except - WRONG):
    try:
        price = float(row['price'])
    except ValueError:
        price = 0.0

    # NEW (centralized - RIGHT):
    from utils.infrastructure import safe_float
    price = safe_float(row['price'], default=0.0, context=f"symbol={symbol}")

DO NOT:
- Catch and silently ignore validation errors (always log with context)
- Use hardcoded defaults without documenting why (0.0 vs None vs sentinel value)
- Mix validation in business logic (separate concerns: validate first, then use)
- Validate optional fields as required (None should be valid for optional fields)
"""

import logging
from typing import Any, Callable, Dict, Optional

from utils.infrastructure import (
    safe_float,
    safe_float_strict,
    safe_int,
    safe_int_strict,
    safe_json_loads,
    safe_parse_date,
    safe_parse_datetime_et,
)


logger = logging.getLogger(__name__)

# Type aliases for clarity
ValidatorFunc = Callable[[Any, str], Optional[Any]]

# Global validation registry - documents all validators in one place
VALIDATORS_BY_TYPE: dict[str, Callable[[Any, str], Any | None]] = {
    "float": safe_float,
    "float_strict": safe_float_strict,
    "int": safe_int,
    "int_strict": safe_int_strict,
    "date": safe_parse_date,
    "datetime_et": safe_parse_datetime_et,
    "json": safe_json_loads,
}


def get_validator(field_type: str) -> Optional[ValidatorFunc]:
    """Get validator function by type name.

    Usage:
        validator = get_validator('float')
        price = validator(row['price'], context="AAPL price")
    """
    return VALIDATORS_BY_TYPE.get(field_type)


def validate_record(
    record: Dict[str, Any], schema: Dict[str, str], context: str = ""
) -> Dict[str, Any]:
    """Validate entire record against schema using centralized validators.

    Args:
        record: Dictionary of field_name -> value
        schema: Dictionary of field_name -> validator_type (e.g. {'price': 'float', 'date': 'date'})
        context: Context string for logging (e.g., "AAPL on 2026-06-12")

    Returns:
        Validated record with safe defaults for invalid fields

    Example:
        schema = {'price': 'float', 'volume': 'int', 'date': 'date'}
        validated = validate_record(row, schema, context=f"{symbol} historical data")
    """
    validated: dict[str, Any] = {}
    for field_name, field_type in schema.items():
        if field_name not in record:
            logger.warning(f"Missing field {field_name} in record {context}")
            validated[field_name] = None
            continue

        value = record[field_name]
        validator = get_validator(field_type)
        if not validator:
            logger.warning(f"No validator for type '{field_type}' (field {field_name})")
            validated[field_name] = value
            continue

        field_context = f"{context}, field={field_name}"
        validated[field_name] = validator(value, context=field_context)  # type: ignore[call-arg]

    return validated


if __name__ == "__main__":
    # Example: validate price data
    print("Data Validation Registry - Centralized validator patterns")
    print("\nRegistered validators:")
    for type_name in VALIDATORS_BY_TYPE:
        print(f"  - {type_name}")
