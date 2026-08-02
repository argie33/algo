#!/usr/bin/env python3
"""Centralized configuration validation for orchestrator phases.

Enforces consistent config value access across all phases, preventing silent None values
and type mismatches. Each phase calls validate_phase_config() at entry to ensure all
required configuration keys are present and properly typed.
"""

from typing import Any


class ConfigValidationError(Exception):
    """Raised when phase configuration is invalid or incomplete."""


def validate_phase_config(config: Any, phase_name: str) -> None:
    """Validate that all required config keys are present before phase execution.

    Args:
        config: Configuration object passed to phase
        phase_name: Name of phase being validated (for error messages)

    Raises:
        ConfigValidationError: If any required config is missing or invalid
    """
    if config is None:
        raise ConfigValidationError(f"[{phase_name}] config is None - no configuration available")

    # Required keys used by ALL phases
    required_keys = {
        "execution_mode": str,  # Must be 'paper', 'review', 'live', or 'auto'
    }

    # Validate each required key
    for key, expected_type in required_keys.items():
        value = config.get(key)
        if value is None:
            raise ConfigValidationError(
                f"[{phase_name}] config['{key}'] is None - required configuration missing. "
                f"Check that orchestrator passes complete config dict to phase."
            )

        if not isinstance(value, expected_type):
            raise ConfigValidationError(
                f"[{phase_name}] config['{key}'] is {type(value).__name__}, expected {expected_type.__name__}. "
                f"Type mismatch in configuration."
            )

    # Validate execution_mode is in valid set
    execution_mode = config.get("execution_mode")
    valid_modes = {"paper", "review", "live", "auto"}
    if execution_mode not in valid_modes:
        raise ConfigValidationError(
            f"[{phase_name}] execution_mode='{execution_mode}' is invalid. "
            f"Must be one of: {valid_modes}"
        )


def get_config_str(config: Any, key: str, phase_name: str = "phase") -> str:
    """Get a required string config value with error checking.

    Args:
        config: Configuration object
        key: Config key to retrieve
        phase_name: Name of phase for error messages

    Returns:
        String value from config

    Raises:
        ConfigValidationError: If key is missing or not a string
    """
    value = config.get(key)
    if value is None:
        raise ConfigValidationError(
            f"[{phase_name}] config['{key}'] is None - required string config missing"
        )
    if not isinstance(value, str):
        raise ConfigValidationError(
            f"[{phase_name}] config['{key}'] is {type(value).__name__}, expected str"
        )
    return value


def get_config_int(config: Any, key: str, phase_name: str = "phase", default: int | None = None) -> int:
    """Get an integer config value with error checking.

    Args:
        config: Configuration object
        key: Config key to retrieve
        phase_name: Name of phase for error messages
        default: Default value if key is missing

    Returns:
        Integer value from config

    Raises:
        ConfigValidationError: If key is missing (and no default) or not an integer
    """
    value = config.get(key)
    if value is None:
        if default is not None:
            return default
        raise ConfigValidationError(
            f"[{phase_name}] config['{key}'] is None - required integer config missing"
        )
    if not isinstance(value, int):
        raise ConfigValidationError(
            f"[{phase_name}] config['{key}'] is {type(value).__name__}, expected int"
        )
    return value


def get_config_float(config: Any, key: str, phase_name: str = "phase", default: float | None = None) -> float:
    """Get a float config value with error checking.

    Args:
        config: Configuration object
        key: Config key to retrieve
        phase_name: Name of phase for error messages
        default: Default value if key is missing

    Returns:
        Float value from config

    Raises:
        ConfigValidationError: If key is missing (and no default) or not a number
    """
    value = config.get(key)
    if value is None:
        if default is not None:
            return default
        raise ConfigValidationError(
            f"[{phase_name}] config['{key}'] is None - required float config missing"
        )
    if not isinstance(value, (int, float)):
        raise ConfigValidationError(
            f"[{phase_name}] config['{key}'] is {type(value).__name__}, expected int or float"
        )
    return float(value)


def get_config_bool(config: Any, key: str, phase_name: str = "phase", default: bool | None = None) -> bool:
    """Get a boolean config value with error checking.

    Args:
        config: Configuration object
        key: Config key to retrieve
        phase_name: Name of phase for error messages
        default: Default value if key is missing

    Returns:
        Boolean value from config

    Raises:
        ConfigValidationError: If key is missing (and no default) or not a boolean
    """
    value = config.get(key)
    if value is None:
        if default is not None:
            return default
        raise ConfigValidationError(
            f"[{phase_name}] config['{key}'] is None - required boolean config missing"
        )
    if not isinstance(value, bool):
        raise ConfigValidationError(
            f"[{phase_name}] config['{key}'] is {type(value).__name__}, expected bool"
        )
    return value
