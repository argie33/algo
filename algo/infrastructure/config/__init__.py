"""Modular configuration system for AlgoConfig (Phase 1+ refactoring).

Re-exports AlgoConfig and helper functions from main.py for backward compatibility.
"""

from .main import (
    AlgoConfig,
    get_alpaca_base_url,
    get_alpaca_timeout,
    get_api_timeout,
    get_config,
    get_db_timeout,
    get_market_data_timeout,
    get_subprocess_timeout,
    get_webhook_timeout,
    reset_config,
    validate_environment,
)


__all__ = [
    "AlgoConfig",
    "get_alpaca_base_url",
    "get_alpaca_timeout",
    "get_api_timeout",
    "get_config",
    "get_db_timeout",
    "get_market_data_timeout",
    "get_subprocess_timeout",
    "get_webhook_timeout",
    "reset_config",
    "validate_environment",
]
