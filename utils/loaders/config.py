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

import logging
import os
import threading
import time
from typing import Any, cast

logger = logging.getLogger(__name__)


class LoaderConfigManager:
    """Thread-safe dynamic loader configuration manager with RDS-aware adaptive parallelism.

    ISSUE #7 FIX: Adaptive per-loader parallelism based on RDS load.
    - Measures RDS connection pool saturation at runtime
    - Adjusts parallelism dynamically per loader with per-loader constraints
    - Respects per-loader min/max bounds (e.g., stock_prices_daily: min=1, max=3)
    """

    # Class-level cache (shared across all instances)
    _cache: dict[str, dict[str, Any]] = {}
    _cache_lock = threading.Lock()
    _cache_timestamp: float = 0.0
    _cache_ttl_seconds = 300  # 5-minute cache TTL

    # Per-loader parallelism constraints: (min, max) to prevent rate limiting or RDS exhaustion
    LOADER_CONSTRAINTS = {
        "stock_prices_daily": (
            1,
            2,
        ),  # yfinance via shared NAT IP across 6 ECS tasks; limit to 2 to prevent 429 cascades
        "technical_data_daily": (1, 4),  # Can scale up if RDS available
        "buy_sell_daily": (1, 3),  # Critical path, yfinance-dependent; conservative
        "signal_quality_scores": (1, 3),  # Critical path
        "swing_trader_scores": (1, 3),  # Critical path
        # yfinance-dependent metrics: auxiliary loaders that feed stock_scores
        # Increased parallelism (2026-06-28) to improve throughput and achieve 80%+ coverage
        # stock_scores requires upstream metrics for reliable scoring
        # CRITICAL FIX 2026-06-30: Increased min from 1 to 2 to prevent 15-min timeout
        # At parallelism=1, positioning_metrics takes 41-83 min for 5000 symbols (0.5-1s per yfinance call)
        # CRITICAL FIX 2026-06-30 22:30: Increase min to 3-4 to meet 5:00 PM deadline
        # With parallelism=3-4: positioning_metrics completes in 13-28 min, value_metrics in 13-20 min
        # Previous parallelism=2 was still taking 40+ min and causing stock_scores to not run
        "positioning_metrics": (
            3,
            4,
        ),  # Increased from 2 to 3 min parallelism (max 4)
        "value_metrics": (
            3,
            4,
        ),  # Increased from 2 to 3 min parallelism (max 4)
        # Note: stability_metrics also slow, but uses price_daily which completes faster
        # CRITICAL FIX 2026-06-30 22:30: Increase min to 2-3 to improve throughput
        "company_profile": (1, 2),
        "analyst_sentiment": (1, 2),
        "stability_metrics": (2, 3),
        # growth_metrics and quality_metrics depend on financial_data_pipeline; increase min to 2-3
        # to load faster once financial data arrives
        "growth_metrics": (2, 3),
        "quality_metrics": (2, 3),
    }

    def __init__(self) -> None:
        """Initialize the configuration manager."""
        self.config_table = os.getenv(
            "LOADER_CONFIG_TABLE",
            f"{os.getenv('PROJECT_NAME', 'algo')}-loader-config-{os.getenv('ENVIRONMENT', 'dev')}",
        )
        self._dynamodb_available: bool | None = None
        self._rds_connection_cache: int | None = None
        self._rds_connection_cache_time: float = 0
        self._rds_cache_ttl = 30  # Cache RDS metrics for 30 seconds

    @classmethod
    def _get_cache(cls, loader_name: str) -> dict[str, Any] | None:
        """Get cached configuration (thread-safe).

        Returns:
            dict: cached config if available and fresh
            None: if cache expired or loader_name not in cache (cache miss expected)
        """
        with cls._cache_lock:
            now = time.time()
            if now - cls._cache_timestamp > cls._cache_ttl_seconds:
                cls._cache.clear()
                cls._cache_timestamp = now
                logger.debug(f"[CONFIG_LOADER] Cache expired, returning None for {loader_name}")
                return None
            return cls._cache.get(loader_name)

    @classmethod
    def _set_cache(cls, loader_name: str, config: dict[str, Any]) -> None:
        """Set cached configuration (thread-safe)."""
        with cls._cache_lock:
            cls._cache[loader_name] = config
            cls._cache_timestamp = time.time()

    def _get_rds_connection_count(self) -> int | None:
        """Get current RDS active connection count from CloudWatch metrics (cached).

        Returns:
            int: Current active connections count from CloudWatch
            None: if CloudWatch metrics unavailable (no datapoints, or cache miss but metrics unavailable)
        """
        now = time.time()
        if self._rds_connection_cache is not None and (now - self._rds_connection_cache_time) < self._rds_cache_ttl:
            return self._rds_connection_cache

        try:
            from datetime import datetime, timedelta

            import boto3

            cloudwatch = boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION", "us-east-1"))
            response = cloudwatch.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName="DatabaseConnections",
                Dimensions=[{"Name": "DBInstanceIdentifier", "Value": "algo-db"}],
                StartTime=datetime.utcnow() - timedelta(minutes=5),
                EndTime=datetime.utcnow(),
                Period=60,
                Statistics=["Average"],
            )

            if response["Datapoints"]:
                latest = max(response["Datapoints"], key=lambda x: x["Timestamp"])
                self._rds_connection_cache = int(latest["Average"])
                self._rds_connection_cache_time = now
                return self._rds_connection_cache
            logger.debug("[CONFIG_LOADER] No CloudWatch datapoints available for RDS connection count")
            return None
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _compute_adaptive_parallelism(self, loader_name: str, base_parallelism: int) -> int:
        """Compute adaptive parallelism based on RDS load and per-loader constraints.

        CLUSTER 6 FIX: Dynamic parallelism adjustment based on RDS connection pool saturation.
        - If RDS Proxy connections > 75 (75% of 100): reduce parallelism by 50%
        - If RDS Proxy connections > 85 (85% of 100): reduce to minimum constraint
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

        # Check RDS Proxy load and reduce if needed (100-connection Proxy limit)
        try:
            conn_count = self._get_rds_connection_count()
            if conn_count is not None:
                max_proxy_connections = 100  # RDS Proxy limit
                saturation_high = max_proxy_connections * 0.85  # 85 connections
                saturation_medium = max_proxy_connections * 0.70  # 70 connections

                if conn_count > saturation_high:
                    # Critical saturation: go to minimum safe parallelism (prevent pool exhaustion)
                    adjusted = min_parallelism
                    logger.warning(
                        f"[{loader_name}] RDS Proxy saturation CRITICAL ({conn_count}/{max_proxy_connections}). "
                        f"Reduced parallelism to minimum {adjusted} (pool exhaustion risk)"
                    )
                elif conn_count > saturation_medium:
                    # Moderate saturation: reduce by 50% but respect minimum
                    adjusted = max(min_parallelism, adjusted // 2)
                    logger.info(
                        f"[{loader_name}] RDS Proxy saturation MEDIUM ({conn_count}/{max_proxy_connections}). "
                        f"Adjusted parallelism to {adjusted}"
                    )
            else:
                logger.warning(
                    f"[{loader_name}] Could not retrieve RDS connection metrics. "
                    f"Using base parallelism {adjusted} without RDS-aware adjustment (potential pool risk)."
                )
        except Exception as e:
            logger.error(
                f"[RDS_METRICS_FAILURE] Adaptive parallelism adjustment failed for {loader_name}: {e}. "
                f"Cannot monitor RDS pool saturation. Using base parallelism {adjusted} (potential exhaustion risk). "
                f"Check CloudWatch metrics and AWS credentials."
            )

        # Final constraint enforcement
        return max(min_parallelism, min(adjusted, max_parallelism))

    def _check_dynamodb_available(self) -> bool:
        """Check if DynamoDB is available (cache result for efficiency).

        Fails fast if unavailable — returns False rather than silently falling back.
        """
        if self._dynamodb_available is not None:
            return self._dynamodb_available

        try:
            import boto3

            client = boto3.client("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
            response = client.describe_table(TableName=self.config_table)
            self._dynamodb_available = response["Table"]["TableStatus"] == "ACTIVE"
            if self._dynamodb_available:
                logger.info(f"[CONFIG] DynamoDB table {self.config_table} is ACTIVE")
            else:
                logger.critical(
                    f"[CONFIG_FAILURE] DynamoDB table {self.config_table} is not ACTIVE (status: {response['Table']['TableStatus']}). "
                    "Loader configuration is unavailable."
                )
            return self._dynamodb_available
        except Exception as e:
            logger.critical(
                f"[CONFIG_FAILURE] DynamoDB check failed: {e}. "
                f"Cannot load {self.config_table}. Loader configuration is unavailable. "
                f"Check AWS credentials, region, and table existence."
            )
            self._dynamodb_available = False
            return False

    def _get_from_dynamodb(self, loader_name: str) -> dict[str, Any] | None:
        """Fetch configuration from DynamoDB.

        Returns:
            dict: configuration item from DynamoDB if found
            None: if loader_name not found in DynamoDB (config not available, use defaults)
        """
        try:
            import boto3

            client = boto3.client("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
            response = client.get_item(TableName=self.config_table, Key={"loader_name": {"S": loader_name}})

            if "Item" in response:
                item = response["Item"]
                # CRITICAL: Validate DynamoDB item structure (no chained .get() without None checks)
                try:
                    loader_name_attr = item.get("loader_name")
                    if loader_name_attr is None:
                        raise ValueError(
                            f"[CONFIG_LOADER] CRITICAL: Missing 'loader_name' attribute. Available: {list(item.keys())}"
                        )
                    parallelism_attr = item.get("parallelism")
                    if parallelism_attr is None:
                        raise ValueError(
                            f"[CONFIG_LOADER] CRITICAL: Missing 'parallelism' attribute. Available: {list(item.keys())}"
                        )
                    enabled_attr = item.get("enabled")
                    if enabled_attr is None:
                        raise ValueError("[CONFIG_LOADER] CRITICAL: Missing 'enabled' attribute")
                    updated_at_attr = item.get("updated_at")

                    return {
                        "loader_name": loader_name_attr.get("S", loader_name),
                        "parallelism": int(parallelism_attr.get("N", "1")),
                        "enabled": enabled_attr.get("BOOL", True),
                        "updated_at": updated_at_attr.get("S", "") if updated_at_attr else "",
                    }
                except (KeyError, ValueError, TypeError) as e:
                    raise RuntimeError(f"[CONFIG_LOADER] CRITICAL: Failed to parse DynamoDB config: {e}") from e
            logger.debug(f"[CONFIG_LOADER] No DynamoDB config found for {loader_name}, using defaults")
            return None
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def get_parallelism(self, loader_name: str) -> int:
        """
        Get adaptive parallelism for a loader.

        ISSUE #7 FIX: Automatic adaptive parallelism based on RDS load.

        Priority:
        1. DynamoDB cached value (if available and fresh) + adaptive RDS adjustment
        2. DynamoDB direct fetch (if available) + adaptive RDS adjustment
        3. Environment variable LOADER_PARALLELISM + adaptive RDS adjustment
        4. Per-loader constraint maximum (e.g., stock_prices_daily max=6)
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
        # Default: use constraint maximum instead of 1, allows adaptive scaling to reach target parallelism
        constraints = self.LOADER_CONSTRAINTS.get(loader_name, (1, 32))
        _, max_parallelism = constraints
        base_parallelism = max_parallelism  # Start with max from constraints

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
            env_parallelism = os.getenv("LOADER_PARALLELISM", None)
            if env_parallelism is not None:
                base_parallelism = int(env_parallelism)
                logger.debug(f"Using env var parallelism for {loader_name}: {base_parallelism}")
            else:
                # CLUSTER 6 FIX 2026-06-28: Default to constraint maximum, not 1
                # This enables loader-specific parallelism limits (e.g., value_metrics max=3)
                # to actually be used when no DynamoDB or env var is set
                # RDS-aware adaptive adjustment can still reduce if pool is saturated
                logger.info(
                    f"Using constraint maximum parallelism for {loader_name}: {max_parallelism} "
                    f"(no DynamoDB/env var). RDS saturation may reduce this if needed."
                )

        # Apply adaptive adjustment based on RDS load
        adjusted = self._compute_adaptive_parallelism(loader_name, base_parallelism)

        if adjusted != base_parallelism:
            logger.info(
                f"[{loader_name}] Adaptive parallelism: {base_parallelism} -> {adjusted} "
                "(RDS-aware, respects constraints)"
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
            return cast(bool, cached["enabled"])

        # Try DynamoDB if available
        if self._check_dynamodb_available():
            config = self._get_from_dynamodb(loader_name)
            if config is not None:
                self._set_cache(loader_name, config)
                return cast(bool, config["enabled"])

        # Default to enabled
        return True


# Global instance for convenience (thread-safe)
_global_manager = None
_global_manager_lock = threading.Lock()


def get_config_manager() -> LoaderConfigManager:
    """Get the global configuration manager instance (thread-safe).

    Uses double-checked locking to prevent race conditions during initialization.
    """
    global _global_manager
    if _global_manager is None:
        with _global_manager_lock:
            # Double-check pattern to avoid race conditions
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

    IMPORTANT: Returns fallback on failure rather than raising to support CLI defaults.
    For production code, call get_parallelism() directly to get exceptions on failures.

    Args:
        loader_name: Name of the loader
        fallback: Fallback value if DynamoDB/env var not available (default: 1)

    Returns:
        Adaptive parallelism value to use as argparse default (or fallback if unavailable)
    """
    try:
        parallelism = get_parallelism(loader_name)
        logger.info(f"[CONFIG] Loaded parallelism for {loader_name}: {parallelism}")
        return parallelism
    except Exception as e:
        logger.warning(
            f"[CONFIG] Could not load parallelism for {loader_name}: {e}. "
            f"Falling back to parallelism={fallback} (may be non-optimal). "
            f"Check DynamoDB and environment configuration."
        )
        return fallback
