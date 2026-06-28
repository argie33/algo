"""Idempotency key handling for API requests.

Prevents duplicate operations on retries by tracking request identifiers
and returning cached responses for repeat requests.

Usage:
    # Check for idempotency key before processing
    cached_response = check_idempotency_key(cur, idempotency_key, endpoint)
    if cached_response:
        return cached_response

    # Process request...
    result = process_request()

    # Store idempotency key with result
    store_idempotency_key(cur, idempotency_key, endpoint, result)
    return result
"""

import json
import logging
from typing import Any

import psycopg2
import psycopg2.errors

logger = logging.getLogger(__name__)


def check_idempotency_key(cur: Any, idempotency_key: str, endpoint: str, timeout_sec: int = 5) -> dict[str, Any] | None:
    """Check if request was already processed using idempotency key.

    Args:
        cur: Database cursor
        idempotency_key: Unique identifier from X-Idempotency-Key header
        endpoint: API endpoint path (e.g., /api/trades/manual)
        timeout_sec: Query timeout in seconds

    Returns:
        Cached response dict if found, None if cache miss (legitimate)

    Raises:
        RuntimeError: If idempotency infrastructure unavailable (table missing or DB connection failure).
                     Raising prevents silent duplicate trade risk from looking like a cache miss.
    """
    if not idempotency_key:
        return None

    try:
        cur.execute("SET LOCAL statement_timeout = %s", (timeout_sec * 1000,))
        cur.execute(
            """
            SELECT response_data, created_at FROM api_idempotency_keys
            WHERE idempotency_key = %s AND endpoint = %s
            LIMIT 1
            """,
            (idempotency_key, endpoint),
        )
        row = cur.fetchone()
        if row:
            logger.info(
                "Idempotency key cache hit: %s (key=%s...)",
                endpoint,
                idempotency_key[:16],
            )
            try:
                response = json.loads(row["response_data"])
                if isinstance(response, dict):
                    return response
                logger.error("Cached response is not a dict: %s", type(response))
                return None
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(
                    "Failed to deserialize cached response: %s. Treating as cache miss.",
                    e,
                )
                return None
        return None
    except (
        psycopg2.errors.UndefinedTable,  # pylint: disable=no-member
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        raise RuntimeError(
            f"IDEMPOTENCY INFRASTRUCTURE FAILURE: {type(e).__name__}: {e}. "
            f"Cannot check idempotency key — duplicate trade protection unavailable. "
            f"Ensure api_idempotency_keys table exists and database connection is healthy."
        ) from e


def store_idempotency_key(
    cur: Any, idempotency_key: str, endpoint: str, response_data: dict[str, Any], timeout_sec: int = 5
) -> bool:
    """Store idempotency key with response for future replays.

    Args:
        cur: Database cursor
        idempotency_key: Unique identifier from X-Idempotency-Key header
        endpoint: API endpoint path (e.g., /api/trades/manual)
        response_data: Full response dict to cache
        timeout_sec: Query timeout in seconds

    Returns:
        True if stored successfully

    Raises:
        RuntimeError: If idempotency infrastructure unavailable (table missing or DB connection failure).
                     Raising prevents silent duplicate trade risk from returning False.
    """
    if not idempotency_key:
        return False

    try:
        response_json = json.dumps(response_data)
        cur.execute("SET LOCAL statement_timeout = %s", (timeout_sec * 1000,))
        cur.execute(
            """
            INSERT INTO api_idempotency_keys (idempotency_key, endpoint, response_data, created_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (idempotency_key, endpoint) DO UPDATE
            SET response_data = %s, created_at = NOW()
            """,
            (idempotency_key, endpoint, response_json, response_json),
        )
        logger.info("Stored idempotency key: %s (key=%s...)", endpoint, idempotency_key[:16])
        return True
    except (
        psycopg2.errors.UndefinedTable,  # pylint: disable=no-member
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        raise RuntimeError(
            f"IDEMPOTENCY INFRASTRUCTURE FAILURE: {type(e).__name__}: {e}. "
            f"Cannot store idempotency key — duplicate trade protection unavailable. "
            f"Ensure api_idempotency_keys table exists and database connection is healthy."
        ) from e


def cleanup_expired_keys(cur: Any, days_old: int = 7, timeout_sec: int = 10) -> int:
    """Clean up expired idempotency keys older than specified days.

    Typically called by background job to prevent unbounded table growth.

    Args:
        cur: Database cursor
        days_old: Delete keys older than this many days (default 7)
        timeout_sec: Query timeout in seconds

    Returns:
        Number of rows deleted
    """
    try:
        cur.execute("SET LOCAL statement_timeout = %s", (timeout_sec * 1000,))
        cur.execute(
            """
            DELETE FROM api_idempotency_keys
            WHERE created_at < NOW() - INTERVAL %s DAY
            AND RANDOM() < 0.1
            """,
            (days_old,),
        )
        deleted_count: int = int(cur.rowcount) if cur.rowcount else 0
        if deleted_count > 0:
            logger.info("Cleaned up %s expired idempotency keys", deleted_count)
        return deleted_count
    except (
        psycopg2.errors.UndefinedTable,  # pylint: disable=no-member
        psycopg2.DatabaseError,
        psycopg2.OperationalError,
    ) as e:
        if isinstance(e, psycopg2.errors.UndefinedTable):  # pylint: disable=no-member
            logger.warning("Cleanup skipped: idempotency key table does not exist")
        else:
            logger.error("Failed to clean up idempotency keys: %s: %s", type(e).__name__, e)
        return 0
