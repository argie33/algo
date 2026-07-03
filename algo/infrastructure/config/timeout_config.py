#!/usr/bin/env python3
"""Timeout configuration for all API/database/subprocess operations.

Manages timeout values for:
- HTTP APIs (Alpaca, FRED, market data)
- Database connections
- Webhook handlers
- Subprocess operations
- Loader operations
- Market data fetches

All values read from environment variables or algo_config database table.
Provides fail-safe defaults to prevent indefinite hangs.
"""

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

logger = logging.getLogger(__name__)


class TimeoutConfig:
    """Configuration for all timeout values (APIs, databases, processes)."""

    def __init__(self, parent: "AlgoConfig") -> None:
        """Initialize TimeoutConfig with parent AlgoConfig.

        Args:
            parent: Parent AlgoConfig instance (holds _config dict and DB connection)
        """
        self.parent = parent

    def get(self, key: str, default: Any = None) -> Any:
        """Get timeout configuration value.

        Delegates to parent AlgoConfig.get(), which handles:
        - Database lookup
        - Fallback to defaults
        - Type validation

        Args:
            key: Configuration key
            default: Default value if key missing

        Returns:
            Configuration value or default
        """
        return self.parent.get(key, default)

    def set(
        self,
        key: str,
        value: Any,
        value_type: str,
        description: str = "",
        changed_by: str = "system",
    ) -> bool:
        """Set timeout configuration value (writes to DB).

        Args:
            key: Configuration key
            value: New value (must be positive integer for timeout values)
            value_type: Type ('int')
            description: Description
            changed_by: Actor making change

        Returns:
            True if value was set; False if rejected
        """
        return self.parent.set(key, value, value_type, description, changed_by)

    def get_api_timeout(self) -> int:
        """Get API request timeout in seconds.

        CRITICAL: Must be explicitly configured or provided via environment variable.

        Checks (in order):
        1. API_TIMEOUT environment variable
        2. algo_config DB table (api_request_timeout_seconds)

        Returns:
            Timeout in seconds

        Raises:
            RuntimeError: If neither env var nor config key is set (fail-fast)
        """
        env_val = os.getenv("API_TIMEOUT")
        if env_val:
            return int(env_val)
        timeout = self.get("api_request_timeout_seconds")
        if timeout is None:
            raise RuntimeError(
                "[TIMEOUT_CONFIG] CRITICAL: api_request_timeout_seconds config key missing. "
                "API timeout must be explicitly configured via environment variable (API_TIMEOUT) "
                "or algo_config table (api_request_timeout_seconds). "
                "Set one of: export API_TIMEOUT=5 OR UPDATE algo_config SET value = '5' WHERE key = 'api_request_timeout_seconds';"
            )
        timeout_int = int(timeout)
        if timeout_int <= 0:
            raise RuntimeError(
                f"[TIMEOUT_CONFIG] CRITICAL: api_request_timeout_seconds must be positive (got {timeout_int}). "
                f"Update algo_config: UPDATE algo_config SET value = '5' WHERE key = 'api_request_timeout_seconds';"
            )
        return timeout_int

    def get_db_timeout(self) -> int:
        """Get database connection timeout in seconds.

        CRITICAL: Must be explicitly configured or provided via environment variable.

        Note: RDS Proxy adds additional latency (connection pooling).

        Checks (in order):
        1. DB_TIMEOUT_SECONDS environment variable
        2. algo_config DB table (db_connection_timeout_seconds)

        Returns:
            Timeout in seconds

        Raises:
            RuntimeError: If neither env var nor config key is set (fail-fast)
        """
        env_val = os.getenv("DB_TIMEOUT_SECONDS")
        if env_val:
            return int(env_val)
        timeout = self.get("db_connection_timeout_seconds")
        if timeout is None:
            raise RuntimeError(
                "[TIMEOUT_CONFIG] CRITICAL: db_connection_timeout_seconds config key missing. "
                "Database timeout must be explicitly configured via environment variable (DB_TIMEOUT_SECONDS) "
                "or algo_config table (db_connection_timeout_seconds). "
                "Set one of: export DB_TIMEOUT_SECONDS=15 OR UPDATE algo_config SET value = '15' WHERE key = 'db_connection_timeout_seconds';"
            )
        timeout_int = int(timeout)
        if timeout_int <= 0:
            raise RuntimeError(
                f"[TIMEOUT_CONFIG] CRITICAL: db_connection_timeout_seconds must be positive (got {timeout_int}). "
                f"Update algo_config: UPDATE algo_config SET value = '15' WHERE key = 'db_connection_timeout_seconds';"
            )
        return timeout_int

    def get_market_data_timeout(self) -> int:
        """Get market data API timeout in seconds.

        Checks (in order):
        1. MARKET_DATA_TIMEOUT environment variable
        2. Default: 10 seconds

        Returns:
            Timeout in seconds
        """
        return int(os.getenv("MARKET_DATA_TIMEOUT", "10"))

    def get_alpaca_timeout(self) -> int:
        """Get Alpaca API timeout in seconds.

        Checks (in order):
        1. ALPACA_TIMEOUT environment variable
        2. Default: 5 seconds

        Returns:
            Timeout in seconds
        """
        return int(os.getenv("ALPACA_TIMEOUT", "5"))

    def get_webhook_timeout(self) -> int:
        """Get webhook handler timeout in seconds.

        Checks (in order):
        1. WEBHOOK_TIMEOUT environment variable
        2. Default: 5 seconds

        Returns:
            Timeout in seconds
        """
        return int(os.getenv("WEBHOOK_TIMEOUT", "5"))

    def get_subprocess_timeout(self) -> int:
        """Get subprocess operation timeout in seconds.

        Checks (in order):
        1. SUBPROCESS_TIMEOUT environment variable
        2. Default: 60 seconds

        Returns:
            Timeout in seconds
        """
        return int(os.getenv("SUBPROCESS_TIMEOUT", "60"))

    def get_loader_timeout(self) -> int:
        """Get loader operation timeout in seconds.

        CRITICAL: Must be explicitly configured or provided via environment variable.

        Used for data loading operations that may take longer than typical API calls.

        Checks (in order):
        1. LOADER_TIMEOUT environment variable
        2. algo_config DB table (loader_timeout_seconds)

        Returns:
            Timeout in seconds

        Raises:
            RuntimeError: If neither env var nor config key is set (fail-fast)
        """
        env_val = os.getenv("LOADER_TIMEOUT")
        if env_val:
            return int(env_val)
        timeout = self.get("loader_timeout_seconds")
        if timeout is None:
            raise RuntimeError(
                "[TIMEOUT_CONFIG] CRITICAL: loader_timeout_seconds config key missing. "
                "Loader timeout must be explicitly configured via environment variable (LOADER_TIMEOUT) "
                "or algo_config table (loader_timeout_seconds). "
                "Set one of: export LOADER_TIMEOUT=300 OR UPDATE algo_config SET value = '300' WHERE key = 'loader_timeout_seconds';"
            )
        timeout_int = int(timeout)
        if timeout_int <= 0:
            raise RuntimeError(
                f"[TIMEOUT_CONFIG] CRITICAL: loader_timeout_seconds must be positive (got {timeout_int}). "
                f"Update algo_config: UPDATE algo_config SET value = '300' WHERE key = 'loader_timeout_seconds';"
            )
        return timeout_int

    def get_all_timeouts(self) -> dict[str, int]:
        """Get all timeout values for debugging/logging.

        Returns:
            {
                "api": 5,
                "db": 15,
                "market_data": 10,
                "alpaca": 5,
                "webhook": 5,
                "subprocess": 60,
                "loader": 300,
            }
        """
        return {
            "api": self.get_api_timeout(),
            "db": self.get_db_timeout(),
            "market_data": self.get_market_data_timeout(),
            "alpaca": self.get_alpaca_timeout(),
            "webhook": self.get_webhook_timeout(),
            "subprocess": self.get_subprocess_timeout(),
            "loader": self.get_loader_timeout(),
        }

    def __repr__(self) -> str:
        return f"<TimeoutConfig {len(self.get_all_timeouts())} timeout values>"
