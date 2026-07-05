"""Centralized authentication and authorization guards for API routes.

Single source of truth for all auth checks (admin, user, role-based).
Replaces 7 duplicate check_admin_access() implementations.
"""

from __future__ import annotations

import logging
from typing import Any

from utils.validation import CognitoValidator

logger = logging.getLogger(__name__)


class RouteAuthGuard:
    """Centralized authorization checks for all routes.

    Usage:
        if not RouteAuthGuard.check_admin_access(jwt_claims):
            return error_response(403, "forbidden", "Admin access required")

    Replaces: check_admin_access() in audit.py, admin.py, and 5 other files
    """

    @staticmethod
    def check_admin_access(jwt_claims: dict[str, Any] | None) -> bool:
        """Check if user has admin access from verified JWT claims.

        Only admin users can access protected admin endpoints.
        Uses CognitoValidator for centralized validation logic.

        Args:
            jwt_claims: JWT claims dict from API Gateway event (or None in dev)

        Returns:
            True if user is in admin group, False otherwise
        """
        if not jwt_claims:
            return False

        # Delegate to centralized validator
        is_admin = bool(CognitoValidator.validate_admin_access(jwt_claims))

        if not is_admin:
            user_id = jwt_claims.get("sub", "unknown")
            groups = jwt_claims.get("cognito:groups", [])
            logger.info(f"[AUTH_GUARD] Admin access denied: user {user_id} not in admin group. Groups: {groups}")

        return is_admin

    @staticmethod
    def check_user_authenticated(jwt_claims: dict[str, Any] | None) -> bool:
        """Check if user is authenticated (has valid JWT claims).

        Args:
            jwt_claims: JWT claims dict from API Gateway event

        Returns:
            True if user is authenticated, False otherwise
        """
        if not jwt_claims:
            logger.debug("[AUTH_GUARD] User not authenticated: jwt_claims is None")
            return False

        # Check for required fields in JWT
        user_id = jwt_claims.get("sub")
        if not user_id:
            logger.warning("[AUTH_GUARD] Invalid JWT: missing 'sub' claim")
            return False

        return True
