#!/usr/bin/env python3
"""
Data Validation Module
Provides utilities for validating data before calculations and trades.
Prevents crashes from NULL values, empty datasets, and edge cases.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def validate_price_data(price: Optional[float], symbol: str, context: str = "") -> Tuple[bool, Optional[str]]:
    """Validate price data is usable for calculations."""
    if price is None:
        msg = f"Price is NULL for {symbol} in {context}"
        return False, msg
    if price <= 0:
        msg = f"Price is {price} (non-positive) for {symbol} in {context}"
        return False, msg
    if price > 1_000_000:
        msg = f"Price is {price} (suspiciously high) for {symbol} in {context}"
        return False, msg
    return True, None


def validate_volume(volume: Optional[float], symbol: str, context: str = "") -> Tuple[bool, Optional[str]]:
    """Validate volume data."""
    if volume is None:
        msg = f"Volume is NULL for {symbol} in {context}"
        return False, msg
    if volume < 0:
        msg = f"Volume is negative ({volume}) for {symbol} in {context}"
        return False, msg
    if volume == 0:
        msg = f"Volume is 0 for {symbol} in {context} (market closed?)"
        return False, msg
    return True, None


def validate_technical_data(data: Optional[Dict[str, Any]], symbol: str) -> Tuple[bool, Optional[str]]:
    """Validate technical indicator data."""
    if data is None:
        return False, f"Technical data NULL for {symbol}"
    if not isinstance(data, dict):
        return False, f"Technical data not dict for {symbol}: {type(data)}"
    if len(data) == 0:
        return False, f"Technical data empty for {symbol}"
    return True, None


def validate_score(score: Optional[float], field: str, symbol: str) -> Tuple[bool, Optional[str]]:
    """Validate score is in valid range (0-100)."""
    if score is None:
        return False, f"{field} is NULL for {symbol}"
    if not isinstance(score, (int, float)):
        return False, f"{field} not numeric for {symbol}: {type(score)}"
    if score < 0 or score > 100:
        return False, f"{field} out of range [0-100] for {symbol}: {score}"
    return True, None


def validate_ratio(ratio: Optional[float], field: str, symbol: str, min_val: float = -10, max_val: float = 10) -> Tuple[bool, Optional[str]]:
    """Validate ratio data (PE, PB, etc.)."""
    if ratio is None:
        return False, f"{field} is NULL for {symbol}"
    if not isinstance(ratio, (int, float)):
        return False, f"{field} not numeric for {symbol}: {type(ratio)}"
    if ratio < min_val or ratio > max_val:
        return False, f"{field} out of range [{min_val}, {max_val}] for {symbol}: {ratio}"
    return True, None


def validate_dataset(data: Optional[List[Any]], symbol: str, min_size: int = 1) -> Tuple[bool, Optional[str]]:
    """Validate dataset has minimum required size."""
    if data is None:
        return False, f"Dataset is NULL for {symbol}"
    if not isinstance(data, list):
        return False, f"Dataset not list for {symbol}: {type(data)}"
    if len(data) < min_size:
        return False, f"Dataset too small for {symbol}: {len(data)} < {min_size}"
    return True, None


def safe_divide(numerator: Optional[float], denominator: Optional[float], default: float = 0.0, label: str = "") -> float:
    """Safely divide with NULL and zero handling."""
    if numerator is None or denominator is None:
        logger.warning(f"Division with NULL: {label} (num={numerator}, denom={denominator})")
        return default
    if denominator == 0:
        logger.warning(f"Division by zero: {label} (returning {default})")
        return default
    try:
        result = numerator / denominator
        if result > 1e6 or result < -1e6:
            logger.warning(f"Division result suspiciously large: {label} = {result}")
        return result
    except Exception as e:
        logger.error(f"Division failed: {label} - {e}")
        return default


def validate_portfolio_state(positions: Optional[List[Dict]], symbol: str) -> Tuple[bool, Optional[str]]:
    """Validate portfolio position data."""
    if positions is None:
        return False, f"Positions NULL for {symbol}"
    if not isinstance(positions, list):
        return False, f"Positions not list for {symbol}: {type(positions)}"
    for pos in positions:
        if not isinstance(pos, dict):
            return False, f"Position not dict for {symbol}: {type(pos)}"
        for required_field in ['symbol', 'entry_price', 'quantity']:
            if required_field not in pos:
                return False, f"Position missing {required_field} for {symbol}"
            if pos[required_field] is None:
                return False, f"Position {required_field} is NULL for {symbol}"
    return True, None


def validate_date_range(start_date, end_date, symbol: str) -> Tuple[bool, Optional[str]]:
    """Validate date range for queries."""
    if start_date is None or end_date is None:
        return False, f"NULL date for {symbol}"
    if start_date > end_date:
        return False, f"Inverted date range for {symbol}: {start_date} > {end_date}"
    return True, None


class ValidationError(Exception):
    """Raised when data validation fails."""
    pass


class DataValidator:
    """Comprehensive data validation for trading system."""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def add_error(self, msg: str):
        """Record validation error."""
        self.errors.append(msg)
        logger.error(f"VALIDATION ERROR: {msg}")

    def add_warning(self, msg: str):
        """Record validation warning."""
        self.warnings.append(msg)
        logger.warning(f"VALIDATION WARNING: {msg}")

    def is_valid(self) -> bool:
        """True if no errors found."""
        return len(self.errors) == 0

    def get_errors(self) -> List[str]:
        """Return all errors."""
        return self.errors

    def get_warnings(self) -> List[str]:
        """Return all warnings."""
        return self.warnings

    def validate_calculation_inputs(self, symbol: str, data: Dict[str, Any]) -> bool:
        """Validate all inputs required for calculations."""
        # Check required fields
        for field in ['price', 'volume', 'date']:
            if field not in data:
                self.add_error(f"Missing {field} for {symbol}")
            elif data[field] is None:
                self.add_error(f"{field} is NULL for {symbol}")

        # Validate price and volume if present
        if 'price' in data and data['price'] is not None:
            valid, msg = validate_price_data(data['price'], symbol, "calculation input")
            if not valid:
                self.add_error(msg)

        if 'volume' in data and data['volume'] is not None:
            valid, msg = validate_volume(data['volume'], symbol, "calculation input")
            if not valid:
                self.add_warning(msg)

        return self.is_valid()

    def validate_trade_execution(self, symbol: str, position_size: float, entry_price: float,
                                 cash_available: float, max_position_pct: float = 15) -> bool:
        """Validate trade can be executed safely."""
        # Check prices
        valid, msg = validate_price_data(entry_price, symbol, "trade entry")
        if not valid:
            self.add_error(msg)

        # Check position size
        if position_size <= 0:
            self.add_error(f"Position size must be > 0 for {symbol}: {position_size}")
        if position_size > cash_available:
            self.add_error(f"Insufficient cash for {symbol}: need {position_size}, have {cash_available}")
        if position_size > (cash_available * max_position_pct / 100):
            self.add_warning(f"Position {position_size} exceeds max {max_position_pct}% for {symbol}")

        return self.is_valid()
