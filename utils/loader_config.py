"""
Dynamic Loader Configuration Manager

ISSUE #7 FIX: Adaptive per-loader parallelism based on RDS load.
Reads loader configuration (parallelism, enabled status) from DynamoDB with in-memory cache.
Falls back to environment variables if DynamoDB is unavailable.
Automatically adjusts parallelism based on RDS connection pool saturation and per-loader constraints.

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
    """Thread-safe dynamic loader configuration manager with RDS-aware adaptive parallelism.

    ISSUE #7 FIX: Adaptive per-loader parallelism based on RDS load.
    - Measures RDS connection pool saturation at runtime
    - Adjusts parallelism dynamically per loader with per-loader constraints
    - Respects per-loader min/max bounds (e.g., stock_prices_daily: min=1, max=3)
    """

    # Class-level cache (shared across all instances)
    _cache: Dict[str, Dict[str, Any]] = {}
    _cache_lock = threading.Lock()
    _cache_timestamp = 0
    _cache_ttl_seconds = 300  # 5-minute cache TTL

    # Per-loader parallelism constraints: (min, max) to prevent rate limiting or RDS exhaustion
    LOADER_CONSTRAINTS = {
        "stock_prices_daily": (1, 3),      # Locked at 1 due to yfinance 429 rate limiting; can go to 3 if RDS allows
        "technical_data_daily": (1, 8),    # Can scale up if RDS available
        "buy_sell_daily": (1, 6),          # Critical path, scale cautiously
        "signal_quality_scores": (1, 6),   # Critical path
        "swing_trader_scores": (1, 6),     # Critical path
        # Analytics loaders can scale higher
        "company_profile": (1, 8),
        "analyst_sentiment": (1, 8),
        "stability_metrics": (1, 8),
        "value_metrics": (1, 8),
        "growth_metrics": (1, 8),
        "quality_metrics": (1, 8),
    }

    def __init__(self):
        """Initialize the configuration manager."""
        self.config_table = os.getenv(
            "LOADER_CONFIG_TABLE",
            f"{os.getenv('PROJECT_NAME', 'algo')}-loader-config-{os.getenv('ENVIRONMENT', 'dev')}"
        )
        self._dynamodb_available = None
        self._rds_connection_cache = None
        self._rds_connection_cache_time = 0
        self._rds_cache_ttl = 30  # Cache RDS metrics for 30 seconds

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

    def _get_rds_connection_count(self) -> Optional[int]:
        """Get current RDS active connection count from CloudWatch metrics (cached).

        Returns:
            Current active connections or None if unavailable.
        """
        now = time.time()
        if self._rds_connection_cache is not None and (now - self._rds_connection_cache_time) < self._rds_cache_ttl:
            return self._rds_connection_cache

        try:
            import boto3
            from datetime import datetime, timedelta

            cloudwatch = boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION", "us-east-1"))
            response = cloudwatch.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName="DatabaseConnections",
                Dimensions=[{"Name": "DBInstanceIdentifier", "Value": "algo-db"}],
                StartTime=datetime.utcnow() - timedelta(minutes=5),
                EndTime=datetime.utcnow(),
                Period=60,
                Statistics=["Average"]
            )

            if response["Datapoints"]:
                latest = max(response["Datapoints"], key=lambda x: x["Timestamp"])
                self._rds_connection_cache = int(latest["Average"])
                self._rds_connection_cache_time = now
                return self._rds_connection_cache
        except Exception as e:
            logger.debug(f"Could not fetch RDS connection count: {e}")

        return None

    def _compute_adaptive_parallelism(self, loader_name: str, base_parallelism: int) -> int:
        """Compute adaptive parallelism based on RDS load and per-loader constraints.

        ISSUE #7 FIX: Dynamic parallelism adjustment based on RDS connection pool saturation.
        - If RDS connections > 400 (80% of 500): reduce parallelism by 50%
        - If RDS connections > 450 (90% of 500): reduce to minimum constraint
        - Never exceed per-loader maximum (e.g., stock_prices_daily max=3)
        - Never go below per-loader minimum (e.g., stock_prices_daily min=1)

        Args:
            loader_name: Name of the loader
            base_parallelism: Starting parallelism value (from DynamoDB or env var)

        Returns:
            Adjusted parallelism respecting RDS load and per-loader bounds
        """
        if base_parallelism <= 1:
            return 1

        # Get per-loader constraints
        constraints = self.LOADER_CONSTRAINTS.get(loader_name, (1, 32))
        min_parallelism, max_parallelism = constraints

        # Apply max constraint first
        adjusted = min(base_parallelism, max_parallelism)

        # Check RDS load and reduce if needed
        try:
            conn_count = self._get_rds_connection_count()
            if conn_count is not None:
                max_db_connections = 500
                saturation_high = max_db_connections * 0.90  # 450
                saturation_medium = max_db_connections * 0.80  # 400

                if conn_count > saturation_high:
                    # Extreme saturation: go to minimum safe parallelism
                    adjusted = min_parallelism
                    logger.warning(
                        f"[{loader_name}] RDS saturation HIGH ({conn_count}/{max_db_connections}). "
                        f"Reduced parallelism to minimum {adjusted}"
                    )
                elif conn_count > saturation_medium:
                    # Moderate saturation: reduce by 50% but respect minimum
                    adjusted = max(min_parallelism, adjusted // 2)
                    logger.info(
                        f"[{loader_name}] RDS saturation MEDIUM ({conn_count}/{max_db_connections}). "
                        f"Adjusted parallelism to {adjusted}"
                    )
        except Exception as e:
            logger.debug(f"Adaptive parallelism adjustment failed: {e}")

        # Final constraint enforcement
        return max(min_parallelism, min(adjusted, max_parallelism))

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
        Get adaptive parallelism for a loader.

        ISSUE #7 FIX: Automatic adaptive parallelism based on RDS load.

        Priority:
        1. DynamoDB cached value (if available and fresh) + adaptive RDS adjustment
        2. DynamoDB direct fetch (if available) + adaptive RDS adjustment
        3. Environment variable LOADER_PARALLELISM + adaptive RDS adjustment
        4. Per-loader constraint minimum (e.g., stock_prices_daily min=1)
        5. Default: 1

        The returned value respects:
        - Per-loader minimum/maximum constraints
        - RDS connection pool saturation (if >80%, reduces parallelism)
        - DynamoDB configuration (if set, overrides environment variable)

        Args:
            loader_name: Name of the loader (e.g., "stock_prices_daily")

        Returns:
            Adaptive parallelism value (number of threads)
        """
        # Get base parallelism from cache or config
        base_parallelism = 1

        # Check in-memory cache first
        cached = self._get_cache(loader_name)
        if cached is not None:
            base_parallelism = cached["parallelism"]
            logger.debug(f"Using cached parallelism for {loader_name}: {base_parallelism}")
        # Try DynamoDB if available
        elif self._check_dynamodb_available():
            config = self._get_from_dynamodb(loader_name)
            if config is not None:
                self._set_cache(loader_name, config)
                base_parallelism = config["parallelism"]
                logger.debug(f"Loaded parallelism for {loader_name} from DynamoDB: {base_parallelism}")
        # Fall back to environment variable
        else:
            base_parallelism = int(os.getenv("LOADER_PARALLELISM", "1"))
            logger.debug(f"Using env var parallelism for {loader_name}: {base_parallelism}")

        # Apply adaptive adjustment based on RDS load
        adjusted = self._compute_adaptive_parallelism(loader_name, base_parallelism)

        if adjusted != base_parallelism:
            logger.info(
                f"[{loader_name}] Adaptive parallelism: {base_parallelism} -> {adjusted} "
                f"(RDS-aware, respects constraints)"
            )

        return adjusted

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
    """Get adaptive parallelism for a loader (convenience function)."""
    return get_config_manager().get_parallelism(loader_name)


def is_enabled(loader_name: str) -> bool:
    """Check if a loader is enabled (convenience function)."""
    return get_config_manager().is_enabled(loader_name)


def get_default_parallelism(loader_name: str, fallback: int = 1) -> int:
    """
    Get default adaptive parallelism for argparse-based loaders.

    This is useful for loaders that use argparse with:
        parser.add_argument("--parallelism", type=int, default=get_default_parallelism("loader_name"))

    Args:
        loader_name: Name of the loader
        fallback: Fallback value if DynamoDB/env var not available (default: 1)

    Returns:
        Adaptive parallelism value to use as argparse default
    """
    try:
        return get_parallelism(loader_name)
    except Exception:
        return fallback
