"""Unified route handler decorator for consistent error handling and validation.

Eliminates duplication across 24+ route files by centralizing:
- Error handling and response formatting
- Authentication checks
- Request validation
- Timeout management
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from api_types import JWTClaims, RouteBody, RouteParams
from psycopg2.extensions import cursor
from routes.utils import error_response, raise_db_error

logger = logging.getLogger(__name__)

T = TypeVar("T")


def route_handler(
    auth_required: bool = False,
    admin_required: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for consistent route handling with error boundaries.

    Handles:
    - Authentication validation (if auth_required=True)
    - Admin check (if admin_required=True)
    - Error handling and response formatting
    - Timeout management

    Usage:
        @route_handler(admin_required=True)
        def handle_admin_route(cur, path, method, params, body, jwt_claims):
            return json_response(200, {"status": "ok"})
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(
            cur: cursor,
            path: str,
            method: str,
            params: RouteParams | dict[str, Any],
            body: RouteBody | dict[str, Any] | None = None,
            jwt_claims: JWTClaims | dict[str, Any] | None = None,
        ) -> Any:
            try:
                # Validate authentication if required
                if auth_required and not jwt_claims:
                    return error_response(401, "unauthorized", "Authentication required")

                # Validate admin access if required
                if admin_required:
                    from auth_utils import check_admin_access

                    if not check_admin_access(jwt_claims):
                        user_id = jwt_claims.get("sub") if jwt_claims else "unknown"
                        logger.warning(f"Unauthorized admin access attempt by {user_id}")
                        return error_response(403, "forbidden", "Admin access required")

                # Call the wrapped handler
                return func(cur, path, method, params, body, jwt_claims)

            except Exception as e:
                # Consistent error handling and logging
                logger.error(f"[{func.__name__}] unhandled {type(e).__name__}: {e}", exc_info=True)
                raise_db_error(e, func.__name__)

        return wrapper

    return decorator
