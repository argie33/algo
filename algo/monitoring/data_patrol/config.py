#!/usr/bin/env python3
"""Patrol configuration management - delegates to AlgoConfig (consolidated)."""

import logging
from typing import Any, cast

logger = logging.getLogger(__name__)

# Severity levels (for backward compatibility)
INFO, WARN, ERROR, CRIT = "info", "warn", "error", "critical"


class PatrolConfig:
    """Patrol configuration - delegates to AlgoConfig for single source of truth.

    This class is kept for backward compatibility. All methods delegate to AlgoConfig
    which loads from algo_config table. This consolidation eliminates duplicate
    database queries and ensures patrol thresholds are managed centrally.
    """

    def __init__(self, cur=None):
        """Legacy constructor for compatibility. Cursor parameter is ignored."""
        from algo.infrastructure import get_config

        self._config = get_config()

    def load(self, cur) -> None:
        """Legacy method - reload AlgoConfig instead."""
        self._config.reload()

    def get(self, key: str, default: int | float | str | None = None) -> int | float | str | None:
        """Get config value with fallback to default."""
        return cast(int | float | str | None, self._config.get(key, default))

    def get_staleness_windows(self) -> dict[str, Any]:
        """Get all staleness thresholds in days."""
        return cast(dict[str, Any], self._config.get_staleness_windows())

    def get_coverage_thresholds(self) -> dict[str, Any]:
        """Get coverage ratio thresholds."""
        return cast(dict[str, Any], self._config.get_coverage_thresholds())

    def get_price_sanity_config(self) -> dict[str, Any]:
        """Get OHLC/price sanity thresholds."""
        return cast(dict[str, Any], self._config.get_price_sanity_config())

    def get_volume_config(self) -> dict[str, Any]:
        """Get volume sanity thresholds."""
        return cast(dict[str, Any], self._config.get_volume_config())

    def get_quality_config(self) -> dict[str, Any]:
        """Get data quality thresholds."""
        return cast(dict[str, Any], self._config.get_quality_config())

    def get_cross_validation_config(self) -> dict[str, Any]:
        """Get cross-validation thresholds."""
        return cast(dict[str, Any], self._config.get_cross_validation_config())

    def get_corporate_actions_config(self) -> dict[str, Any]:
        """Get corporate actions detection config."""
        return cast(dict[str, Any], self._config.get_corporate_actions_config())

    def get_loader_contracts(self) -> dict[str, dict[str, Any]]:
        """Get loader contracts with expected output thresholds."""
        return cast(dict[str, dict[str, Any]], self._config.get_loader_contracts())

    def as_dict(self) -> dict[str, Any]:
        """Return patrol config as a dict (for logging)."""
        return {
            "staleness_windows": self.get_staleness_windows(),
            "coverage_thresholds": self.get_coverage_thresholds(),
            "price_sanity": self.get_price_sanity_config(),
            "volume_sanity": self.get_volume_config(),
            "quality": self.get_quality_config(),
            "cross_validation": self.get_cross_validation_config(),
            "corporate_actions": self.get_corporate_actions_config(),
        }
