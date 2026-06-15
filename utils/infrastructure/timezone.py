#!/usr/bin/env python3
"""Centralized timezone utilities for consistent UTC and Eastern time handling.

Single source of truth for all timezone conversions and datetime operations.
"""

from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from typing import Union

# Single source of truth for Eastern timezone
EASTERN_TZ = ZoneInfo("America/New_York")


def normalize_to_utc_datetime(dt: Union[datetime, date, None]) -> datetime:
    """Convert any datetime or date to UTC-aware datetime.

    Handles:
    - Naive datetimes (assumes UTC)
    - Aware datetimes (converts to UTC)
    - date objects (converts to start of day UTC)
    - None (returns current UTC time)
    """
    if dt is None:
        return datetime.now(timezone.utc)

    if isinstance(dt, date) and not isinstance(dt, datetime):
        return datetime.combine(dt, datetime.min.time(), tzinfo=timezone.utc)

    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return datetime.now(timezone.utc)


def to_eastern_time(dt: datetime) -> datetime:
    """Convert UTC-aware datetime to Eastern time (aware)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(EASTERN_TZ)


def from_eastern_time(dt: datetime) -> datetime:
    """Convert Eastern time datetime to UTC (aware).

    Assumes input is Eastern time if naive.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EASTERN_TZ)
    return dt.astimezone(timezone.utc)
