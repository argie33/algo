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
from typing import Any

from utils.validation import (
    ValidatorRegistry,
    create_default_registry,
    get_global_registry,
)

logger = logging.getLogger(__name__)

_initialized = False


def initialize_validators() -> None:
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
        # Explicit metadata access - don't silently fall back to empty string
        metadata = (
            default_registry._metadata.get(validator_name) if validator_name in default_registry._metadata else {}
        )
        description = metadata.get("description", "") if isinstance(metadata, dict) else ""
        if not description:
            logger.debug(f"No description found for validator '{validator_name}', using empty string")
        registry.register(
            validator_name,
            validator,
            description or "",
        )

    _initialized = True
    logger.info(
        f"Validator registry initialized with {len(registry._validators)} validators: "
        f"{list(registry._validators.keys())}"
    )


def get_validators() -> ValidatorRegistry:
    if not _initialized:
        initialize_validators()

    return get_global_registry()


def validate_phase_results(phase_results: Any) -> dict[str, Any]:
    """Validate orchestrator phase results using the framework.

    This is the recommended way to validate phase results instead of calling
    validate_phase_results() directly in dashboard.py.

    Args:
        phase_results: List of phase dicts with 'name' and 'status'

    Returns:
        {
            'valid': bool (True only if all validations pass),
            'phases': List[Dict] if valid, None if validation failed,
            'errors': List[str] with error messages, empty list if valid
        }
    """
    validators = get_validators()
    result = validators.validate("phase_results", phase_results, context="phase_results")

    # Explicit: Only return data when validation passes
    return {
        "valid": result.is_valid,
        "phases": result.data if result.is_valid else None,
        "errors": result.errors,
    }


def validate_alpaca_order(order_data: Any) -> dict[str, Any]:
    """Validate Alpaca order response using the framework.

    Args:
        order_data: Alpaca API order response dict

    Returns:
        {
            'valid': bool (True only if all validations pass),
            'order': Dict if valid, None if validation failed,
            'errors': List[str] with error messages, empty list if valid
        }
    """
    validators = get_validators()
    result = validators.validate("alpaca_order", order_data, context="alpaca_order")

    # Explicit: Only return data when validation passes
    return {
        "valid": result.is_valid,
        "order": result.data if result.is_valid else None,
        "errors": result.errors,
    }


def validate_alpaca_order_status(order_data: Any) -> dict[str, Any]:
    """Validate Alpaca order status response using the framework.

    Args:
        order_data: Alpaca API order status response dict

    Returns:
        {
            'valid': bool (True only if all validations pass),
            'order': Dict if valid, None if validation failed,
            'errors': List[str] with error messages, empty list if valid
        }
    """
    validators = get_validators()
    result = validators.validate("alpaca_order_status", order_data, context="alpaca_order_status")

    # Explicit: Only return data when validation passes
    return {
        "valid": result.is_valid,
        "order": result.data if result.is_valid else None,
        "errors": result.errors,
    }


def validate_alpaca_account(account_data: Any) -> dict[str, Any]:
    """Validate Alpaca account response using the framework.

    Args:
        account_data: Alpaca API account response dict

    Returns:
        {
            'valid': bool (True only if all validations pass),
            'account': Dict if valid, None if validation failed,
            'errors': List[str] with error messages, empty list if valid
        }
    """
    validators = get_validators()
    result = validators.validate("alpaca_account", account_data, context="alpaca_account")

    # Explicit: Only return data when validation passes
    return {
        "valid": result.is_valid,
        "account": result.data if result.is_valid else None,
        "errors": result.errors,
    }


def validate_alpaca_position(position_data: Any) -> dict[str, Any]:
    """Validate Alpaca position response using the framework.

    Args:
        position_data: Alpaca API position response dict

    Returns:
        {
            'valid': bool (True only if all validations pass),
            'position': Dict if valid, None if validation failed,
            'errors': List[str] with error messages, empty list if valid
        }
    """
    validators = get_validators()
    result = validators.validate("alpaca_position", position_data, context="alpaca_position")

    # Explicit: Only return data when validation passes
    return {
        "valid": result.is_valid,
        "position": result.data if result.is_valid else None,
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
