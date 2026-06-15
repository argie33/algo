"""User isolation utilities for multi-tenant API.

Provides helper functions to:
- Extract authenticated user's Cognito sub from JWT claims
- Scope database queries to specific user
- Validate user access to resources
- Get user-scoped Alpaca credentials
"""

import logging
import psycopg2.sql
from typing import Optional, Dict, Any
from functools import wraps
from routes.utils import error_response
from utils.db.sql_safety import assert_safe_table, assert_safe_column

logger = logging.getLogger(__name__)


def get_user_id(jwt_claims: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract user ID (Cognito sub) from JWT claims.

    Args:
        jwt_claims: JWT claims dictionary from API Gateway or Lambda authorizer

    Returns:
        Cognito sub (user ID) or None if not authenticated
    """
    if not jwt_claims:
        return None

    user_id = jwt_claims.get("sub")
    if user_id:
        logger.debug(f"[USER] Authenticated as {user_id}")
    return user_id


def require_user(jwt_claims: Optional[Dict[str, Any]]) -> str:
    """Require user to be authenticated, return user ID.

    Args:
        jwt_claims: JWT claims dictionary

    Returns:
        Cognito sub

    Raises:
        ValueError: If user not authenticated
    """
    user_id = get_user_id(jwt_claims)
    if not user_id:
        raise ValueError("Authentication required for this endpoint")
    return user_id


def scope_query(sql: str, user_id: str, table_alias: str = None) -> tuple[str, dict]:
    """Add user scoping WHERE clause to SQL query.

    For queries that select from tables with cognito_sub column, automatically
    filters to only return rows for the authenticated user.

    Args:
        sql: SQL query string
        user_id: Cognito sub (user ID) to filter by
        table_alias: Optional table alias for cognito_sub column
                    (e.g., 'at' for 'algo_trades at WHERE at.cognito_sub = %s')
                    If None, uses 'cognito_sub' directly

    Returns:
        (scoped_sql: str, params: dict) - SQL with user filter added and params dict

    Example:
        >>> sql = "SELECT * FROM algo_positions WHERE symbol = %s"
        >>> scoped_sql, params = scope_query(sql, user_id, table_alias='ap')
        >>> # Result: "SELECT * FROM algo_positions ap WHERE symbol = %s AND ap.cognito_sub = %s"
    """
    if table_alias:
        user_filter = f" AND {table_alias}.cognito_sub = %s"
    else:
        user_filter = " AND cognito_sub = %s"

    # Check if query already has a WHERE clause
    if " WHERE " in sql.upper():
        scoped_sql = sql + user_filter
    else:
        scoped_sql = sql + " WHERE cognito_sub = %s"

    return scoped_sql, {"user_id": user_id}


def get_user_alpaca_credentials(
    cur, user_id: str, default_to_shared: bool = True
) -> Optional[Dict[str, str]]:
    """Get Alpaca credentials for a specific user.

    Attempts to fetch user-scoped Alpaca credentials. Falls back to shared
    credentials if user doesn't have their own (for backward compatibility).

    Args:
        cur: Database cursor
        user_id: Cognito sub (user ID)
        default_to_shared: If True, fall back to shared algo/alpaca secret if user has no specific secret

    Returns:
        {'key': api_key, 'secret': api_secret} or None if not found
    """
    try:
        from config.credential_manager import get_alpaca_credentials

        logger.debug(
            f"[ALPACA] Attempting to load user-scoped credentials for {user_id}"
        )
        return get_alpaca_credentials(user_id=user_id)
    except Exception as e:
        logger.warning(
            f"[ALPACA] Could not load user-scoped credentials for {user_id}: {e}"
        )
        if default_to_shared:
            logger.debug("[ALPACA] Falling back to shared credentials")
            try:
                from config.credential_manager import get_alpaca_credentials

                return get_alpaca_credentials(user_id=None)
            except Exception as fallback_err:
                logger.error(
                    f"[ALPACA] Fallback to shared credentials also failed: {fallback_err}"
                )
                return None
        return None


def validate_user_resource_access(
    cur, user_id: str, resource_type: str, resource_id: str
) -> bool:
    """Validate that user owns/can access a resource.

    Prevents users from accessing other users' data by validating ownership.

    Args:
        cur: Database cursor
        user_id: Cognito sub (user ID)
        resource_type: Type of resource ('trade', 'position', 'snapshot', etc.)
        resource_id: ID of the resource to validate access to

    Returns:
        True if user owns the resource, False otherwise
    """
    resource_tables = {
        "trade": ("algo_trades", "trade_id"),
        "position": ("algo_positions", "position_id"),
        "snapshot": ("algo_portfolio_snapshots", "snapshot_id"),
        "trade_add": ("algo_trade_adds", "trade_id"),
    }

    if resource_type not in resource_tables:
        logger.warning(f"[ACCESS] Unknown resource type: {resource_type}")
        return False

    table, id_column = resource_tables[resource_type]

    try:
        table_safe = assert_safe_table(table)
        col_safe = assert_safe_column(id_column)
        cur.execute(
            psycopg2.sql.SQL(
                "SELECT 1 FROM {} WHERE {} = %s AND cognito_sub = %s LIMIT 1"
            ).format(
                psycopg2.sql.Identifier(table_safe),
                psycopg2.sql.Identifier(col_safe),
            ),
            (resource_id, user_id),
        )
        result = cur.fetchone()
        return result is not None
    except Exception as e:
        logger.error(
            f"[ACCESS] Error validating access to {resource_type} {resource_id}: {e}"
        )
        return False


def require_user_resource_access(
    cur, user_id: str, resource_type: str, resource_id: str
) -> bool:
    """Require user to have access to resource, raise if denied.

    Args:
        cur: Database cursor
        user_id: Cognito sub (user ID)
        resource_type: Type of resource
        resource_id: ID of the resource

    Raises:
        PermissionError: If user doesn't own the resource
    """
    if not validate_user_resource_access(cur, user_id, resource_type, resource_id):
        raise PermissionError(f"Access denied to {resource_type} {resource_id}")
    return True


# Decorator for route handlers that require user authentication
def requires_auth(handler_func):
    """Decorator to require authentication for a handler.

    Wraps handler function to check for valid JWT claims and extract user_id.
    """

    @wraps(handler_func)
    def wrapper(cur, path, method, params, body=None, jwt_claims=None):
        try:
            user_id = require_user(jwt_claims)
            # Pass user_id as additional parameter to handler
            return handler_func(
                cur, path, method, params, body, jwt_claims=jwt_claims, user_id=user_id
            )
        except ValueError as e:
            return error_response(401, "unauthorized", str(e))

    return wrapper


# Decorator for route handlers that handle both authenticated and public requests
def optional_auth(handler_func):
    """Decorator for handlers that support both authenticated and public access.

    Extracts user_id if available, sets to None if not authenticated.
    """

    @wraps(handler_func)
    def wrapper(cur, path, method, params, body=None, jwt_claims=None):
        user_id = get_user_id(jwt_claims)
        return handler_func(
            cur, path, method, params, body, jwt_claims=jwt_claims, user_id=user_id
        )

    return wrapper
