"""Shared helpers used by multiple lambda/api/routes/market/* handler modules.

Split out 2026-09-05 as part of the market.py file-size-ratchet decomposition (see
lambda/api/routes/market/__init__.py for the full split rationale). _rollback_savepoint is
used by technicals.py, top_movers.py and distribution_days.py; _parse_range_param is used by
sentiment.py and by __init__.py's fear-greed wrapper.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
from psycopg2.extensions import cursor

logger = logging.getLogger(__name__)


def _rollback_savepoint(cur: cursor, name: str) -> None:
    """Consolidate savepoint rollback error handling."""
    try:
        cur.execute(f"ROLLBACK TO SAVEPOINT {name}")
        cur.execute(f"RELEASE SAVEPOINT {name}")
    except (psycopg2.OperationalError, psycopg2.DatabaseError) as sp_err:
        logger.debug(f"[SAVEPOINT_ROLLBACK] Error rolling back {name}: {type(sp_err).__name__}")


def _parse_range_param(params: dict[str, Any], default: int = 30) -> int:
    if not params:
        return default

    # CRITICAL: Fail-fast on malformed params. Range/days must be explicit, not silent fallback.
    range_val = params.get("range")
    if range_val:
        if not isinstance(range_val, list) or not range_val:
            raise ValueError("CRITICAL: 'range' parameter must be a non-empty list")
        try:
            val_str = str(range_val[0]).strip()
            # Handle time suffixes: 30d, 4w, 12m, 1y
            if val_str and val_str[-1].lower() in "dwmy":
                suffix = val_str[-1].lower()
                num = int(val_str[:-1])
                if suffix == "d":
                    parsed = num
                elif suffix == "w":
                    parsed = num * 7
                elif suffix == "m":
                    parsed = num * 30  # Approximate 30 days per month
                elif suffix == "y":
                    parsed = num * 365  # Approximate 365 days per year
            else:
                parsed = int(val_str)

            if parsed <= 0:
                raise ValueError(f"CRITICAL: 'range' must be positive, got {parsed}")
            return parsed
        except (ValueError, TypeError) as e:
            raise ValueError(f"CRITICAL: 'range' parameter invalid: {e}") from e

    days_val = params.get("days")
    if days_val:
        if not isinstance(days_val, list) or not days_val:
            raise ValueError("CRITICAL: 'days' parameter must be a non-empty list")
        try:
            val_str = str(days_val[0]).strip()
            # Handle time suffixes: 30d, 4w, 12m, 1y
            if val_str and val_str[-1].lower() in "dwmy":
                suffix = val_str[-1].lower()
                num = int(val_str[:-1])
                if suffix == "d":
                    parsed = num
                elif suffix == "w":
                    parsed = num * 7
                elif suffix == "m":
                    parsed = num * 30
                elif suffix == "y":
                    parsed = num * 365
            else:
                parsed = int(val_str)

            if parsed <= 0:
                raise ValueError(f"CRITICAL: 'days' must be positive, got {parsed}")
            return parsed
        except (ValueError, TypeError) as e:
            raise ValueError(f"CRITICAL: 'days' parameter invalid: {e}") from e

    return default
