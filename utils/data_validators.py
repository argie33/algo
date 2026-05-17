"""
Data quality validators for all loaders.
Prevents corrupted data from entering the database.
"""

import logging
import math
import re
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, date

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Data validation failed."""
    pass


class PriceValidator:
    """Validate OHLCV price data."""

    @staticmethod
    def validate_row(row: Dict[str, Any], symbol_col: str = 'symbol',
                    date_col: str = 'date') -> Tuple[bool, Optional[str]]:
        """
        Validate a single price row.

        Returns: (is_valid, error_message)
        """
        try:
            # Required fields
            required = {symbol_col, date_col, 'open', 'high', 'low', 'close', 'volume'}
            missing = required - set(row.keys())
            if missing:
                return False, f"Missing required fields: {missing}"

            symbol = row.get(symbol_col)
            date_val = row.get(date_col)
            open_price = float(row.get('open', 0))
            high = float(row.get('high', 0))
            low = float(row.get('low', 0))
            close = float(row.get('close', 0))
            volume = int(row.get('volume', 0))

            # Symbol validation
            if not symbol or not isinstance(symbol, str):
                return False, f"Invalid symbol: {symbol}"
            if not re.match(r'^[A-Z0-9.\-]{1,20}$', symbol):
                return False, f"Invalid symbol format: {symbol}"

            # Date validation
            if isinstance(date_val, str):
                try:
                    date.fromisoformat(date_val)
                except ValueError:
                    return False, f"Invalid date format: {date_val}"
            elif not isinstance(date_val, (date, datetime)):
                return False, f"Invalid date type: {type(date_val)}"

            # Price validation
            if any(math.isnan(p) or math.isinf(p) for p in [open_price, high, low, close]):
                return False, "Price contains NaN or Infinity"

            if any(p < 0 for p in [open_price, high, low, close]):
                return False, f"Negative prices not allowed: O={open_price}, H={high}, L={low}, C={close}"

            if high < low:
                return False, f"High {high} < Low {low}"

            if high < open_price:
                return False, f"High {high} < Open {open_price}"

            if high < close:
                return False, f"High {high} < Close {close}"

            if low > open_price:
                return False, f"Low {low} > Open {open_price}"

            if low > close:
                return False, f"Low {low} > Close {close}"

            # Volume validation
            if volume < 0:
                return False, f"Negative volume: {volume}"

            if volume == 0 and high > low:  # Market moved but no volume
                logger.warning(f"{symbol} {date_val}: Price moved with zero volume")

            # Extreme moves check (warn, don't fail)
            prev_close = row.get('prev_close')
            if prev_close:
                try:
                    prev_close = float(prev_close)
                    pct_change = abs(close - prev_close) / prev_close * 100
                    if pct_change > 50:
                        logger.warning(f"{symbol} {date_val}: Extreme move {pct_change:.1f}%")
                except (ValueError, ZeroDivisionError):
                    pass

            return True, None

        except Exception as e:
            return False, f"Validation error: {str(e)}"

    @staticmethod
    def validate_batch(rows: List[Dict[str, Any]], symbol_col: str = 'symbol',
                      date_col: str = 'date', fail_on_first: bool = False) -> Tuple[int, List[str]]:
        """
        Validate batch of rows.

        Returns: (valid_count, error_messages)
        """
        valid_count = 0
        errors = []

        for i, row in enumerate(rows):
            is_valid, error = PriceValidator.validate_row(row, symbol_col, date_col)
            if is_valid:
                valid_count += 1
            else:
                error_msg = f"Row {i}: {error}"
                errors.append(error_msg)
                if fail_on_first:
                    break

        return valid_count, errors


class SymbolValidator:
    """Validate stock symbol format."""

    @staticmethod
    def validate(symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Validate symbol format.

        Returns: (is_valid, error_message)
        """
        if not symbol or not isinstance(symbol, str):
            return False, f"Invalid symbol: {symbol}"

        symbol_upper = symbol.upper()

        # Format: A-Z, numbers, dots, hyphens only
        if not re.match(r'^[A-Z0-9.\-]{1,20}$', symbol_upper):
            return False, f"Invalid symbol format: {symbol} (must be alphanumeric with . or -)"

        # No reserved SQL keywords
        reserved = {'SELECT', 'FROM', 'WHERE', 'INSERT', 'UPDATE', 'DELETE', 'DROP'}
        if symbol_upper in reserved:
            return False, f"Reserved keyword not allowed: {symbol}"

        return True, None


