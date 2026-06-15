#!/usr/bin/env python3
"""
Data Operations Integration - Unified API for freshness, validation, caching
"""

import logging
from typing import Any, Callable, Dict, Optional

from utils.validation import check_freshness, is_fresh
from utils.validation import validate_record
from utils.db import get_or_create_cache

logger = logging.getLogger(__name__)

def load_with_freshness(
    fetch_fn: Callable[[], Any],
    data_type: str,
    context: str = "",
    stale_ok: bool = False,
) -> Optional[Any]:
    """Load data and validate freshness."""
    try:
        data, last_updated = fetch_fn()
    except Exception as e:
        logger.error(f"Failed to fetch {data_type} {context}: {e}")
        return None

    if data is None:
        return None

    freshness = check_freshness(last_updated, data_type, context=context)
    if not freshness["is_fresh"] and not stale_ok:
        logger.warning(f"Skipping stale {data_type}: {freshness['message']}")
        return None

    return (data, freshness)

def get_or_cache(
    key: Any,
    compute_fn: Callable[[], Any],
    ttl_seconds: int = 300,
    cache_name: str = "default",
    context: str = "",
    allow_stale: bool = False,
) -> Optional[Any]:
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
        logger.error(f"Cache operation failed: {e}")
        return None

def validate_and_log(
    record: Dict[str, Any],
    schema: Dict[str, str],
    context: str = "",
) -> Dict[str, Any]:
    """Validate record against schema and log failures."""
    try:
        return validate_record(record, schema, context=context)
    except Exception as e:
        logger.error(f"Record validation failed: {e}")
        return record

def check_data_fresh(
    last_updated: Optional[Any],
    data_type: str,
    context: str = "",
) -> bool:
    """Quick freshness check."""
    return is_fresh(last_updated, data_type, context=context)
