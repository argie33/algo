#!/usr/bin/env python3
"""
Validation Integration Module - Usage Patterns and Setup

This module shows how to use the unified validation framework and sets up
the global validator registry with all domain-specific validators.

QUICK START:

    from utils.validation import get_validators
    validators = get_validators()

    # Validate a phase result
    result = validators.validate('phase_results', [
        {'name': 'PreTrade', 'status': 'ok'},
        {'name': 'Execute', 'status': 'completed'},
    ])
    if result.is_valid:
        phases = result.data

PATTERNS:

(1) Simple type validation:
    from utils.validation import TypeValidator
    validator = TypeValidator('float', min_val=0.0)
    result = validator.validate(45.50)

(2) Schema validation:
    from utils.validation import SchemaValidator, TypeValidator
    schema = SchemaValidator({
        'price': TypeValidator('float', min_val=0),
        'date': TypeValidator('date'),
    })
    result = schema.validate({'price': 45.50, 'date': '2026-06-12'})

(3) List validation:
    from utils.validation import ListValidator, PhaseValidator
    phases = ListValidator(PhaseValidator())
    result = phases.validate([
        {'name': 'Phase1', 'status': 'ok'},
        {'name': 'Phase2', 'status': 'completed'},
    ])

(4) Using registry:
    validators = get_validators()
    result = validators.validate('alpaca_order', order_data)
    if not result.is_valid:
        logger.error(f"Order validation failed: {result.errors}")
"""

import logging
from typing import Dict, Any

from utils.validation import ValidatorRegistry, get_global_registry
from utils.validation import create_default_registry

logger = logging.getLogger(__name__)

_initialized = False


def initialize_validators():
    """Initialize the global validator registry with all domain validators.

    Call this once at application startup (e.g., in main() or __init__).
    """
    global _initialized

    if _initialized:
        logger.debug("Validators already initialized")
        return

    registry = get_global_registry()
    default_registry = create_default_registry()

    # Copy all validators from default registry to global registry
    for validator_name, validator in default_registry._validators.items():
        registry.register(
            validator_name,
            validator,
            default_registry._metadata[validator_name].get("description", ""),
        )

    _initialized = True
    logger.info(
        f"Validator registry initialized with {len(registry._validators)} validators: "
        f"{list(registry._validators.keys())}"
    )


def get_validators() -> ValidatorRegistry:
    """Get the global validator registry, initializing if needed.

    Returns:
        ValidatorRegistry with all registered validators
    """
    if not _initialized:
        initialize_validators()

    return get_global_registry()


def validate_phase_results(phase_results: Any) -> Dict[str, Any]:
    """Validate orchestrator phase results using the framework.

    This is the recommended way to validate phase results instead of calling
    validate_phase_results() directly in dashboard.py.

    Args:
        phase_results: List of phase dicts with 'name' and 'status'

    Returns:
        {
            'valid': bool,
            'phases': List[Dict] or None (cleaned data),
            'errors': List[str] or []
        }
    """
    validators = get_validators()
    result = validators.validate("phase_results", phase_results, context="phase_results")

    return {
        "valid": result.is_valid,
        "phases": result.data,
        "errors": result.errors,
    }


def validate_alpaca_order(order_data: Any) -> Dict[str, Any]:
    """Validate Alpaca order response using the framework.

    Args:
        order_data: Alpaca API order response dict

    Returns:
        {
            'valid': bool,
            'order': Dict or None (cleaned data),
            'errors': List[str] or []
        }
    """
    validators = get_validators()
    result = validators.validate("alpaca_order", order_data, context="alpaca_order")

    return {
        "valid": result.is_valid,
        "order": result.data,
        "errors": result.errors,
    }


def validate_alpaca_order_status(order_data: Any) -> Dict[str, Any]:
    """Validate Alpaca order status response using the framework.

    Args:
        order_data: Alpaca API order status response dict

    Returns:
        {
            'valid': bool,
            'order': Dict or None (cleaned data),
            'errors': List[str] or []
        }
    """
    validators = get_validators()
    result = validators.validate("alpaca_order_status", order_data, context="alpaca_order_status")

    return {
        "valid": result.is_valid,
        "order": result.data,
        "errors": result.errors,
    }


def validate_alpaca_account(account_data: Any) -> Dict[str, Any]:
    """Validate Alpaca account response using the framework.

    Args:
        account_data: Alpaca API account response dict

    Returns:
        {
            'valid': bool,
            'account': Dict or None (cleaned data),
            'errors': List[str] or []
        }
    """
    validators = get_validators()
    result = validators.validate("alpaca_account", account_data, context="alpaca_account")

    return {
        "valid": result.is_valid,
        "account": result.data,
        "errors": result.errors,
    }


def validate_alpaca_position(position_data: Any) -> Dict[str, Any]:
    """Validate Alpaca position response using the framework.

    Args:
        position_data: Alpaca API position response dict

    Returns:
        {
            'valid': bool,
            'position': Dict or None (cleaned data),
            'errors': List[str] or []
        }
    """
    validators = get_validators()
    result = validators.validate("alpaca_position", position_data, context="alpaca_position")

    return {
        "valid": result.is_valid,
        "position": result.data,
        "errors": result.errors,
    }


# Example demonstrating the unified framework
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("=" * 80)
    print("Unified Validation Framework - Demonstration")
    print("=" * 80)

    # Initialize validators
    validators = get_validators()

    print(f"\nRegistered validators: {list(validators._validators.keys())}")

    # Example 1: Validate phase results
    print("\n--- Example 1: Validate phase results ---")
    phases = [
        {"name": "PreTrade", "status": "ok"},
        {"name": "Execute", "status": "completed"},
    ]
    phase_result = validators.validate("phase_results", phases)
    print(f"Validation result: {phase_result}")
    if phase_result.is_valid:
        print(f"Cleaned phases: {phase_result.data}")

    # Example 2: Validate Alpaca order
    print("\n--- Example 2: Validate Alpaca order ---")
    order = {
        "id": "abc123",
        "status": "filled",
        "filled_avg_price": 150.25,
        "order_class": "simple",
    }
    order_result = validators.validate("alpaca_order", order)
    print(f"Validation result: {order_result}")
    if order_result.is_valid:
        print(f"Cleaned order: {order_result.data}")
