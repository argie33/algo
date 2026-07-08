#!/usr/bin/env python3
"""Configuration source monitoring and validation utilities.

Tracks where each config value comes from (database, defaults, overrides)
and provides utilities for configuration auditing and debugging.

Usage:
    from algo.config.config_monitoring import ConfigSourceMonitor

    monitor = ConfigSourceMonitor(config)
    monitor.print_config_sources()
    stale_defaults = monitor.find_missing_database_overrides()
"""

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class ConfigSourceMonitor:
    """Monitor and audit configuration sources."""

    def __init__(self, config: Any):
        """Initialize with config object that has _sources dict."""
        self.config = config
        self._sources: dict[str, str] = getattr(config, "_sources", {})

    def get_source(self, key: str) -> str:
        """Get source of a config value."""
        return self._sources.get(key, "unknown")

    def print_config_sources(self) -> None:
        """Print all config values and their sources."""
        sources_by_type = defaultdict(list)
        for key, source in self._sources.items():
            sources_by_type[source].append(key)

        logger.info("=== CONFIG SOURCE SUMMARY ===")
        for source, keys in sources_by_type.items():
            logger.info(f"\n{source.upper()} ({len(keys)} keys):")
            for key in sorted(keys)[:10]:
                logger.info(f"  - {key}")
            if len(keys) > 10:
                logger.info(f"  ... and {len(keys) - 10} more")

    def find_overrides(self) -> list[str]:
        """Find all config values that come from overrides."""
        return [k for k, v in self._sources.items() if v == "override"]

    def find_defaults_in_use(self) -> list[str]:
        """Find all config values still using default values."""
        return [k for k, v in self._sources.items() if v == "default"]

    def find_database_values(self) -> list[str]:
        """Find all config values loaded from database."""
        return [k for k, v in self._sources.items() if v == "database"]

    def validate_sources(self) -> list[str]:
        """Validate all config sources are known. Returns issues found."""
        issues = []
        for key, source in self._sources.items():
            if source not in ("database", "override", "default_fallback", "default"):
                issues.append(f"Unknown source '{source}' for config key '{key}'")
        return issues
