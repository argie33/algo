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

import psycopg2
import psycopg2.errors


logger = logging.getLogger(__name__)


def check_idempotency_key(cur, idempotency_key: str, endpoint: str, timeout_sec: int = 5) -> dict | None:
    """Check if request was already processed using idempotency key.

    Args:
        cur: Database cursor
        idempotency_key: Unique identifier from X-Idempotency-Key header
        endpoint: API endpoint path (e.g., /api/trades/manual)
        timeout_sec: Query timeout in seconds

    Returns:
        Cached response dict if found, None otherwise
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
            logger.info(f"Idempotency key cache hit: {endpoint} (key={idempotency_key[:16]}...)")
            try:
                response = json.loads(row["response_data"])
                if isinstance(response, dict):
                    return response
                else:
                    logger.error(f"Cached response is not a dict: {type(response)}")
                    return None
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to deserialize cached response: {e}. Treating as cache miss.")
                return None
        return None
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ):
        logger.debug("Idempotency key table does not exist or database error — proceeding without cache")
        return None


def store_idempotency_key(cur, idempotency_key: str, endpoint: str, response_data: dict, timeout_sec: int = 5) -> bool:
    """Store idempotency key with response for future replays.

    Args:
        cur: Database cursor
        idempotency_key: Unique identifier from X-Idempotency-Key header
        endpoint: API endpoint path (e.g., /api/trades/manual)
        response_data: Full response dict to cache
        timeout_sec: Query timeout in seconds

    Returns:
        True if stored successfully, False otherwise
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
        logger.info(f"Stored idempotency key: {endpoint} (key={idempotency_key[:16]}...)")
        return True
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        logger.debug(f"Idempotency key storage skipped (table missing or DB error): {type(e).__name__}")
        return False


def cleanup_expired_keys(cur, days_old: int = 7, batch_size: int = 1000, timeout_sec: int = 10) -> int:
    """Clean up expired idempotency keys older than specified days.

    Typically called by background job to prevent unbounded table growth.

    Args:
        cur: Database cursor
        days_old: Delete keys older than this many days (default 7)
        batch_size: Delete this many rows per batch
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
            logger.info(f"Cleaned up {deleted_count} expired idempotency keys")
        return deleted_count
    except (psycopg2.errors.UndefinedTable, psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        if isinstance(e, psycopg2.errors.UndefinedTable):
            logger.warning("Cleanup skipped: idempotency key table does not exist")
        else:
            logger.error(f"Failed to clean up idempotency keys: {type(e).__name__}: {e}")
        return 0
