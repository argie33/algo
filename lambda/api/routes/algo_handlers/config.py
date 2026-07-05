"""Route: algo"""

import logging
from datetime import datetime, timezone
from typing import Any

from psycopg2.extensions import cursor

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    db_route_handler,
    error_response,
    json_response,
    safe_dict_convert,
    safe_json_serialize,
)

from algo.infrastructure import AlgoConfig

logger = logging.getLogger(__name__)


@db_route_handler("fetch algo config")
def _get_algo_config(cur: cursor) -> Any:
    """Return all algo configuration rows with defaults and categorization for TIER 3 visibility."""
    try:
        cur.execute("SELECT key, value, value_type, description, updated_at FROM algo_config ORDER BY key")
        rows = cur.fetchall()

        # Build config dict keyed by config key (matches dashboard contract schema)
        config_dict = {}
        if rows:
            for row in rows:
                try:
                    row_dict = safe_json_serialize(safe_dict_convert(row))
                    key = row_dict.get("key")
                    value = row_dict.get("value")

                    if key:
                        # Use key directly as dict key (e.g., "algo_enabled": true)
                        # Convert string "true"/"false" to boolean if needed
                        if isinstance(value, str):
                            if value.lower() == "true":
                                config_dict[key] = True
                            elif value.lower() == "false":
                                config_dict[key] = False
                            else:
                                try:
                                    config_dict[key] = float(value) if "." in value else int(value)
                                except (ValueError, TypeError):
                                    config_dict[key] = value
                        else:
                            config_dict[key] = value
                except Exception as row_err:
                    logger.warning(f"Skipping config row due to error: {row_err}")
                    continue

        # Return as JSON response (not list response)
        # Ensure we always return a dict
        result = json_response(200, config_dict if config_dict else {"status": "empty"})
        if not isinstance(result, dict):
            logger.error(f"CRITICAL: json_response did not return dict! Got {type(result)}")
            return {"statusCode": 500, "errorType": "internal_error", "message": "Handler returned non-dict", "_error": "Handler error"}
        return result
    except Exception as e:
        logger.error(f"Config handler exception: {type(e).__name__}: {e}", exc_info=True)
        return error_response(500, "internal_error", f"Config handler error: {str(e)[:100]}")


@db_route_handler("fetch algo config key")
def _get_algo_config_key(cur: cursor, key: str) -> Any:
    """Return a single algo config key."""
    cur.execute(
        "SELECT key, value, value_type, description, updated_at FROM algo_config WHERE key = %s",
        (key,),
    )
    row = cur.fetchone()
    if not row:
        return error_response(404, "not_found", f"Configuration key not found: {key}")
    return json_response(200, safe_json_serialize(safe_dict_convert(row)))


@db_route_handler("reset algo config key")
def _reset_algo_config_key(cur: cursor, key: str, actor: str) -> Any:
    """Reset a configuration key to its default value (TIER 5: Reset capability)."""
    # Validate the key exists
    if key not in AlgoConfig.DEFAULTS:
        return error_response(404, "not_found", f"Config key not found: {key}")

    default_val = AlgoConfig.DEFAULTS[key][0]

    # Get current value for audit
    cur.execute("SELECT value FROM algo_config WHERE key = %s", (key,))
    old_row = cur.fetchone()
    old_value = old_row["value"] if old_row else None

    # Reset to default
    cur.execute(
        """
        UPDATE algo_config
        SET value = %s, updated_at = CURRENT_TIMESTAMP, updated_by = %s
        WHERE key = %s
    """,
        (default_val, actor, key),
    )

    # Log to audit trail
    cur.execute(
        """
        INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
    """,
        (key, old_value, default_val, actor),
    )

    logger.info(f"[TIER5] Config reset by {actor}: {key} = {default_val} (was {old_value})")

    return json_response(
        200,
        {
            "status": "success",
            "key": key,
            "old_value": old_value,
            "new_value": default_val,
            "reset_to_default": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": actor,
        },
    )


@db_route_handler("update algo config key")
def _update_algo_config_key(cur: cursor, key: str, body: dict[str, Any], actor: str) -> Any:
    """Update a configuration key (TIER 4: Configuration Editing)."""
    if not body or "value" not in body:
        return error_response(400, "bad_request", "value required in request body")

    # Validate the key exists and get its type
    cur.execute("SELECT key, value_type FROM algo_config WHERE key = %s", (key,))
    row = cur.fetchone()
    if row is None:
        return error_response(404, "not_found", f"Config key not found: {key}")

    new_value = body.get("value")

    # Validate the new value against AlgoConfig constraints
    try:
        if not AlgoConfig.DEFAULTS.get(key):
            return error_response(400, "bad_request", f"Unknown config key: {key}")

        expected_type = AlgoConfig.DEFAULTS[key][1]
        # Validate bounds and type
        config = AlgoConfig()
        config._validate_value(key, str(new_value), expected_type)
    except ValueError as e:
        logger.warning(f"Config validation failed for {key}={new_value}: {e}")
        return error_response(400, "bad_request", f"Invalid value for {key}: {e!s}")

    # Get old value for audit
    cur.execute("SELECT value FROM algo_config WHERE key = %s", (key,))
    old_row = cur.fetchone()
    old_value = old_row["value"] if old_row else None

    # Update the config
    cur.execute(
        """
            UPDATE algo_config
            SET value = %s, updated_at = CURRENT_TIMESTAMP, updated_by = %s
            WHERE key = %s
        """,
        (str(new_value), actor, key),
    )

    # Log to audit trail
    cur.execute(
        """
            INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (key, old_value, str(new_value), actor),
    )

    logger.info(f"[TIER4] Config updated by {actor}: {key} = {new_value} (was {old_value})")

    return json_response(
        200,
        {
            "status": "success",
            "key": key,
            "old_value": old_value,
            "new_value": str(new_value),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": actor,
        },
    )
