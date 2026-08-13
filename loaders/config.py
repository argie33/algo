#!/usr/bin/env python3
"""Loader configuration - centralized settings for all loaders.

Provides environment-driven configuration to avoid hardcoded magic numbers:
- max_fail_rate: Maximum percentage of symbols allowed to fail before marking load as failed
- backfill_days: Default number of days to backfill when loading incremental data
- event_history_max: Maximum number of events to store in phase event history
"""

import os


def get_loader_max_fail_rate(loader_type: str = "default") -> float:
    """Get maximum failure rate for a loader type.

    Args:
        loader_type: Type of loader (e.g., "price", "sec", "financial", "default")

    Returns:
        Maximum percentage (0-100) of symbols allowed to fail
    """
    # Loader-specific defaults: price data is critical, but realistic failure rates are higher
    # Session 101 FIX: Increase price max_fail_rate from 5% to 8%
    # Reason: yfinance rate limiting causes exponential backoff; 92-93% is realistic max
    # (delisted/halted symbols ~3-5%, yfinance rate-limit cascades ~3-5% additional)
    defaults = {
        "price": 8.0,  # 8% = ~392 symbols out of 4900 (allows yfinance rate-limit variance)
        "sec": 5.0,  # 5% = more lenient for SEC API which rate-limits
        "financial": 5.0,
        "earnings": 5.0,
        "default": 5.0,
    }

    env_key = f"LOADER_MAX_FAIL_RATE_{loader_type.upper()}"
    env_value = os.getenv(env_key)
    if env_value is not None:
        try:
            return float(env_value)
        except ValueError as e:
            raise ValueError(
                f"CRITICAL: {env_key} value is invalid: {env_value!r}. Must be a valid float between 0-100. {e}"
            ) from e

    return defaults.get(loader_type, defaults["default"])


def get_loader_backfill_days() -> int:
    """Get default backfill days for incremental loaders.

    Returns:
        Number of days to backfill (0 = only today/latest watermark, >0 = backfill N days)
    """
    env_value = os.getenv("LOADER_BACKFILL_DAYS")
    if env_value is not None:
        try:
            return int(env_value)
        except ValueError as e:
            raise ValueError(
                f"CRITICAL: LOADER_BACKFILL_DAYS value is invalid: {env_value!r}. Must be a valid integer >= 0. {e}"
            ) from e

    return 0


def get_phase_event_history_max() -> int:
    """Get maximum number of events to store in phase event history.

    Returns:
        Maximum event count before pruning old events
    """
    env_value = os.getenv("PHASE_EVENT_HISTORY_MAX")
    if env_value is not None:
        try:
            return int(env_value)
        except ValueError as e:
            raise ValueError(
                f"CRITICAL: PHASE_EVENT_HISTORY_MAX value is invalid: {env_value!r}. Must be a valid integer > 0. {e}"
            ) from e

    return 1000  # Default: keep last 1000 events per phase


def get_loader_batch_size() -> int:
    """Get batch size for data loader operations.

    Returns:
        Number of items per batch for optimal loader
    """
    env_value = os.getenv("LOADER_BATCH_SIZE")
    if env_value is not None:
        try:
            return int(env_value)
        except ValueError as e:
            raise ValueError(
                f"CRITICAL: LOADER_BATCH_SIZE value is invalid: {env_value!r}. Must be a valid integer > 0. {e}"
            ) from e

    return 10000  # Default: 10k items per batch


def get_loader_max_backfill_days() -> int:
    """Get maximum backfill window for loaders.

    Returns:
        Maximum number of days that can be backfilled in a single load
    """
    env_value = os.getenv("LOADER_MAX_BACKFILL_DAYS")
    if env_value is not None:
        try:
            return int(env_value)
        except ValueError as e:
            raise ValueError(
                f"CRITICAL: LOADER_MAX_BACKFILL_DAYS value is invalid: {env_value!r}. Must be a valid integer > 0. {e}"
            ) from e

    # Default: read from algo/config which supports environment override
    try:
        # Use absolute import to avoid namespace collision with root config/
        import importlib

        algo_config = importlib.import_module("algo.config")
        return getattr(algo_config, "MAX_BACKFILL_DAYS_LIMIT", 1825)
    except (ImportError, AttributeError):
        # Fallback to default if import fails
        return 1825


def get_loader_sla_timeout(loader_type: str = "default") -> int:
    """DEPRECATED - Use loaders/loader_timeout_config.py::get_loader_timeout instead.

    This function is dead code from Session 102 cleanup. All loader timeouts must be
    configured centrally in loaders/loader_timeout_config.py via get_loader_timeout().

    The hardcoded defaults (3600s, 5400s, 4200s) were causing timeout mismatches and
    brittleness when the centralized config had different values.

    SESSION 102 FIX: This function now raises an error to force migration to the
    centralized timeout configuration.

    Args:
        loader_type: Type of loader (e.g., "price", "signals", "default")

    Returns:
        Timeout in seconds

    Raises:
        RuntimeError: Always - use get_loader_timeout() instead
    """
    raise RuntimeError(
        "[DEPRECATED] get_loader_sla_timeout() is dead code (Session 102). "
        "Use loaders/loader_timeout_config.py::get_loader_timeout() instead. "
        "All timeouts must be centralized to prevent configuration drift. "
        "Migrate to: from loaders.loader_timeout_config import get_loader_timeout; "
        "timeout = get_loader_timeout(loader_name)"
    )
