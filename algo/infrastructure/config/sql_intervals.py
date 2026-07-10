#!/usr/bin/env python3
"""SQL INTERVAL Helper - Convert config days to SQL INTERVAL strings.

Provides utilities to convert configuration day values to PostgreSQL INTERVAL strings.
This centralizes INTERVAL construction to make it easy to swap between config-driven
and hardcoded values during migration.

Usage:
    from config.sql_intervals import get_interval_sql

    # Get the INTERVAL for 7 days from config
    interval_7d = get_interval_sql("7d")  # Returns "INTERVAL '7 days'"

    # Use in SQL
    cur.execute(f"SELECT * FROM table WHERE created > NOW() - {interval_7d}")

Configuration Keys:
    sql_interval_1d_days       → INTERVAL '1 days'
    sql_interval_7d_days       → INTERVAL '7 days'
    sql_interval_14d_days      → INTERVAL '14 days'
    sql_interval_24h_days      → INTERVAL '1 days' (24 hours = 1 day)
    sql_interval_30d_days      → INTERVAL '30 days'
    sql_interval_50d_days      → INTERVAL '50 days'
    sql_interval_60d_days      → INTERVAL '60 days'
    sql_interval_90d_days      → INTERVAL '90 days'
    sql_interval_365d_days     → INTERVAL '365 days'
    sql_interval_52w_days      → INTERVAL '364 days'
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import AlgoConfig


def get_interval_sql(interval_key: str, config: "AlgoConfig | None" = None) -> str:
    """Get SQL INTERVAL string from config.

    Args:
        interval_key: Key like "7d", "30d", "24h", or "365d"
        config: Optional AlgoConfig instance (uses get_config() if not provided)

    Returns:
        SQL INTERVAL string like "INTERVAL '7 days'"

    Raises:
        ValueError: If interval_key is not recognized
    """
    if config is None:
        from . import get_config
        config = get_config()

    # Map short keys to config keys
    key_map = {
        "1d": "sql_interval_1d_days",
        "7d": "sql_interval_7d_days",
        "14d": "sql_interval_14d_days",
        "24h": "sql_interval_24h_days",
        "30d": "sql_interval_30d_days",
        "50d": "sql_interval_50d_days",
        "60d": "sql_interval_60d_days",
        "90d": "sql_interval_90d_days",
        "365d": "sql_interval_365d_days",
        "52w": "sql_interval_52w_days",
    }

    config_key = key_map.get(interval_key)
    if not config_key:
        raise ValueError(
            f"Unknown interval key: {interval_key!r}. "
            f"Supported: {', '.join(sorted(key_map.keys()))}"
        )

    days = config.get(config_key)
    if days is None:
        raise ValueError(f"Configuration key {config_key!r} not found")

    # Convert to int if float (for 24h which is stored as 1.0 days)
    days_int = int(days) if isinstance(days, float) and days == int(days) else days

    return f"INTERVAL '{days_int} days'"


def get_interval_days(interval_key: str, config: "AlgoConfig | None" = None) -> int | float:
    """Get raw day value from config.

    Args:
        interval_key: Key like "7d", "30d", "24h", etc.
        config: Optional AlgoConfig instance

    Returns:
        Numeric value (int or float) representing days
    """
    if config is None:
        from . import get_config
        config = get_config()

    key_map = {
        "1d": "sql_interval_1d_days",
        "7d": "sql_interval_7d_days",
        "14d": "sql_interval_14d_days",
        "24h": "sql_interval_24h_days",
        "30d": "sql_interval_30d_days",
        "50d": "sql_interval_50d_days",
        "60d": "sql_interval_60d_days",
        "90d": "sql_interval_90d_days",
        "365d": "sql_interval_365d_days",
        "52w": "sql_interval_52w_days",
    }

    config_key = key_map.get(interval_key)
    if not config_key:
        raise ValueError(
            f"Unknown interval key: {interval_key!r}. "
            f"Supported: {', '.join(sorted(key_map.keys()))}"
        )

    value = config.get(config_key)
    if value is None:
        raise ValueError(f"Configuration key {config_key!r} not found")
    return value if isinstance(value, (int, float)) else int(value)
