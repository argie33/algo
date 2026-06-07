"""
Dynamic Loader Configuration Manager

Reads loader configuration (parallelism, enabled status) from DynamoDB with in-memory cache.
Falls back to environment variables if DynamoDB is unavailable.

Environment Variables:
  LOADER_CONFIG_TABLE: DynamoDB table name (default: "{project}-loader-config-{environment}")
  LOADER_PARALLELISM: Fallback parallelism if DynamoDB unavailable (default: "1")
"""

import json
import logging
import os
import threading
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class LoaderConfigManager:
    """Thread-safe dynamic loader configuration manager with in-memory cache."""

    # Class-level cache (shared across all instances)
    _cache: Dict[str, Dict[str, Any]] = {}
    _cache_lock = threading.Lock()
    _cache_timestamp = 0
    _cache_ttl_seconds = 300  # 5-minute cache TTL

    def __init__(self):
        """Initialize the configuration manager."""
        self.config_table = os.getenv(
            "LOADER_CONFIG_TABLE",
            f"{os.getenv('PROJECT_NAME', 'algo')}-loader-config-{os.getenv('ENVIRONMENT', 'dev')}"
        )
        self._dynamodb_available = None

    @classmethod
    def _get_cache(cls, loader_name: str) -> Optional[Dict[str, Any]]:
        """Get cached configuration (thread-safe)."""
        with cls._cache_lock:
            now = time.time()
            if now - cls._cache_timestamp > cls._cache_ttl_seconds:
                cls._cache.clear()
                cls._cache_timestamp = now
                return None
            return cls._cache.get(loader_name)

    @classmethod
    def _set_cache(cls, loader_name: str, config: Dict[str, Any]):
        """Set cached configuration (thread-safe)."""
        with cls._cache_lock:
            cls._cache[loader_name] = config
            cls._cache_timestamp = time.time()

    def _check_dynamodb_available(self) -> bool:
        """Check if DynamoDB is available (cache result for efficiency)."""
        if self._dynamodb_available is not None:
            return self._dynamodb_available

        try:
            import boto3
            client = boto3.client("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
            response = client.describe_table(TableName=self.config_table)
            self._dynamodb_available = response["Table"]["TableStatus"] == "ACTIVE"
            return self._dynamodb_available
        except Exception as e:
            logger.debug(f"DynamoDB check failed: {e}")
            self._dynamodb_available = False
            return False

    def _get_from_dynamodb(self, loader_name: str) -> Optional[Dict[str, Any]]:
        """Fetch configuration from DynamoDB."""
        try:
            import boto3
            client = boto3.client("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
            response = client.get_item(
                TableName=self.config_table,
                Key={"loader_name": {"S": loader_name}}
            )

            if "Item" in response:
                item = response["Item"]
                return {
                    "loader_name": item.get("loader_name", {}).get("S", loader_name),
                    "parallelism": int(item.get("parallelism", {}).get("N", "1")),
                    "enabled": item.get("enabled", {}).get("BOOL", True),
                    "updated_at": item.get("updated_at", {}).get("S", ""),
                }
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch config for {loader_name} from DynamoDB: {e}")
            return None

    def get_parallelism(self, loader_name: str) -> int:
        """
        Get parallelism for a loader.

        Priority:
        1. DynamoDB cached value (if available and fresh)
        2. DynamoDB direct fetch (if available)
        3. Environment variable LOADER_PARALLELISM
        4. Default: 1

        Args:
            loader_name: Name of the loader (e.g., "stock_prices_daily")

        Returns:
            Parallelism value (number of threads)
        """
        # Check in-memory cache first
        cached = self._get_cache(loader_name)
        if cached is not None:
            logger.debug(f"Using cached parallelism for {loader_name}: {cached['parallelism']}")
            return cached["parallelism"]

        # Try DynamoDB if available
        if self._check_dynamodb_available():
            config = self._get_from_dynamodb(loader_name)
            if config is not None:
                self._set_cache(loader_name, config)
                logger.info(f"Loaded parallelism for {loader_name} from DynamoDB: {config['parallelism']}")
                return config["parallelism"]

        # Fall back to environment variable
        default_parallelism = int(os.getenv("LOADER_PARALLELISM", "1"))
        logger.info(f"Using env var parallelism for {loader_name}: {default_parallelism}")
        return default_parallelism

    def is_enabled(self, loader_name: str) -> bool:
        """
        Check if a loader is enabled.

        Priority:
        1. DynamoDB value (if available)
        2. Default: True

        Args:
            loader_name: Name of the loader

        Returns:
            True if loader is enabled, False otherwise
        """
        # Check in-memory cache first
        cached = self._get_cache(loader_name)
        if cached is not None:
            return cached["enabled"]

        # Try DynamoDB if available
        if self._check_dynamodb_available():
            config = self._get_from_dynamodb(loader_name)
            if config is not None:
                self._set_cache(loader_name, config)
                return config["enabled"]

        # Default to enabled
        return True


# Global instance for convenience
_global_manager = None


def get_config_manager() -> LoaderConfigManager:
    """Get the global configuration manager instance."""
    global _global_manager
    if _global_manager is None:
        _global_manager = LoaderConfigManager()
    return _global_manager


def get_parallelism(loader_name: str) -> int:
    """Get parallelism for a loader (convenience function)."""
    return get_config_manager().get_parallelism(loader_name)


def is_enabled(loader_name: str) -> bool:
    """Check if a loader is enabled (convenience function)."""
    return get_config_manager().is_enabled(loader_name)


def get_default_parallelism(loader_name: str, fallback: int = 1) -> int:
    """
    Get default parallelism for argparse-based loaders.

    This is useful for loaders that use argparse with:
        parser.add_argument("--parallelism", type=int, default=get_default_parallelism("loader_name"))

    Args:
        loader_name: Name of the loader
        fallback: Fallback value if DynamoDB/env var not available (default: 1)

    Returns:
        Parallelism value to use as argparse default
    """
    try:
        return get_parallelism(loader_name)
    except Exception:
        return fallback
