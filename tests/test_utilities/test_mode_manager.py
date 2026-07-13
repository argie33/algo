#!/usr/bin/env python3
"""Unified test mode manager - single source of truth for all test mode configuration.

Consolidates test mode detection, validation, and enabling across the codebase.
Provides single entry point: enable_test_mode().
"""

import os
from datetime import datetime, timezone
from typing import Any


def is_test_mode_enabled() -> bool:
    dry_run = os.getenv("ORCHESTRATOR_DRY_RUN", "false").lower() in ("true", "1", "yes")
    test_mode = os.getenv("TEST_MODE_ENABLED", "false").lower() in ("true", "1", "yes")
    return dry_run or test_mode


def is_dev_environment() -> bool:
    """Check if current environment permits test mode.

    Test mode is only valid in development, test, and local environments.
    Returns False for production to prevent accidental test data usage.
    """
    env = os.getenv("ENVIRONMENT", "production").lower()
    return env in ("development", "test", "local")


def get_test_mode_config() -> dict[str, Any]:
    return {
        "test_mode_enabled": is_test_mode_enabled(),
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "orchestrator_dry_run": os.getenv("ORCHESTRATOR_DRY_RUN", "false"),
        "allow_price_seeding": os.getenv("ALLOW_PRICE_SEEDING", "false"),
        "test_mode_enabled_flag": os.getenv("TEST_MODE_ENABLED", "false"),
        "test_mode_activated_at": os.getenv("TEST_MODE_ACTIVATED_AT"),
    }


def validate_test_mode_environment() -> None:
    """Validate that current environment supports test mode.

    Raises:
        RuntimeError: If test mode is enabled but environment is production
    """
    if is_test_mode_enabled() and not is_dev_environment():
        env = os.getenv("ENVIRONMENT", "unknown")
        raise RuntimeError(
            f"[TEST_MODE_INVALID_ENVIRONMENT] Test mode is enabled but ENVIRONMENT={env}. "
            f"Test mode is only valid in development, test, or local environments. "
            f"Set ENVIRONMENT=development or disable test mode flags."
        )


def enable_test_mode(
    mode: str = "dry-run",
    components: list[str] | None = None,
    environment_override: str = "development",
) -> dict[str, Any]:
    """Enable test mode with explicit configuration.

    SINGLE ENTRY POINT for all test mode activation.

    Args:
        mode: Test mode type ('dry-run', 'seed-prices', 'full-test')
        components: List of components to enable test mode for (['reconciliation'], ['prices'], None for all)
        environment_override: Environment to use (default: 'development')

    Returns:
        Dict showing test mode configuration

    Raises:
        RuntimeError: If environment is not development/test/local
    """
    # Validate environment
    if environment_override not in ("development", "test", "local"):
        raise RuntimeError(
            f"Test mode only valid in development environments. "
            f"Got ENVIRONMENT={environment_override}. "
            f"Set to 'development', 'test', or 'local'."
        )

    # Set environment variables
    os.environ["ENVIRONMENT"] = environment_override
    os.environ["TEST_MODE_ENABLED"] = "true"
    os.environ["TEST_MODE_ACTIVATED_AT"] = datetime.now(timezone.utc).isoformat()

    # Set mode-specific flags
    if mode == "dry-run" or "reconciliation" in (components or []):
        os.environ["ORCHESTRATOR_DRY_RUN"] = "true"

    if mode == "seed-prices" or "prices" in (components or []):
        os.environ["ALLOW_PRICE_SEEDING"] = "true"

    return {
        "test_mode_enabled": True,
        "mode": mode,
        "components": components or ["all"],
        "environment": environment_override,
        "activated_at": os.getenv("TEST_MODE_ACTIVATED_AT"),
    }


def mark_mock_data(data: dict[str, Any]) -> dict[str, Any]:
    """Mark data as mock/test data with explicit indicators.

    Args:
        data: Data dict to mark

    Returns:
        Data dict with mock data markers added
    """
    if not isinstance(data, dict):
        raise TypeError(f"mark_mock_data requires dict, got {type(data).__name__}")

    data["_is_mock_data"] = True
    data["_is_testing_only"] = True
    data["_marked_at"] = datetime.now(timezone.utc).isoformat()
    return data


def assert_not_test_data(data: Any, location: str = "unknown") -> None:
    """Assert that data is not mock/test data in production paths.

    Raises:
        RuntimeError: If data contains mock data markers
    """
    if not isinstance(data, dict):
        return  # Only dicts can have markers

    mock_markers = {"_is_mock_data", "_is_testing_only", "_mock_portfolio_value", "_mock_cash"}
    found_markers = [m for m in mock_markers if m in data]

    if found_markers:
        raise RuntimeError(
            f"[MOCK_DATA_IN_PRODUCTION] {location} received mock data. "
            f"Test data must not reach production paths. "
            f"Markers found: {found_markers}. "
            f"Data: {data}"
        )
