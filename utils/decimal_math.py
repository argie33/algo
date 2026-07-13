"""
Decimal math utilities for financial calculations with precise 2-decimal-place rounding.

Solves the IEEE 754 float precision problem while keeping code clean and readable.
All functions return floats (for database/API compatibility) with 2-decimal precision.
"""

from decimal import ROUND_HALF_UP, Decimal


def to_decimal(value: float | str | int | Decimal) -> Decimal:
    """Convert any numeric type to Decimal safely."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    return Decimal(str(value))


def quantize_price(value: float | Decimal | str) -> float:
    """Round to 2 decimal places using banker's rounding. Returns float for DB/API."""
    decimal_value = to_decimal(value)
    rounded = decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(rounded)


def add(a: float | str | int | Decimal, b: float | str | int | Decimal) -> float:
    """Add two numbers with precise decimal arithmetic."""
    result = to_decimal(a) + to_decimal(b)
    return quantize_price(result)


def subtract(a: float | str | int | Decimal, b: float | str | int | Decimal) -> float:
    """Subtract b from a with precise decimal arithmetic."""
    result = to_decimal(a) - to_decimal(b)
    return quantize_price(result)


def multiply(a: float | str | int | Decimal, b: float | str | int | Decimal) -> float:
    """Multiply two numbers with precise decimal arithmetic."""
    result = to_decimal(a) * to_decimal(b)
    return quantize_price(result)


def divide(a: float | str | int | Decimal, b: float | str | int | Decimal) -> float:
    """Divide a by b with precise decimal arithmetic. Raises if b is 0."""
    divisor = to_decimal(b)
    if divisor == 0:
        raise ZeroDivisionError(f"Cannot divide {a} by zero")
    result = to_decimal(a) / divisor
    return quantize_price(result)


def percentage(value: float | str | int | Decimal, percentage_val: float | str | int | Decimal) -> float:
    return multiply(value, divide(percentage_val, 100))


def percentage_change(old: float | str | int | Decimal, new: float | str | int | Decimal) -> float:
    old_d = to_decimal(old)
    if old_d == 0:
        raise ValueError(f"Cannot calculate percentage change: old value is 0, new value is {new}")
    change = (to_decimal(new) - old_d) / old_d * Decimal(100)
    return quantize_price(change)


def r_multiple(
    current_price: float | str | int | Decimal,
    entry_price: float | str | int | Decimal,
    stop_loss: float | str | int | Decimal,
) -> float:
    """
    Calculate R-multiple (risk units): (current - entry) / (entry - stop).
    Raises if risk is <= 0 (invalid trade setup).
    """
    risk = to_decimal(entry_price) - to_decimal(stop_loss)
    if risk <= 0:
        raise ValueError(f"Invalid trade setup for R-multiple: entry={entry_price}, stop_loss={stop_loss}, risk={risk}")
    result = (to_decimal(current_price) - to_decimal(entry_price)) / risk
    return quantize_price(result)


def position_value(shares: float | str | int | Decimal, price: float | str | int | Decimal) -> float:
    return multiply(shares, price)


def average_fill_price(
    total_cost: float | str | int | Decimal,
    total_shares: float | str | int | Decimal,
) -> float:
    return divide(total_cost, total_shares)


def pnl_percent(
    entry_price: float | str | int | Decimal,
    exit_price: float | str | int | Decimal,
) -> float:
    return percentage_change(entry_price, exit_price)


def pnl_dollars(
    entry_price: float | str | int | Decimal,
    exit_price: float | str | int | Decimal,
    shares: float | str | int | Decimal,
) -> float:
    return multiply(subtract(exit_price, entry_price), shares)
