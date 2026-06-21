#!/usr/bin/env python3
"""
DEPRECATED: This module is superseded by utils.validation.framework

For backward compatibility, this module re-exports the unified validation
functions from utils.validation. All new code should import directly from
utils.validation instead.

See utils/validation/__init__.py for the single source of truth.
"""

import logging
from typing import Optional

# Re-export unified validation system for backward compatibility
from utils.validation import (
    EASTERN_TZ,
    safe_bool,
    safe_int,
    safe_int_strict,
    safe_json_loads,
    safe_parse_date,
    safe_parse_datetime_et,
    safe_str,
)


logger = logging.getLogger(__name__)

__all__ = [
    "safe_float",
    "safe_float_strict",
    "safe_int",
    "safe_int_strict",
    "safe_parse_date",
    "safe_parse_datetime_et",
    "safe_json_loads",
    "safe_str",
    "safe_bool",
    "EASTERN_TZ",
    "log_data_fetch",
    "log_loader_completion",
]


def log_data_fetch(
    source: str,
    count: int,
    error: Optional[str] = None,
    fetch_time_ms: Optional[float] = None,
) -> None:
    """Log data fetch results with consistent format."""
    time_str = f" ({fetch_time_ms:.0f}ms)" if fetch_time_ms else ""

    if error:
        logger.error(f"[{source}] Fetch failed: {error}{time_str}")
    elif count == 0:
        logger.warning(f"[{source}] Returned 0 rows{time_str}")
    else:
        logger.info(f"[{source}] Fetched {count} rows{time_str}")


def log_loader_completion(
    table_name: str,
    rows_inserted: int,
    rows_skipped: int = 0,
    rows_failed: int = 0,
    duration_sec: float = 0.0,
) -> None:
    """Log loader completion with summary statistics."""
    total = rows_inserted + rows_skipped + rows_failed
    if total == 0:
        logger.warning(f"[{table_name}] No data processed")
        return

    duration_str = f" ({duration_sec:.1f}s)" if duration_sec > 0 else ""

    if rows_failed > 0:
        logger.error(
            f"[{table_name}] Loaded {rows_inserted}/{total} rows "
            f"({rows_skipped} skipped, {rows_failed} FAILED){duration_str}"
        )
    elif rows_inserted == 0:
        logger.warning(
            f"[{table_name}] No new rows inserted "
            f"({rows_skipped} skipped, {rows_failed} failed){duration_str}"
        )
    else:
        logger.info(
            f"[{table_name}] Loaded {rows_inserted}/{total} rows "
            f"({rows_skipped} skipped){duration_str}"
        )
