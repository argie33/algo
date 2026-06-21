#!/usr/bin/env python3
"""
Data Operations Integration - Unified API for freshness, validation, caching
"""

import logging
from collections.abc import Callable
from typing import Any

from utils.data.age_validator import check_freshness, is_fresh
from utils.db.query_cache import get_or_create_cache


logger = logging.getLogger(__name__)


def load_with_freshness(
    fetch_fn: Callable[[], Any],
    data_type: str,
    context: str = "",
    stale_ok: bool = False,
) -> Any | None:
    """Load data and validate freshness."""
    try:
        data, last_updated = fetch_fn()
    except Exception as e:
        raise RuntimeError(f"Operation failed: {e}") from e

    if data is None:
        return None

    freshness = check_freshness(last_updated, data_type, context=context)
    if not freshness["is_fresh"] and not stale_ok:
        raise RuntimeError(
            f"Data freshness check failed for {data_type}: {freshness['message']}. "
            f"Cannot proceed with stale data ({context}). "
            f"Set stale_ok=True only for non-critical operations."
        )

    return (data, freshness)


def get_or_cache(
    key: Any,
    compute_fn: Callable[[], Any],
    ttl_seconds: int = 300,
    cache_name: str = "default",
    context: str = "",
    allow_stale: bool = False,
) -> Any | None:
    """Get value from cache or compute if missing."""
    cache = get_or_create_cache(cache_name, ttl_seconds=ttl_seconds)
    try:
        return cache.get_or_compute(
            key=key,
            compute_fn=compute_fn,
            context=context,
            allow_stale=allow_stale,
        )
    except Exception as e:
        raise RuntimeError(f"Operation failed: {e}") from e


def check_data_fresh(
    last_updated: Any | None,
    data_type: str,
    context: str = "",
) -> bool:
    """Quick freshness check."""
    return is_fresh(last_updated, data_type)
