#!/usr/bin/env python3
"""Centralized database timezone management.

This module provides a single source of truth for database timezone handling,
reducing duplication across 15+ files that independently run SHOW timezone.
"""

import logging
from zoneinfo import ZoneInfo

import psycopg2

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

_DB_TZ_CACHE = None


def get_db_timezone() -> ZoneInfo:
    """Retrieve the database session timezone once and cache it.

    All database connections in this session use the same timezone configuration,
    so we fetch it once and reuse. This reduces database round trips and provides
    a single point to handle timezone failures.

    Returns:
        ZoneInfo object representing the database timezone

    Raises:
        RuntimeError: If timezone cannot be retrieved from database
    """
    global _DB_TZ_CACHE

    if _DB_TZ_CACHE is not None:
        return _DB_TZ_CACHE

    try:
        with DatabaseContext("read") as cur:
            cur.execute("SHOW timezone")
            result = cur.fetchone()
            if not result:
                raise RuntimeError("Failed to retrieve database timezone - SHOW timezone returned no rows")
            _DB_TZ_CACHE = ZoneInfo(result[0])
            logger.debug(f"[DB_TZ] Database timezone: {result[0]}")
            return _DB_TZ_CACHE
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[DB_TZ] Database error retrieving timezone: {e}")
        raise RuntimeError(f"Cannot retrieve database timezone: {e}") from e
    except Exception as e:
        logger.error(f"[DB_TZ] Unexpected error retrieving timezone: {e}")
        raise RuntimeError(f"Cannot retrieve database timezone: {e}") from e