class ScoreValidator:
    """Validate score data (0-100 range)."""

    @staticmethod
    def validate_score(value: Any, allow_none: bool = True) -> Tuple[bool, Optional[str]]:
        """
        Validate single score value.

        Returns: (is_valid, error_message)
        """
        if value is None:
            return (True, None) if allow_none else (False, "Score cannot be None")

        try:
            score = float(value)

            if math.isnan(score) or math.isinf(score):
                return False, "Score is NaN or Infinity"

            if not (0 <= score <= 100):
                return False, f"Score {score} not in range [0, 100]"

            return True, None

        except (ValueError, TypeError) as e:
            return False, f"Invalid score value: {value} ({str(e)})"

    @staticmethod
    def validate_row(row: Dict[str, Any], score_fields: List[str]) -> Tuple[bool, Optional[str]]:
        """
        Validate score row (all fields must be 0-100 or None).

        Returns: (is_valid, error_message)
        """
        for field in score_fields:
            if field not in row:
                continue

            is_valid, error = ScoreValidator.validate_score(row[field], allow_none=True)
            if not is_valid:
                return False, f"{field}: {error}"

        return True, None


class DateValidator:
    """Validate date values."""

    @staticmethod
    def validate(date_val: Any, format_str: str = '%Y-%m-%d') -> Tuple[bool, Optional[str]]:
        """
        Validate date format.

        Returns: (is_valid, error_message)
        """
        if isinstance(date_val, (date, datetime)):
            return True, None

        if isinstance(date_val, str):
            try:
                datetime.strptime(date_val, format_str)
                return True, None
            except ValueError:
                return False, f"Invalid date format: {date_val} (expected {format_str})"

        return False, f"Invalid date type: {type(date_val)}"

    @staticmethod
    def is_trading_day(date_val: Any) -> bool:
        """Check if date is a weekday (potential trading day)."""
        if isinstance(date_val, str):
            try:
                date_val = datetime.strptime(date_val, '%Y-%m-%d').date()
            except ValueError:
                return False
        elif isinstance(date_val, datetime):
            date_val = date_val.date()

        # Weekday 0-4 = Monday-Friday, 5-6 = Sat-Sun
        return date_val.weekday() < 5


class DataQualityReport:
    """Track validation results."""

    def __init__(self):
        self.total_rows = 0
        self.valid_rows = 0
        self.invalid_rows = 0
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def add_error(self, error: str):
        self.errors.append(error)
        self.invalid_rows += 1

    def add_warning(self, warning: str):
        self.warnings.append(warning)

    def record_row(self, valid: bool):
        self.total_rows += 1
        if valid:
            self.valid_rows += 1
        else:
            self.invalid_rows += 1

    def is_acceptable(self, min_valid_pct: float = 95.0) -> bool:
        """Check if validation meets threshold."""
        if self.total_rows == 0:
            return False
        pct_valid = (self.valid_rows / self.total_rows) * 100
        return pct_valid >= min_valid_pct

    def summary(self) -> Dict[str, Any]:
        """Get summary report."""
        pct_valid = (self.valid_rows / max(self.total_rows, 1)) * 100
        return {
            'total': self.total_rows,
            'valid': self.valid_rows,
            'invalid': self.invalid_rows,
            'valid_pct': round(pct_valid, 2),
            'errors': len(self.errors),
            'warnings': len(self.warnings),
            'is_acceptable': self.is_acceptable()
        }

    def log(self, logger_obj):
        """Log report."""
        summary = self.summary()
        logger_obj.info(f"Data Quality: {summary['valid']}/{summary['total']} rows valid ({summary['valid_pct']:.1f}%)")
        if self.errors:
            logger_obj.error(f"Validation errors: {len(self.errors)}")
            for err in self.errors[:5]:  # Log first 5
                logger_obj.error(f"  - {err}")
        if self.warnings:
            logger_obj.warning(f"Validation warnings: {len(self.warnings)}")
