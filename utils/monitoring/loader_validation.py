#!/usr/bin/env python3
"""
Loader Data Validation Framework

Provides reusable validation functions for all loaders to ensure data quality
before INSERT into database. Prevents NaN, Inf, invalid types, and duplicates.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


import logging
import math
import re
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)


def is_valid_float(value: Any, allow_none: bool = False, min_val: Optional[float] = None, max_val: Optional[float] = None) -> bool:
    """Validate a float value: not NaN, not Inf, within bounds."""
    if value is None:
        return allow_none

    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return False
        if min_val is not None and f < min_val:
            return False
        if max_val is not None and f > max_val:
            return False
        return True
    except (TypeError, ValueError):
        return False


def is_valid_int(value: Any, allow_none: bool = False, min_val: Optional[int] = None, max_val: Optional[int] = None) -> bool:
    """Validate an integer value: valid int, within bounds."""
    if value is None:
        return allow_none

    try:
        i = int(value)
        if min_val is not None and i < min_val:
            return False
        if max_val is not None and i > max_val:
            return False
        return True
    except (TypeError, ValueError):
        return False


def is_valid_symbol(symbol: str) -> bool:
    """Validate stock symbol format: 1-20 chars, uppercase alphanumeric with dash/dot."""
    if not symbol or not isinstance(symbol, str):
        return False
    return bool(re.match(r'^[A-Z0-9.\-]{1,20}$', str(symbol).upper()))


def is_valid_date(value: Any, date_format: str = '%Y-%m-%d') -> bool:
    """Validate date string format."""
    if not value or not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, date_format)
        return True
    except ValueError:
        return False


def validate_price_row(row: Dict[str, Any], allow_missing_fields: bool = False) -> Tuple[bool, str]:
    """
    Validate OHLCV price row: all prices must be positive, high >= low, volume >= 0.

    Returns: (is_valid, error_message)
    """
    required_fields = ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']

    if not allow_missing_fields:
        for field in required_fields:
            if field not in row or row[field] is None:
                return False, f"Missing required field: {field}"

    if not is_valid_symbol(row.get('symbol')):
        return False, f"Invalid symbol: {row.get('symbol')}"

    if not is_valid_date(row.get('date')):
        return False, f"Invalid date: {row.get('date')}"

    for price_field in ['open', 'high', 'low', 'close']:
        if price_field not in row or row[price_field] is None:
            return False, f"Missing {price_field} price"
        if not is_valid_float(row[price_field], min_val=0.01):
            return False, f"Invalid {price_field} price: {row[price_field]}"

    o, h, l, c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])

    if h < l:
        return False, f"High {h} < Low {l}"
    if h < o or h < c:
        return False, f"High {h} must be >= Open {o} and Close {c}"
    if l > o or l > c:
        return False, f"Low {l} must be <= Open {o} and Close {c}"

    if 'volume' in row and row['volume'] is not None:
        if not is_valid_int(row['volume'], min_val=0):
            return False, f"Invalid volume: {row['volume']}"

    return True, ""


def validate_technical_row(row: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate technical indicator row: all numeric fields must be valid floats or None.

    Returns: (is_valid, error_message)
    """
    required_fields = ['symbol', 'date']

    for field in required_fields:
        if field not in row or row[field] is None:
            return False, f"Missing required field: {field}"

    if not is_valid_symbol(row.get('symbol')):
        return False, f"Invalid symbol: {row.get('symbol')}"
    if not is_valid_date(row.get('date')):
        return False, f"Invalid date: {row.get('date')}"

    # Technical indicator fields that should be 0-100 if present
    indicator_0_100 = ['rsi', 'macd', 'bb_upper', 'bb_middle', 'bb_lower', 'atr']

    for field in indicator_0_100:
        if field in row and row[field] is not None:
            if not is_valid_float(row[field], min_val=-500, max_val=500):  # RSI 0-100 typically, MACD can be negative
                return False, f"Invalid {field}: {row[field]}"

    # SMA/EMA fields should be positive if present
    for field in ['sma_50', 'sma_200', 'ema_12', 'ema_26']:
        if field in row and row[field] is not None:
            if not is_valid_float(row[field], min_val=0.01):
                return False, f"Invalid {field}: {row[field]}"

    return True, ""


def validate_score_row(row: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate stock score row: all scores should be 0-100 if present.

    Returns: (is_valid, error_message)
    """
    required_fields = ['symbol']

    for field in required_fields:
        if field not in row or row[field] is None:
            return False, f"Missing required field: {field}"

    if not is_valid_symbol(row.get('symbol')):
        return False, f"Invalid symbol: {row.get('symbol')}"

    # Score fields should be 0-100 if present
    score_fields = ['momentum_score', 'quality_score', 'value_score', 'growth_score',
                    'stability_score', 'positioning_score', 'composite_score']

    for field in score_fields:
        if field in row and row[field] is not None:
            if not is_valid_float(row[field], min_val=0, max_val=100):
                return False, f"Invalid {field}: {row[field]} (must be 0-100)"

    return True, ""


def validate_fundamental_row(row: Dict[str, Any], fields_to_check: List[str]) -> Tuple[bool, str]:
    """
    Generic validation for fundamental/financial data rows.

    Args:
        row: Data row to validate
        fields_to_check: List of field names that should be valid floats (or None)

    Returns: (is_valid, error_message)
    """
    required_fields = ['ticker', 'symbol']

    symbol = row.get('symbol') or row.get('ticker')
    if not symbol or not is_valid_symbol(symbol):
        return False, f"Invalid symbol/ticker: {symbol}"

    for field in fields_to_check:
        if field in row and row[field] is not None:
            if not is_valid_float(row[field]):
                return False, f"Invalid {field}: {row[field]}"

    return True, ""


def log_validation_error(loader_name: str, row_num: int, symbol: str, error: str) -> None:
    """Log a validation error with context."""
    logger.error(f"{loader_name} row {row_num} ({symbol}): {error}")


def count_validation_errors(rows: List[Dict], validator_func, logger_name: str = "loader") -> Tuple[List[Dict], int]:
    """
    Filter rows through a validator function, logging errors.

    Args:
        rows: List of data rows
        validator_func: Function that takes row and returns (is_valid, error_message)
        logger_name: Name for logging

    Returns: (valid_rows, error_count)
    """
    valid_rows = []
    error_count = 0

    for i, row in enumerate(rows, 1):
        is_valid, error = validator_func(row)
        if is_valid:
            valid_rows.append(row)
        else:
            error_count += 1
            symbol = row.get('symbol') or row.get('ticker', 'UNKNOWN')
            log_validation_error(logger_name, i, symbol, error)

    if error_count > 0:
        logger.warning(f"{logger_name}: Filtered out {error_count}/{len(rows)} invalid rows ({100*error_count/len(rows):.1f}%)")

    return valid_rows, error_count


def detect_duplicates(rows: List[Dict], key_fields: List[str]) -> Tuple[List[Dict], int]:
    """
    Detect and remove duplicate rows based on key fields.

    Returns: (deduplicated_rows, duplicate_count)
    """
    seen = set()
    deduplicated = []
    duplicate_count = 0

    for row in rows:
        key = tuple(row.get(field) for field in key_fields)
        if key in seen:
            duplicate_count += 1
            symbol = row.get('symbol') or row.get('ticker', 'UNKNOWN')
            logger.warning(f"Duplicate row detected for {symbol}: {key}")
        else:
            seen.add(key)
            deduplicated.append(row)

    if duplicate_count > 0:
        logger.warning(f"Removed {duplicate_count} duplicate rows")

    return deduplicated, duplicate_count
