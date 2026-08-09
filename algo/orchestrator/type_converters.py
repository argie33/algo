#!/usr/bin/env python3
"""Shared type conversion helpers for orchestrator phase executors.

Centralized conversion logic for psycopg2/database types (Decimal, numpy.int64)
to native Python types (int, float). Prevents duplication across phase files.
"""

from decimal import Decimal
from typing import Any


def ensure_int(val: Any, field_name: str = "value") -> int:
    """Convert any integer value to native Python int with diagnostic logging."""
    if val is None:
        raise ValueError(f"Cannot convert None {field_name} to int")
    try:
        if isinstance(val, Decimal):
            result = int(str(val))
        elif isinstance(val, int) and not isinstance(val, bool):
            result = val
        else:
            result = int(val)
        native_int = int(result)
        if not isinstance(native_int, int) or isinstance(native_int, bool):
            raise TypeError(f"{field_name}: int() returned {type(native_int).__name__}, cannot force to native int")
        return native_int
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field_name}: Cannot convert {type(val).__name__} to native Python int: {e}") from e


def ensure_float(val: Any, field_name: str = "value") -> float:
    """Convert any numeric value to native Python float, handling psycopg2 Decimal types."""
    if val is None:
        raise ValueError(f"Cannot convert None {field_name} to float")
    try:
        result = float(str(val))
        native_float = float(result)
        if not isinstance(native_float, float) or isinstance(native_float, bool):
            raise TypeError(f"{field_name}: conversion returned {type(native_float).__name__}, not native float")
        return native_float
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field_name}: Cannot convert {type(val).__name__} to native Python float: {e}") from e
