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
        1. algo_config DB table (api_request_timeout_seconds) — PRIMARY
        2. API_TIMEOUT environment variable — OVERRIDE ONLY

        Returns:
            Timeout in seconds

        Raises:
            RuntimeError: If neither database nor env var is set (fail-fast)
        """
        timeout = self.get("api_request_timeout_seconds")
        if timeout is not None:
            timeout_int = int(timeout)
            if timeout_int <= 0:
                raise RuntimeError(
                    f"[TIMEOUT_CONFIG] CRITICAL: api_request_timeout_seconds must be positive (got {timeout_int}). "
                    f"Update algo_config: UPDATE algo_config SET value = '5' WHERE key = 'api_request_timeout_seconds';"
                )
            return timeout_int
        env_val = os.getenv("API_TIMEOUT")
        if env_val:
            env_int = int(env_val)
            if env_int <= 0:
                raise RuntimeError(
                    f"[TIMEOUT_CONFIG] CRITICAL: API_TIMEOUT must be positive (got {env_int}). "
                    f"Set: export API_TIMEOUT=5"
                )
            logger.info("[TIMEOUT_CONFIG] Using API_TIMEOUT from environment variable (database value empty)")
            return env_int
        raise RuntimeError(
            "[TIMEOUT_CONFIG] CRITICAL: api_request_timeout_seconds config key missing. "
            "API timeout must be explicitly configured via algo_config table (api_request_timeout_seconds). "
            "Set: UPDATE algo_config SET value = '5' WHERE key = 'api_request_timeout_seconds';"
        )

    def get_db_timeout(self) -> int:
        """Get database connection timeout in seconds.

        CRITICAL: Must be explicitly configured or provided via environment variable.

        Note: RDS Proxy adds additional latency (connection pooling).

        Checks (in order):
        1. algo_config DB table (db_connection_timeout_seconds) — PRIMARY
        2. DB_TIMEOUT_SECONDS environment variable — OVERRIDE ONLY

        Returns:
            Timeout in seconds

        Raises:
            RuntimeError: If neither database nor env var is set (fail-fast)
        """
        timeout = self.get("db_connection_timeout_seconds")
        if timeout is not None:
            timeout_int = int(timeout)
            if timeout_int <= 0:
                raise RuntimeError(
                    f"[TIMEOUT_CONFIG] CRITICAL: db_connection_timeout_seconds must be positive (got {timeout_int}). "
                    f"Update algo_config: UPDATE algo_config SET value = '15' WHERE key = 'db_connection_timeout_seconds';"
                )
            return timeout_int
        env_val = os.getenv("DB_TIMEOUT_SECONDS")
        if env_val:
            env_int = int(env_val)
            if env_int <= 0:
                raise RuntimeError(
                    f"[TIMEOUT_CONFIG] CRITICAL: DB_TIMEOUT_SECONDS must be positive (got {env_int}). "
                    f"Set: export DB_TIMEOUT_SECONDS=15"
                )
            logger.info("[TIMEOUT_CONFIG] Using DB_TIMEOUT_SECONDS from environment variable (database value empty)")
            return env_int
        raise RuntimeError(
            "[TIMEOUT_CONFIG] CRITICAL: db_connection_timeout_seconds config key missing. "
            "Database timeout must be explicitly configured via algo_config table (db_connection_timeout_seconds). "
            "Set: UPDATE algo_config SET value = '15' WHERE key = 'db_connection_timeout_seconds';"
        )

    def get_market_data_timeout(self) -> int:
        """Get market data API timeout in seconds.

        Checks (in order):
        1. algo_config DB table (market_data_timeout_seconds)
        2. MARKET_DATA_TIMEOUT environment variable
        3. Default: 10 seconds

        Returns:
            Timeout in seconds
        """
        timeout = self.get("market_data_timeout_seconds")
        if timeout is not None:
            return int(timeout)
        env_val = os.getenv("MARKET_DATA_TIMEOUT")
        if env_val:
            return int(env_val)
        return 10

    def get_alpaca_timeout(self) -> int:
        """Get Alpaca API timeout in seconds.

        Checks (in order):
        1. algo_config DB table (alpaca_timeout_seconds)
        2. ALPACA_TIMEOUT environment variable
        3. Default: 5 seconds

        Returns:
            Timeout in seconds
        """
        timeout = self.get("alpaca_timeout_seconds")
        if timeout is not None:
            return int(timeout)
        env_val = os.getenv("ALPACA_TIMEOUT")
        if env_val:
            return int(env_val)
        return 5

    def get_webhook_timeout(self) -> int:
        """Get webhook handler timeout in seconds.

        Checks (in order):
        1. algo_config DB table (webhook_timeout_seconds)
        2. WEBHOOK_TIMEOUT environment variable
        3. Default: 5 seconds

        Returns:
            Timeout in seconds
        """
        timeout = self.get("webhook_timeout_seconds")
        if timeout is not None:
            return int(timeout)
        env_val = os.getenv("WEBHOOK_TIMEOUT")
        if env_val:
            return int(env_val)
        return 5

    def get_subprocess_timeout(self) -> int:
        """Get subprocess operation timeout in seconds.

        Checks (in order):
        1. algo_config DB table (subprocess_timeout_seconds)
        2. SUBPROCESS_TIMEOUT environment variable
        3. Default: 60 seconds

        Returns:
            Timeout in seconds
        """
        timeout = self.get("subprocess_timeout_seconds")
        if timeout is not None:
            return int(timeout)
        env_val = os.getenv("SUBPROCESS_TIMEOUT")
        if env_val:
            return int(env_val)
        return 60

    def get_loader_timeout(self) -> int:
        """Get loader operation timeout in seconds.

        CRITICAL: Must be explicitly configured or provided via environment variable.

        Used for data loading operations that may take longer than typical API calls.

        Checks (in order):
        1. algo_config DB table (loader_timeout_seconds) — PRIMARY
        2. LOADER_TIMEOUT environment variable — OVERRIDE ONLY

        Returns:
            Timeout in seconds

        Raises:
            RuntimeError: If neither database nor env var is set (fail-fast)
        """
        timeout = self.get("loader_timeout_seconds")
        if timeout is not None:
            timeout_int = int(timeout)
            if timeout_int <= 0:
                raise RuntimeError(
                    f"[TIMEOUT_CONFIG] CRITICAL: loader_timeout_seconds must be positive (got {timeout_int}). "
                    f"Update algo_config: UPDATE algo_config SET value = '300' WHERE key = 'loader_timeout_seconds';"
                )
            return timeout_int
        env_val = os.getenv("LOADER_TIMEOUT")
        if env_val:
            env_int = int(env_val)
            if env_int <= 0:
                raise RuntimeError(
                    f"[TIMEOUT_CONFIG] CRITICAL: LOADER_TIMEOUT must be positive (got {env_int}). "
                    f"Set: export LOADER_TIMEOUT=300"
                )
            logger.info("[TIMEOUT_CONFIG] Using LOADER_TIMEOUT from environment variable (database value empty)")
            return env_int
        raise RuntimeError(
            "[TIMEOUT_CONFIG] CRITICAL: loader_timeout_seconds config key missing. "
            "Loader timeout must be explicitly configured via algo_config table (loader_timeout_seconds). "
            "Set: UPDATE algo_config SET value = '300' WHERE key = 'loader_timeout_seconds';"
        )

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
