"""Configuration management for API health checks and data freshness.

All parameters are read from environment variables at Lambda cold start,
with sensible defaults for development and production environments.
"""

import os
import logging
import threading

logger = logging.getLogger(__name__)


class HealthCheckConfig:
    """Configuration for health check endpoints.

    Attributes:
        data_freshness_max_hours: Maximum age (hours) before data is considered stale.
            Default: 24 (1 trading day). Configurable via DATA_FRESHNESS_MAX_HOURS env var.

        signal_stale_threshold_hours: Hours threshold for signal staleness warning.
            Default: 24. Signals older than this are flagged as STALE.

        pipeline_healthy_days: Days threshold for pipeline freshness (HEALTHY status).
            Default: 2. Data older than this gets WARNING status.

        pipeline_critical_days: Days threshold for pipeline freshness (CRITICAL status).
            Default: 7. Data older than this gets CRITICAL status.
    """

    def __init__(self):
        # Data freshness maximum age (hours)
        # This is used by Phase 1 and health endpoints to determine if data is stale
        # For trading systems: normally 24 hours (1 trading day)
        # For non-trading days (weekends, holidays): adjusted in check_data_freshness()
        self.data_freshness_max_hours = self._read_int_env(
            "DATA_FRESHNESS_MAX_HOURS",
            default=24,
            min_val=1,
            max_val=168,  # Max 7 days (1 week)
        )

        # Signal data staleness thresholds (hours)
        # Used in /api/health basic endpoint to categorize signal freshness
        self.signal_stale_threshold_hours = self._read_int_env(
            "SIGNAL_STALE_THRESHOLD_HOURS", default=24, min_val=1, max_val=168
        )

        # Pipeline health check thresholds (days)
        # HEALTHY: data <= X days old
        # STALE: X < data <= Y days old
        # CRITICAL: data > Y days old
        self.pipeline_healthy_days = self._read_int_env(
            "PIPELINE_HEALTHY_DAYS", default=2, min_val=1, max_val=30
        )

        self.pipeline_critical_days = self._read_int_env(
            "PIPELINE_CRITICAL_DAYS", default=7, min_val=1, max_val=30
        )

        # Log configuration at startup (useful for debugging threshold issues)
        logger.info(
            f"[HealthCheckConfig] Loaded: data_freshness_max_hours={self.data_freshness_max_hours}h, "
            f"signal_stale={self.signal_stale_threshold_hours}h, "
            f"pipeline_healthy={self.pipeline_healthy_days}d, pipeline_critical={self.pipeline_critical_days}d"
        )

    def _read_int_env(
        self, key: str, default: int, min_val: int = None, max_val: int = None
    ) -> int:
        """Read integer from environment variable with bounds checking.

        Args:
            key: Environment variable name
            default: Default value if not set
            min_val: Minimum allowed value (inclusive)
            max_val: Maximum allowed value (inclusive)

        Returns:
            Parsed integer value, clamped to [min_val, max_val] if specified
        """
        value_str = os.getenv(key, "").strip()
        if not value_str:
            return default

        try:
            value = int(value_str)

            # Clamp to bounds
            if min_val is not None and value < min_val:
                logger.warning(
                    f"{key}={value} is below minimum {min_val}, using {min_val}"
                )
                return min_val
            if max_val is not None and value > max_val:
                logger.warning(
                    f"{key}={value} exceeds maximum {max_val}, using {max_val}"
                )
                return max_val

            return value
        except ValueError:
            logger.warning(
                f"{key}={value_str} is not a valid integer, using default {default}"
            )
            return default


# Global singleton — initialized at Lambda cold start (thread-safe)
_config = None
_config_lock = threading.Lock()


def get_config() -> HealthCheckConfig:
    """Get the global health check configuration (lazy initialized, thread-safe).

    Returns the same instance on every call (singleton pattern).
    Uses double-checked locking to prevent race conditions during initialization.
    """
    global _config
    if _config is None:
        with _config_lock:
            # Double-check pattern to avoid race conditions
            if _config is None:
                _config = HealthCheckConfig()
    return _config
