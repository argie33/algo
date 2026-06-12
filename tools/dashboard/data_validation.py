"""Data validation and safe conversion utilities for dashboard."""

import json
import logging
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

logger = logging.getLogger(__name__)

T = TypeVar('T')


def safe_float(value: Any, default: Union[float, None] = 0.0, field_name: str = None) -> Union[float, None]:
    """Safely convert value to float with logging. Returns default (0.0 or None) if conversion fails."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as e:
        if field_name:
            logger.warning(f"Failed to convert {field_name}={value!r} to float: {e}")
        else:
            logger.warning(f"Failed to convert {value!r} to float: {e}")
        return default


def safe_int(value: Any, default: int = 0, field_name: str = None) -> int:
    """Safely convert value to int with logging."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        if field_name:
            logger.warning(f"Failed to convert {field_name}={value!r} to int: {e}")
        else:
            logger.warning(f"Failed to convert {value!r} to int: {e}")
        return default


def safe_json_parse(value: Any, default: Any = None, field_name: str = None) -> Any:
    """Safely parse JSON string with logging."""
    if value is None:
        return default if default is not None else {}

    # If it's already parsed, return as-is
    if isinstance(value, (dict, list)):
        return value

    # If it's a string, try to parse
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            if field_name:
                logger.warning(f"Failed to parse JSON in {field_name}: {e}. Value: {value[:100]}")
            else:
                logger.warning(f"Failed to parse JSON: {e}. Value: {value[:100]}")
            return default if default is not None else {}

    # For unexpected types, log and return default
    if field_name:
        logger.warning(f"Expected string or dict for {field_name}, got {type(value).__name__}: {value!r}")
    else:
        logger.warning(f"Expected string or dict, got {type(value).__name__}: {value!r}")
    return default if default is not None else {}


def safe_bool(value: Any, default: bool = False, field_name: str = None) -> bool:
    """Safely convert value to bool with logging."""
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        val_lower = value.lower().strip()
        if val_lower in ('true', '1', 'yes', 'on'):
            return True
        elif val_lower in ('false', '0', 'no', 'off', ''):
            return False
        else:
            if field_name:
                logger.warning(f"Cannot convert {field_name}={value!r} to bool")
            else:
                logger.warning(f"Cannot convert {value!r} to bool")
            return default

    try:
        return bool(value)
    except Exception as e:
        if field_name:
            logger.warning(f"Failed to convert {field_name}={value!r} to bool: {e}")
        else:
            logger.warning(f"Failed to convert {value!r} to bool: {e}")
        return default


def safe_str(value: Any, default: str = "", field_name: str = None) -> str:
    """Safely convert value to string with logging."""
    if value is None:
        return default

    if isinstance(value, str):
        return value

    try:
        return str(value)
    except Exception as e:
        if field_name:
            logger.warning(f"Failed to convert {field_name}={value!r} to str: {e}")
        else:
            logger.warning(f"Failed to convert {value!r} to str: {e}")
        return default


def validate_required_fields(data: Dict[str, Any], required_fields: List[str],
                             source: str = None) -> bool:
    """Check if required fields exist in data dict. Log warnings for missing fields."""
    missing = [f for f in required_fields if f not in data or data[f] is None]
    if missing:
        source_str = f" from {source}" if source else ""
        logger.warning(f"Missing required fields{source_str}: {missing}")
        return False
    return True


def validate_field_types(data: Dict[str, Any], type_spec: Dict[str, Type],
                         source: str = None) -> bool:
    """Validate that fields in data match expected types. Log warnings for type mismatches."""
    issues = []
    for field, expected_type in type_spec.items():
        if field not in data:
            continue
        value = data[field]
        if value is None:
            continue
        if not isinstance(value, expected_type):
            issues.append(f"{field}: expected {expected_type.__name__}, got {type(value).__name__}")

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
