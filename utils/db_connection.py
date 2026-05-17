#!/usr/bin/env python3
"""
Unified database connection factory.

Centralizes all psycopg2.connect() calls to a single source.
Handles retries, pooling, and proper credential fallback.
"""

import psycopg2
import logging

from config.credential_helper import get_db_config

logger = logging.getLogger(__name__)


def get_db_connection(max_retries: int = 3, timeout: int = 5):
    """Get a PostgreSQL connection with automatic retry and credential management.

    Args:
        max_retries: Number of connection attempts before failing
        timeout: Connection timeout in seconds

    Returns:
        psycopg2.extensions.connection: Connected database connection

    Raises:
        psycopg2.OperationalError: If connection fails after max retries
    """
    config = get_db_config()
    config["connect_timeout"] = timeout

    last_error = None
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(**config)
            logger.debug(f"Database connection established (attempt {attempt + 1})")
            return conn
        except psycopg2.OperationalError as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.warning(f"Connection attempt {attempt + 1} failed, retrying: {e}")
            else:
                logger.error(f"Failed to connect to database after {max_retries} attempts: {e}")

    raise last_error or psycopg2.OperationalError("Database connection failed")
