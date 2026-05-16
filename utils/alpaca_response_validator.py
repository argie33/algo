#!/usr/bin/env python3
"""
Alpaca API Response Validation

Provides defensive validation for all Alpaca API responses to prevent
silent failures from missing fields, null values, or invalid types.

Pattern: Call validate() after every API response to catch errors early.
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class AlpacaResponseValidator:
    """Validates Alpaca API responses for required fields and types."""

    @staticmethod
    def validate_order_response(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate order creation response from POST /v2/orders.

        Returns: {
            'valid': bool,
            'errors': [str] or [],
            'order_id': str or None,
            'status': str or None,
            'filled_avg_price': float or None,
            'order_class': str ('simple' or 'bracket'),
            'legs': [dict] or [],
        }
        """
        if not isinstance(data, dict):
            return {
                'valid': False,
                'errors': ['Response is not a dictionary'],
                'order_id': None,
                'status': None,
                'filled_avg_price': None,
                'order_class': 'simple',
                'legs': [],
            }

        errors = []
        order_id = data.get('id')
        status = data.get('status')
        filled_avg_price = data.get('filled_avg_price')
        order_class = data.get('order_class', 'simple')
        legs = data.get('legs', [])

        # Validate required fields
        if not order_id:
            errors.append('Missing or empty order ID')
        elif not isinstance(order_id, str):
            errors.append(f'Order ID must be string, got {type(order_id).__name__}')

        if not status:
            errors.append('Missing or empty status')
        elif status not in ('pending_new', 'accepted', 'pending_new', 'accepted_for_bidding',
                           'filled', 'partially_filled', 'pending_cancel', 'cancelled', 'rejected'):
            errors.append(f'Invalid status value: {status}')

        # Validate filled price (optional, only if filled)
        if filled_avg_price is not None:
            try:
                filled_float = float(filled_avg_price)
                if filled_float < 0:
                    errors.append(f'Filled price must be non-negative, got {filled_float}')
                filled_avg_price = filled_float
            except (ValueError, TypeError):
                errors.append(f'Filled price not numeric: {filled_avg_price}')
                filled_avg_price = None

        # Validate bracket legs if order_class is bracket
        if order_class == 'bracket':
            if not isinstance(legs, list):
                errors.append(f'Legs must be list, got {type(legs).__name__}')
                legs = []
            elif len(legs) < 2:
                errors.append(f'Bracket order requires 2+ legs, got {len(legs)}')

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'order_id': order_id,
            'status': status,
            'filled_avg_price': filled_avg_price,
            'order_class': order_class,
            'legs': legs,
        }

    @staticmethod
    def validate_order_status_response(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate order status response from GET /v2/orders/{order_id}.

        Returns: {
            'valid': bool,
            'errors': [str] or [],
            'status': str or None,
            'filled_qty': int or None,
            'filled_avg_price': float or None,
            'qty': int or None,
        }
        """
        if not isinstance(data, dict):
            return {
                'valid': False,
                'errors': ['Response is not a dictionary'],
                'status': None,
                'filled_qty': None,
                'filled_avg_price': None,
                'qty': None,
            }

        errors = []
        status = data.get('status')
        filled_qty = data.get('filled_qty')
        filled_avg_price = data.get('filled_avg_price')
        qty = data.get('qty')

        # Validate status
        if not status:
            errors.append('Missing or empty status')

        # Validate quantities (must be non-negative integers if present)
        if filled_qty is not None:
            try:
                filled_qty = int(filled_qty)
                if filled_qty < 0:
                    errors.append(f'Filled qty must be non-negative, got {filled_qty}')
            except (ValueError, TypeError):
                errors.append(f'Filled qty not integer: {filled_qty}')
                filled_qty = None

        if qty is not None:
            try:
                qty = int(qty)
                if qty < 0:
                    errors.append(f'Qty must be non-negative, got {qty}')
            except (ValueError, TypeError):
                errors.append(f'Qty not integer: {qty}')
                qty = None

        # Validate filled price (optional)
        if filled_avg_price is not None:
            try:
                filled_avg_price = float(filled_avg_price)
                if filled_avg_price < 0:
                    errors.append(f'Filled price must be non-negative, got {filled_avg_price}')
            except (ValueError, TypeError):
                errors.append(f'Filled price not numeric: {filled_avg_price}')
                filled_avg_price = None

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'status': status,
            'filled_qty': filled_qty,
            'filled_avg_price': filled_avg_price,
            'qty': qty,
        }

    @staticmethod
    def validate_account_response(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate account response from GET /v2/account.

        Returns: {
            'valid': bool,
            'errors': [str] or [],
            'portfolio_value': float or None,
            'cash': float or None,
            'buying_power': float or None,
        }
        """
        if not isinstance(data, dict):
            return {
                'valid': False,
                'errors': ['Response is not a dictionary'],
                'portfolio_value': None,
                'cash': None,
                'buying_power': None,
            }

        errors = []

        # Portfolio value (required)
        portfolio_value = data.get('portfolio_value') or data.get('equity')
        if portfolio_value is not None:
            try:
                portfolio_value = float(portfolio_value)
                if portfolio_value < 0:
                    errors.append(f'Portfolio value must be non-negative, got {portfolio_value}')
            except (ValueError, TypeError):
                errors.append(f'Portfolio value not numeric: {portfolio_value}')
                portfolio_value = None

        # Cash (optional but important)
        cash = data.get('cash')
        if cash is not None:
            try:
                cash = float(cash)
                if cash < 0:
                    errors.append(f'Cash must be non-negative, got {cash}')
            except (ValueError, TypeError):
                errors.append(f'Cash not numeric: {cash}')
                cash = None

        # Buying power (optional)
        buying_power = data.get('buying_power')
        if buying_power is not None:
            try:
                buying_power = float(buying_power)
                if buying_power < 0:
                    errors.append(f'Buying power must be non-negative, got {buying_power}')
            except (ValueError, TypeError):
                errors.append(f'Buying power not numeric: {buying_power}')
                buying_power = None

        return {
            'valid': portfolio_value is not None and len(errors) == 0,
            'errors': errors,
            'portfolio_value': portfolio_value,
            'cash': cash,
            'buying_power': buying_power,
        }

    @staticmethod
    def validate_position_response(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate single position response from GET /v2/positions/{symbol}.

        Returns: {
            'valid': bool,
            'errors': [str] or [],
            'symbol': str or None,
            'qty': int or None,
            'current_price': float or None,
        }
        """
        if not isinstance(data, dict):
            return {
                'valid': False,
                'errors': ['Response is not a dictionary'],
                'symbol': None,
                'qty': None,
                'current_price': None,
            }

        errors = []
        symbol = data.get('symbol')
        qty = data.get('qty')
        current_price = data.get('current_price')

        if not symbol:
            errors.append('Missing symbol')

        if qty is not None:
            try:
                qty = int(qty)
            except (ValueError, TypeError):
                errors.append(f'Qty not integer: {qty}')
                qty = None

        if current_price is not None:
            try:
                current_price = float(current_price)
                if current_price < 0:
                    errors.append(f'Price must be non-negative, got {current_price}')
            except (ValueError, TypeError):
                errors.append(f'Price not numeric: {current_price}')
                current_price = None

        return {
            'valid': symbol is not None and len(errors) == 0,
            'errors': errors,
            'symbol': symbol,
            'qty': qty,
            'current_price': current_price,
        }

    @staticmethod
    def log_validation_errors(response_type: str, errors: List[str], context: str = '') -> None:
        """Log validation errors for debugging.

        Args:
            response_type: 'order', 'account', 'position', etc.
            errors: List of error messages
            context: Additional context (symbol, order_id, etc.)
        """
        for error in errors:
            logger.error(f"[Alpaca {response_type} Validation] {error} {context}")


__all__ = ['AlpacaResponseValidator']
