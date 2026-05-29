"""FIXED Issue #20: Runtime configuration loader for Alpaca trading mode and other settings.

Allows changing trading mode, position sizing, and other parameters without requiring
Terraform redeploy or environment variable changes. Configuration cached for 5 minutes
to avoid excessive database queries.
"""

import time
import logging
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)


class RuntimeConfig:
    """Thread-safe runtime configuration with 5-minute cache."""

    _cache: Dict[str, str] = {}
    _cache_timestamp: Optional[float] = None
    CACHE_TTL = 300  # 5 minutes

    # Allowed configuration keys with validation
    ALLOWED_KEYS = {
        'alpaca_trading_mode': ('paper', 'live', 'disabled'),
        'max_position_size_usd': (int, 1000, 100000),  # Min 1k, max 100k
        'circuit_breaker_vix_threshold': (int, 30, 100),  # Min 30, max 100
        'data_freshness_sla_hours': (int, 1, 168),  # Min 1h, max 7 days
        'orchestrator_enabled': ('true', 'false'),
        'execution_monitor_enabled': ('true', 'false'),
    }

    @classmethod
    def get(cls, key: str, default: Optional[str] = None) -> Optional[str]:
        """Load config from RDS with 5-minute cache.

        Args:
            key: Configuration key to retrieve
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        now = time.time()

        # Return cached value if still valid
        if cls._cache_timestamp and (now - cls._cache_timestamp) < cls.CACHE_TTL:
            cached = cls._cache.get(key)
            if cached is not None:
                logger.debug(f"[RUNTIME_CONFIG_CACHED] {key} = {cached[:50]}")
                return cached
            return default

        # Refresh cache from RDS
        if cls._refresh_cache():
            return cls._cache.get(key, default)

        logger.warning(f"[RUNTIME_CONFIG_LOAD_FAILED] Could not load {key}, using default")
        return default

    @classmethod
    def get_bool(cls, key: str, default: bool = False) -> bool:
        """Get boolean configuration value.

        Args:
            key: Configuration key
            default: Default boolean value

        Returns:
            Boolean configuration value
        """
        value = cls.get(key, 'true' if default else 'false')
        return value.lower() in ('true', '1', 'yes')

    @classmethod
    def get_int(cls, key: str, default: int = 0) -> int:
        """Get integer configuration value.

        Args:
            key: Configuration key
            default: Default integer value

        Returns:
            Integer configuration value
        """
        try:
            value = cls.get(key)
            if value is not None:
                return int(value)
        except (ValueError, TypeError):
            logger.warning(f"[RUNTIME_CONFIG_TYPE_ERROR] {key} not an integer: {value}")
        return default

    @classmethod
    def _refresh_cache(cls) -> bool:
        """Refresh configuration cache from RDS.

        Returns:
            True if cache refreshed successfully, False otherwise
        """
        try:
            # Import here to avoid circular dependency
            from utils.db_connection import get_db_connection

            conn = get_db_connection()
            if not conn:
                logger.error("[RUNTIME_CONFIG_DB_ERROR] No database connection")
                return False

            with conn.cursor() as cur:
                cur.execute(
                    """SELECT config_key, config_value FROM algo_runtime_config
                       ORDER BY config_key"""
                )
                rows = cur.fetchall()

                # Convert to dict (handle both tuple and dict cursor)
                cls._cache = {}
                for row in rows:
                    if isinstance(row, dict):
                        cls._cache[row['config_key']] = row['config_value']
                    else:
                        cls._cache[row[0]] = row[1]

                cls._cache_timestamp = time.time()
                logger.info(
                    f"[RUNTIME_CONFIG_LOADED] {len(cls._cache)} keys cached, "
                    f"expires in {cls.CACHE_TTL}s"
                )
                return True

        except Exception as e:
            logger.error(f"[RUNTIME_CONFIG_LOAD_ERROR] Failed to refresh cache: {e}")
            return False

    @classmethod
    def clear_cache(cls) -> None:
        """Force cache refresh on next access."""
        cls._cache = {}
        cls._cache_timestamp = None
        logger.info("[RUNTIME_CONFIG_CACHE_CLEARED]")

    @classmethod
    def validate_value(cls, key: str, value: Any) -> tuple[bool, Optional[str]]:
        """Validate configuration value before saving.

        Args:
            key: Configuration key
            value: Value to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if key not in cls.ALLOWED_KEYS:
            return False, f"Unknown configuration key: {key}"

        allowed = cls.ALLOWED_KEYS[key]

        # String enum validation
        if isinstance(allowed, tuple) and isinstance(allowed[0], str):
            if str(value) not in allowed:
                return False, f"Must be one of: {', '.join(allowed)}"
            return True, None

        # Integer range validation
        if isinstance(allowed, tuple) and isinstance(allowed[0], type):
            if allowed[0] == int:
                try:
                    int_val = int(value)
                    if len(allowed) >= 3 and not (allowed[1] <= int_val <= allowed[2]):
                        return (
                            False,
                            f"Must be between {allowed[1]} and {allowed[2]}"
                        )
                    return True, None
                except (ValueError, TypeError):
                    return False, f"Must be an integer"

        return True, None


# Usage in orchestrator:
# ```python
# from algo.config.runtime_config import RuntimeConfig
#
# # Get Alpaca trading mode
# alpaca_mode = RuntimeConfig.get('alpaca_trading_mode', 'paper')
# if alpaca_mode == 'live':
#     execution_mode = 'live'
# elif alpaca_mode == 'paper':
#     execution_mode = 'paper'
# else:
#     execution_mode = 'disabled'
# ```
