#!/usr/bin/env python3
"""
Alpaca API Response Validation

Provides defensive validation for all Alpaca API responses to prevent
silent failures from missing fields, null values, or invalid types.

Pattern: Call validate() after every API response to catch errors early.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AlpacaResponseValidator:

    @staticmethod
    def validate_order_response(data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {
                "valid": False,
                "errors": ["Response is not a dictionary"],
                "order_id": None,
                "status": None,
                "filled_avg_price": None,
                "order_class": "simple",
                "legs": [],
            }

        errors = []
        # Explicitly check for each field rather than silent .get() defaults
        order_id = data.get("id") if "id" in data else None
        status = data.get("status") if "status" in data else None
        filled_avg_price = data.get("filled_avg_price") if "filled_avg_price" in data else None
        # order_class is optional, default to simple only if missing (explicit intent)
        order_class = data.get("order_class") if "order_class" in data else "simple"
        legs = data.get("legs") if "legs" in data else None

        if not order_id:
            errors.append("Missing or empty order ID")
        elif not isinstance(order_id, str):
            errors.append(f"Order ID must be string, got {type(order_id).__name__}")

        if not status:
            errors.append("Missing or empty status")
        elif status not in (
            "pending_new",
            "accepted",
            "pending_new",
            "accepted_for_bidding",
            "filled",
            "partially_filled",
            "pending_cancel",
            "cancelled",
            "rejected",
        ):
            errors.append(f"Invalid status value: {status}")

        if filled_avg_price is not None:
            try:
                filled_float = float(filled_avg_price)
                if filled_float < 0:
                    errors.append(f"Filled price must be non-negative, got {filled_float}")
                filled_avg_price = filled_float
            except (ValueError, TypeError):
                errors.append(f"Filled price not numeric: {filled_avg_price}")
                filled_avg_price = None

        if order_class == "bracket":
            if not isinstance(legs, list):
                errors.append(f"Legs must be list, got {type(legs).__name__}")
                # Don't silently fall back to empty list - mark as invalid
                legs = None
            elif len(legs) < 2:
                errors.append(f"Bracket order requires 2+ legs, got {len(legs)}")

        # Explicitly extract rejection reason - don't chain or operations
        rejection_reason = None
        if "cancel_reason" in data and data["cancel_reason"] is not None:
            rejection_reason = data["cancel_reason"]
        elif "failed_reason" in data and data["failed_reason"] is not None:
            rejection_reason = data["failed_reason"]
        elif "reason" in data and data["reason"] is not None:
            rejection_reason = data["reason"]

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "order_id": order_id,
            "status": status,
            "filled_avg_price": filled_avg_price,
            "order_class": order_class,
            "legs": legs,
            "rejection_reason": rejection_reason,
        }

    @staticmethod
    def validate_order_status_response(data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {
                "valid": False,
                "errors": ["Response is not a dictionary"],
                "status": None,
                "filled_qty": None,
                "filled_avg_price": None,
                "qty": None,
            }

        errors = []
        # Explicitly check for each field - avoid silent .get() defaults
        status = data.get("status") if "status" in data else None
        filled_qty = data.get("filled_qty") if "filled_qty" in data else None
        filled_avg_price = data.get("filled_avg_price") if "filled_avg_price" in data else None
        qty = data.get("qty") if "qty" in data else None

        if not status:
            errors.append("Missing or empty status")

        if filled_qty is not None:
            try:
                filled_qty = int(filled_qty)
                if filled_qty < 0:
                    errors.append(f"Filled qty must be non-negative, got {filled_qty}")
            except (ValueError, TypeError):
                errors.append(f"Filled qty not integer: {filled_qty}")
                filled_qty = None

        if qty is not None:
            try:
                qty = int(qty)
                if qty < 0:
                    errors.append(f"Qty must be non-negative, got {qty}")
            except (ValueError, TypeError):
                errors.append(f"Qty not integer: {qty}")
                qty = None

        if filled_avg_price is not None:
            try:
                filled_avg_price = float(filled_avg_price)
                if filled_avg_price < 0:
                    errors.append(f"Filled price must be non-negative, got {filled_avg_price}")
            except (ValueError, TypeError):
                errors.append(f"Filled price not numeric: {filled_avg_price}")
                filled_avg_price = None

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "status": status,
            "filled_qty": filled_qty,
            "filled_avg_price": filled_avg_price,
            "qty": qty,
        }

    @staticmethod
    def validate_position_response(data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {
                "valid": False,
                "errors": ["Response is not a dictionary"],
                "symbol": None,
                "qty": None,
                "current_price": None,
            }

        errors = []
        # Explicitly check for each field - avoid silent .get() defaults
        symbol = data.get("symbol") if "symbol" in data else None
        qty = data.get("qty") if "qty" in data else None
        current_price = data.get("current_price") if "current_price" in data else None

        if not symbol:
            errors.append("Missing symbol")

        if qty is not None:
            try:
                qty = int(qty)
            except (ValueError, TypeError):
                errors.append(f"Qty not integer: {qty}")
                qty = None

        if current_price is not None:
            try:
                current_price = float(current_price)
                if current_price < 0:
                    errors.append(f"Price must be non-negative, got {current_price}")
            except (ValueError, TypeError):
                errors.append(f"Price not numeric: {current_price}")
                current_price = None

        return {
            "valid": symbol is not None and len(errors) == 0,
            "errors": errors,
            "symbol": symbol,
            "qty": qty,
            "current_price": current_price,
        }

    @staticmethod
    def log_validation_errors(response_type: str, errors: list[str], context: str = "") -> None:
        """Log validation errors for debugging.

        Args:
            response_type: 'order', 'account', 'position', etc.
            errors: List of error messages
            context: Additional context (symbol, order_id, etc.)
        """
        for error in errors:
            logger.error(f"[Alpaca {response_type} Validation] {error} {context}")


__all__ = ["AlpacaResponseValidator"]
