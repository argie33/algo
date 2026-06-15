#!/usr/bin/env python3
"""
DEPRECATED: Use utils.data.age_validator.DataAgeValidator instead.

This module is kept for backwards compatibility only. All new code should use:
    from utils.data.age_validator import DataAgeValidator

    result = DataAgeValidator.check('price_daily')
    if not result['is_fresh']:
        logger.warning(f"Stale: {result['message']}")
"""

import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Re-export from new unified validator for backwards compatibility
from utils.data.age_validator import check_freshness


def get_staleness_threshold_days() -> int:
    """DEPRECATED: Get max data staleness from config.

    This was the old approach — using a single global threshold.
    New code should use DataAgeValidator.check() which respects
    per-table thresholds from freshness_config.
    """
    try:
        from algo.infrastructure import get_config

        return get_config().get("max_data_staleness_days", 3)
    except Exception:
        return 3


def assert_fresh(
    last_loaded_date: Optional[Any],
    data_type: str = "generic",
    context: str = "",
) -> None:
    """DEPRECATED: Assert data is fresh.

    Raises:
        ValueError: If data is stale or missing
    """
    freshness = check_freshness(last_loaded_date, data_type, context=context)
    if not freshness["is_fresh"]:
        raise ValueError(f"{freshness['message']}")
