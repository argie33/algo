#!/usr/bin/env python3
"""
Financial Data Validator - Specialized validation for critical trading data

Ensures trading prices, quantities, and positions meet strict integrity requirements:
- No silent fallback to 0 or placeholder values
- All conversions logged with context
- Type-safe with proper range checking
- Prevents NaN, Infinity, negative prices (where invalid)
"""

import logging
import math
from decimal import Decimal, InvalidOperation
from typing import Any


logger = logging.getLogger(__name__)


class FinancialDataValidator:
    """Validates financial data with fail-closed behavior."""

    @staticmethod
    def validate_price(price: Any, context: str = "", allow_zero: bool = False) -> tuple[bool, float | None, str]:
        """Validate a price value (entry, exit, stop loss, etc).

        Args:
            price: Price value (can be str, int, float, Decimal, None)
            context: Context for logging (e.g., "entry_price for AAPL")
            allow_zero: Whether 0 is valid (usually False for prices)

        Returns:
            (is_valid, price_float, error_message)
            - is_valid: True if valid
            - price_float: Converted float if valid, None otherwise
            - error_message: Descriptive error if invalid
        """
        if price is None:
            msg = f"Price is None {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, msg

        # Handle Decimal and convert to float
        if isinstance(price, Decimal):
            try:
                price = float(price)
            except (ValueError, TypeError, InvalidOperation) as e:
                msg = f"Price (Decimal) not convertible: {price!r} {context} ({e})"
                logger.error(f"[FINANCIAL_VALIDATION] {msg}")
                return False, None, msg
        else:
            try:
                price = float(price)
            except (ValueError, TypeError) as e:
                msg = f"Price not numeric: {price!r} {context} ({e})"
                logger.error(f"[FINANCIAL_VALIDATION] {msg}")
                return False, None, msg

        # Check for NaN and Infinity
        if math.isnan(price):
            msg = f"Price is NaN {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, msg
        if math.isinf(price):
            msg = f"Price is Infinity {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, msg

        # Check range
        if price < 0:
            msg = f"Price cannot be negative: {price:.2f} {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, msg

        if price == 0 and not allow_zero:
            msg = f"Price cannot be zero {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, msg

        return True, price, ""

    @staticmethod
    def validate_quantity(qty: Any, context: str = "") -> tuple[bool, int | None, str]:
        """Validate position/order quantity (must be positive integer).

        Args:
            qty: Quantity value (can be str, int, float)
            context: Context for logging (e.g., "entry_qty for AAPL")

        Returns:
            (is_valid, qty_int, error_message)
        """
        if qty is None:
            msg = f"Quantity is None {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, msg

        try:
            qty_int = int(float(qty))  # Convert float to int (rounds down)
        except (ValueError, TypeError, OverflowError) as e:
            msg = f"Quantity not numeric or overflow: {qty!r} {context} ({e})"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, msg
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Unexpected error in quantity validation: {e}. Cannot proceed.") from e

        if qty_int <= 0:
            msg = f"Quantity must be positive: {qty_int} {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, msg

        return True, qty_int, ""

    @staticmethod
    def validate_stop_loss(entry_price: float, stop_loss: float, context: str = "") -> tuple[bool, str]:
        """Validate stop loss is below entry price.

        Args:
            entry_price: Entry price (must be > 0)
            stop_loss: Stop loss price (must be > 0 and < entry_price)
            context: Context for logging

        Returns:
            (is_valid, error_message)
        """
        if entry_price <= 0:
            msg = f"Entry price invalid for stop loss check: {entry_price:.2f} {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, msg

        if stop_loss <= 0:
            msg = f"Stop loss must be positive: {stop_loss:.2f} {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, msg

        if stop_loss >= entry_price:
            msg = f"Stop loss {stop_loss:.2f} must be below entry {entry_price:.2f} {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, msg

        # Warn if stop is very tight (< 1% risk)
        risk_pct = (entry_price - stop_loss) / entry_price * 100
        if risk_pct < 1.0:
            logger.warning(f"[FINANCIAL_VALIDATION] Stop loss is very tight ({risk_pct:.2f}% risk) {context}")

        return True, ""

    @staticmethod
    def validate_pnl_calculation(
        entry: float, exit_price: float, qty: int, context: str = ""
    ) -> tuple[bool, float | None, float | None, str]:
        """Validate P&L calculation inputs.

        Args:
            entry: Entry price
            exit_price: Exit price
            qty: Position quantity
            context: Context for logging

        Returns:
            (is_valid, pnl_dollars, pnl_pct, error_message)
        """
        if entry <= 0:
            msg = f"Entry price must be positive for P&L: {entry:.2f} {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, None, msg

        if exit_price <= 0:
            msg = f"Exit price must be positive for P&L: {exit_price:.2f} {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, None, msg

        if qty <= 0:
            msg = f"Quantity must be positive for P&L: {qty} {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, None, msg

        try:
            pnl_dollars = (exit_price - entry) * qty
            pnl_pct = (exit_price - entry) / entry * 100.0
        except (ValueError, TypeError, ZeroDivisionError, OverflowError) as e:
            msg = f"P&L calculation failed {context}: {e}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, None, msg
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error in P&L calculation: {e}. "
                "Precondition checks failed; entry={entry}, exit={exit_price}, qty={qty}"
            ) from e

        return True, pnl_dollars, pnl_pct, ""

    @staticmethod
    def validate_r_multiple(
        entry: float, exit_price: float, stop_loss: float, context: str = ""
    ) -> tuple[bool, float | None, str]:
        """Validate R-multiple (risk/reward ratio) calculation.

        Args:
            entry: Entry price
            exit_price: Exit price
            stop_loss: Stop loss price
            context: Context for logging

        Returns:
            (is_valid, r_multiple, error_message)
        """
        if entry <= 0 or stop_loss <= 0:
            msg = f"Invalid prices for R calculation: entry={entry:.2f}, stop={stop_loss:.2f} {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, msg

        risk = entry - stop_loss
        if risk <= 0:
            msg = f"Risk must be positive: {risk:.2f} {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, msg

        if exit_price <= 0:
            msg = f"Exit price must be positive: {exit_price:.2f} {context}"
            logger.error(f"[FINANCIAL_VALIDATION] {msg}")
            return False, None, msg

        r_multiple = (exit_price - entry) / risk

        return True, r_multiple, ""


# Convenience function for common validation pattern
def validate_trade_entry_prices(
    symbol: str, entry_price: Any, stop_loss_price: Any
) -> tuple[bool, float | None, float | None, str]:
    """Validate entry and stop loss prices for a trade entry.

    Returns:
        (is_valid, entry_float, stop_loss_float, error_message)
    """
    valid, entry_f, err1 = FinancialDataValidator.validate_price(
        entry_price, context=f"entry_price for {symbol}", allow_zero=False
    )
    if not valid:
        return False, None, None, err1

    valid, stop_f, err2 = FinancialDataValidator.validate_price(
        stop_loss_price, context=f"stop_loss_price for {symbol}", allow_zero=False
    )
    if not valid:
        return False, None, None, err2

    valid, err3 = FinancialDataValidator.validate_stop_loss(
        entry_f or 0.0, stop_f or 0.0, context=f"trade entry for {symbol}"
    )
    if not valid:
        return False, None, None, err3

    return True, entry_f, stop_f, ""
