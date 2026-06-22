"""
Security Validators for API Input Sanitization

Provides safe wrappers for common validation patterns:
- Stock symbols
- Numeric values with bounds checking
- Dates and time ranges
- Risk parameters
"""

import logging
import re
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# Validation patterns
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9\.\-]{1,12}$")  # Stock symbols: AAPL, BRK.B
NASDAQ_PATTERN = re.compile(r"^[A-Z]{1,5}$|^[A-Z\d]{3}\.[A-Z]$")  # More strict NASDAQ format


class ValidationError(ValueError):
    """Raised when validation fails"""


def validate_symbol(symbol: str, strict: bool = False) -> str:
    """
    Validate stock symbol format.

    Args:
        symbol: Ticker symbol (e.g., 'AAPL', 'BRK.B')
        strict: If True, use stricter NASDAQ rules

    Returns:
        Validated symbol in uppercase

    Raises:
        ValidationError: If symbol is invalid
    """
    if not symbol:
        raise ValidationError("Symbol cannot be empty")

    symbol = symbol.upper().strip()

    if len(symbol) > 12:
        raise ValidationError(f"Symbol too long: {len(symbol)} > 12")

    if strict:
        if not NASDAQ_PATTERN.match(symbol):
            raise ValidationError(f"Invalid NASDAQ symbol format: {symbol}")
    else:
        if not SYMBOL_PATTERN.match(symbol):
            raise ValidationError(f"Invalid symbol format: {symbol}")

    return symbol


def validate_percentage(value: int | float | str, min_pct: float = 0, max_pct: float = 100) -> float:
    """
    Validate percentage value is within bounds.

    Args:
        value: Percentage value (0-100)
        min_pct: Minimum allowed percentage
        max_pct: Maximum allowed percentage

    Returns:
        Float percentage value

    Raises:
        ValidationError: If out of bounds or invalid format
    """
    try:
        pct = float(value)
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid percentage value: {value}") from None

    if pct < min_pct or pct > max_pct:
        raise ValidationError(f"Percentage out of range: {pct} not in [{min_pct}, {max_pct}]")

    return pct


def validate_price(price: int | float | str, min_price: float = 0.01, max_price: float = 1_000_000) -> Decimal:
    """
    Validate stock price.

    Args:
        price: Stock price
        min_price: Minimum allowed price
        max_price: Maximum allowed price

    Returns:
        Decimal price value

    Raises:
        ValidationError: If out of range or invalid format
    """
    try:
        price_decimal = Decimal(str(price))
    except (InvalidOperation, ValueError):
        raise ValidationError(f"Invalid price format: {price}") from None

    if price_decimal <= 0:
        raise ValidationError(f"Price must be positive: {price}")

    if price_decimal < Decimal(str(min_price)):
        raise ValidationError(f"Price too low: {price} < {min_price}")

    if price_decimal > Decimal(str(max_price)):
        raise ValidationError(f"Price too high: {price} > {max_price}")

    return price_decimal


def validate_quantity(qty: int | str, min_qty: int = 1, max_qty: int = 1_000_000) -> int:
    """
    Validate trade quantity.

    Args:
        qty: Number of shares
        min_qty: Minimum shares
        max_qty: Maximum shares

    Returns:
        Integer quantity

    Raises:
        ValidationError: If out of range or invalid
    """
    try:
        quantity = int(qty)
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid quantity: {qty}") from None

    if quantity < min_qty:
        raise ValidationError(f"Quantity too low: {quantity} < {min_qty}")

    if quantity > max_qty:
        raise ValidationError(f"Quantity too high: {quantity} > {max_qty}")

    return quantity


def validate_risk_multiple(r_multiple: int | float | str) -> float:
    """
    Validate R-multiple (risk/reward ratio).

    Args:
        r_multiple: R-multiple value (should be positive)

    Returns:
        Float R-multiple

    Raises:
        ValidationError: If invalid or negative
    """
    try:
        r = float(r_multiple)
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid R-multiple: {r_multiple}") from None

    if r <= 0:
        raise ValidationError(f"R-multiple must be positive: {r}")

    if r > 100:  # Sanity check
        raise ValidationError(f"R-multiple unusually high: {r}")

    return r


def validate_date_string(date_str: str, format_str: str = "%Y-%m-%d") -> str:
    """
    Validate date string format.

    Args:
        date_str: Date string to validate
        format_str: Expected format (default: YYYY-MM-DD)

    Returns:
        Validated date string

    Raises:
        ValidationError: If invalid format
    """
    from datetime import datetime

    try:
        datetime.strptime(date_str, format_str)
        return date_str
    except ValueError:
        raise ValidationError(f"Invalid date format: {date_str} (expected {format_str})")


def validate_integer_range(
    value: int | str,
    min_val: int | None = None,
    max_val: int | None = None,
    name: str = "value",
) -> int:
    """
    Generic integer range validation.

    Args:
        value: Integer value
        min_val: Minimum value (None = no minimum)
        max_val: Maximum value (None = no maximum)
        name: Parameter name for error messages

    Returns:
        Validated integer

    Raises:
        ValidationError: If out of range or invalid format
    """
    try:
        int_val = int(value)
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid integer for {name}: {value}") from None

    if min_val is not None and int_val < min_val:
        raise ValidationError(f"{name} too low: {int_val} < {min_val}")

    if max_val is not None and int_val > max_val:
        raise ValidationError(f"{name} too high: {int_val} > {max_val}")

    return int_val


def validate_float_range(
    value: int | float | str,
    min_val: float | None = None,
    max_val: float | None = None,
    name: str = "value",
) -> float:
    """
    Generic float range validation.

    Args:
        value: Float value
        min_val: Minimum value (None = no minimum)
        max_val: Maximum value (None = no maximum)
        name: Parameter name for error messages

    Returns:
        Validated float

    Raises:
        ValidationError: If out of range or invalid format
    """
    try:
        float_val = float(value)
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid float for {name}: {value}") from None

    if min_val is not None and float_val < min_val:
        raise ValidationError(f"{name} too low: {float_val} < {min_val}")

    if max_val is not None and float_val > max_val:
        raise ValidationError(f"{name} too high: {float_val} > {max_val}")

    return float_val


def validate_email(email: str) -> str:
    """
    Validate email address format (basic).

    Args:
        email: Email address

    Returns:
        Validated email (lowercase)

    Raises:
        ValidationError: If invalid format
    """
    email = email.strip().lower()

    # Basic email validation
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise ValidationError(f"Invalid email format: {email}")

    if len(email) > 254:
        raise ValidationError(f"Email too long: {len(email)} > 254")

    return email


def validate_order_type(order_type: str) -> str:
    """
    Validate order type against allowed values.

    Args:
        order_type: Order type (e.g., 'market', 'limit', 'stop')

    Returns:
        Validated order type (lowercase)

    Raises:
        ValidationError: If not in whitelist
    """
    valid_types = {"market", "limit", "stop", "stop_limit", "trailing_stop"}
    order_type = order_type.lower().strip()

    if order_type not in valid_types:
        raise ValidationError(f"Invalid order type: {order_type}. Must be one of: {valid_types}")

    return order_type


def validate_position_side(side: str) -> str:
    """
    Validate position side (long/short).

    Args:
        side: Position side

    Returns:
        Validated side (lowercase)

    Raises:
        ValidationError: If not 'long' or 'short'
    """
    side = side.lower().strip()

    if side not in {"long", "short"}:
        raise ValidationError(f"Invalid position side: {side}. Must be 'long' or 'short'")

    return side
