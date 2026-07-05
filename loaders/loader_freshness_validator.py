#!/usr/bin/env python3
"""Shared freshness validation utilities for all loaders.

Provides reusable freshness check pattern for loaders that depend on
snapshot tables (yfinance_snapshot, company_profile_snapshot, etc).

Usage:
    from datetime import date
    from loaders.loader_freshness_validator import validate_snapshot_freshness

    if not validate_snapshot_freshness(row, max_age_hours=24):
        return [self._unavailable_record(symbol, "Stale snapshot data")]
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


def validate_snapshot_freshness(
    row: dict[str, Any] | None,
    symbol: str,
    max_age_hours: int = 24,
    table_name: str = "snapshot",
) -> bool:
    """Validate snapshot data is fresh (within max_age_hours).

    Args:
        row: Database row with optional 'updated_at' field
        symbol: Symbol for logging
        max_age_hours: Maximum acceptable age in hours (default 24)
        table_name: Table name for logging

    Returns:
        True if data is fresh, False if stale or missing timestamp
    """
    if not row:
        logger.warning(f"[{table_name}] No data for {symbol}")
        return False

    updated_at = row.get("updated_at")
    if not updated_at:
        logger.warning(f"[{table_name}] {symbol} missing updated_at timestamp")
        return False

    try:
        age = datetime.now(timezone.utc) - updated_at
        if age > timedelta(hours=max_age_hours):
            logger.warning(f"[{table_name}] {symbol} data stale ({age.total_seconds() / 3600:.1f}h old)")
            return False
        return True
    except Exception as e:
        logger.error(f"[{table_name}] Freshness check failed for {symbol}: {e}")
        return False


def get_stale_message(row: dict[str, Any] | None, max_age_hours: int = 24) -> str:
    """Get human-readable message for stale data."""
    if not row or not row.get("updated_at"):
        return "Snapshot data missing or unverifiable"

    age = datetime.now(timezone.utc) - row["updated_at"]
    hours_old = age.total_seconds() / 3600
    return f"Stale snapshot data ({hours_old:.0f}h old, max {max_age_hours}h)"
