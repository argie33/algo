#!/usr/bin/env python3
"""
Centralized Data Freshness Checking - Single Source of Truth for Staleness Detection

All freshness checks should go through this module to ensure consistency.
Uses AlgoConfig's max_data_staleness_days as the source of truth.

PRINCIPLE: Never hardcode staleness thresholds. All freshness logic must respect
the centralized config value that can be adjusted at runtime.

USAGE:
    from utils.validation import check_freshness, is_fresh
    from datetime import date

    # Quick yes/no check
    if is_fresh(last_loaded_date, data_type='price'):
        use_cached_data()
    else:
        refresh_data()

    # Detailed check with logging
    freshness = check_freshness(last_loaded_date, 'price', context="AAPL")
    if not freshness['is_fresh']:
        logger.warning(f"Stale data: {freshness['message']}")
        refresh_data()
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Any
from algo.infrastructure import get_config

logger = logging.getLogger(__name__)


def get_staleness_threshold_days() -> int:
    """Get max data staleness from centralized config.

    Returns:
        Maximum age of data in days before considered stale
    """
    return get_config().get('max_data_staleness_days', 3)


def is_fresh(
    last_loaded_date: Optional[Any],
    data_type: str = "generic",
    today: Optional[date] = None,
) -> bool:
    """Quick boolean check: is data fresh?

    Args:
        last_loaded_date: Date data was last loaded (date, datetime, or str ISO format)
        data_type: Type of data for logging context ('price', 'earnings', 'fundamentals', etc.)
        today: Reference date (defaults to today)

    Returns:
        True if data is fresh, False if stale or missing
    """
    freshness = check_freshness(last_loaded_date, data_type, today=today)
    return freshness['is_fresh']


def check_freshness(
    last_loaded_date: Optional[Any],
    data_type: str = "generic",
    today: Optional[date] = None,
    context: str = "",
) -> Dict[str, Any]:
    """Detailed freshness check with diagnostics.

    Args:
        last_loaded_date: Date data was last loaded (date, datetime, or str ISO format)
        data_type: Type of data for logging context
        today: Reference date (defaults to today)
        context: Additional context for logging (e.g., "AAPL", "sector=Technology")

    Returns:
        Dictionary with keys:
        - is_fresh: bool
        - age_days: int (age of data, or -1 if missing)
        - threshold_days: int (config value)
        - message: str (human-readable explanation)
        - last_loaded_date: date or None (normalized date)
    """
    if today is None:
        today = date.today()

    threshold_days = get_staleness_threshold_days()

    # Handle missing data
    if last_loaded_date is None:
        msg = f"[{data_type}] Data missing {context}".strip()
        logger.warning(msg)
        return {
            'is_fresh': False,
            'age_days': -1,
            'threshold_days': threshold_days,
            'message': msg,
            'last_loaded_date': None,
        }

    # Normalize to date
    try:
        if isinstance(last_loaded_date, datetime):
            loaded_date = last_loaded_date.date()
        elif isinstance(last_loaded_date, date):
            loaded_date = last_loaded_date
        elif isinstance(last_loaded_date, str):
            loaded_date = date.fromisoformat(last_loaded_date)
        else:
            msg = f"[{data_type}] Invalid date type {type(last_loaded_date).__name__} {context}".strip()
            logger.warning(msg)
            return {
                'is_fresh': False,
                'age_days': -1,
                'threshold_days': threshold_days,
                'message': msg,
                'last_loaded_date': None,
            }
    except (ValueError, AttributeError) as e:
        msg = f"[{data_type}] Failed to parse date {last_loaded_date!r}: {e} {context}".strip()
        logger.warning(msg)
        return {
            'is_fresh': False,
            'age_days': -1,
            'threshold_days': threshold_days,
            'message': msg,
            'last_loaded_date': None,
        }

    # Calculate age
    age = (today - loaded_date).days
    is_fresh = age <= threshold_days

    if is_fresh:
        msg = f"[{data_type}] Fresh ({age}d old, threshold {threshold_days}d) {context}".strip()
        logger.debug(msg)
    else:
        msg = f"[{data_type}] STALE ({age}d old, threshold {threshold_days}d) {context}".strip()
        logger.warning(msg)

    return {
        'is_fresh': is_fresh,
        'age_days': age,
        'threshold_days': threshold_days,
        'message': msg,
        'last_loaded_date': loaded_date,
    }


def assert_fresh(
    last_loaded_date: Optional[Any],
    data_type: str = "generic",
    context: str = "",
) -> None:
    """Assert data is fresh, raise error if stale.

    Args:
        last_loaded_date: Date data was last loaded
        data_type: Type of data
        context: Additional context for error message

    Raises:
        ValueError: If data is stale or missing
    """
    freshness = check_freshness(last_loaded_date, data_type, context=context)
    if not freshness['is_fresh']:
        raise ValueError(f"{freshness['message']}")


if __name__ == "__main__":
    # Example: check if price data is fresh
    from datetime import date
    today = date.today()
    three_days_ago = today - timedelta(days=3)
    five_days_ago = today - timedelta(days=5)

    print("Freshness Check Examples:")
    print("\nCase 1: Fresh data (3 days old, threshold=3)")
    result = check_freshness(three_days_ago, 'price', context="AAPL")
    print(f"  Fresh: {result['is_fresh']}, Message: {result['message']}")

    print("\nCase 2: Stale data (5 days old, threshold=3)")
    result = check_freshness(five_days_ago, 'price', context="TSLA")
    print(f"  Fresh: {result['is_fresh']}, Message: {result['message']}")

    print("\nCase 3: Missing data")
    result = check_freshness(None, 'earnings', context="MSFT")
    print(f"  Fresh: {result['is_fresh']}, Message: {result['message']}")
