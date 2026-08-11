"""Centralized authentication and authorization guards for API routes.

Single source of truth for all auth checks (admin, user, role-based).
"""

from __future__ import annotations

import logging
from typing import Any

from auth_utils import check_admin_access as _check_admin_access

logger = logging.getLogger(__name__)


class RouteAuthGuard:
    """Centralized authorization checks for all routes.

    Usage:
        if not RouteAuthGuard.check_admin_access(jwt_claims):
            return error_response(403, "forbidden", "Admin access required")
    """

    @staticmethod
    def check_admin_access(jwt_claims: dict[str, Any] | None) -> bool:
        """Check if user has admin access from verified JWT claims.

        Delegates to auth_utils.check_admin_access() - the actual single source of
        truth (used by 6 other route files). This class previously carried its own
        parallel copy of the same check, missing the dev-admin recognition the
        canonical version has - both docstrings independently claimed to be "the
        single source of truth" while diverging in behavior. In practice this meant
        /api/audit/* was the one route family that rejected a valid local dev-admin
        session with a 403 while every other admin-gated route accepted it - a
        functional inconsistency (fail-closed, not a security hole) rather than a
        vulnerability, but exactly the kind of duplicated-logic drift this codebase
        has hit before in other areas (see MEMORY.md's execution_mode
        blocklist/allowlist entries for the same root pattern: one copy gets fixed,
        the other one doesn't even know it's a copy).

        Args:
            jwt_claims: JWT claims dict from API Gateway event (or None in dev)

        Returns:
            True if user is admin, False otherwise
        """
        is_admin = _check_admin_access(jwt_claims)
        if not is_admin and jwt_claims:
            user_id = jwt_claims.get("sub", "unknown") if isinstance(jwt_claims, dict) else "unknown"
            logger.info(f"[AUTH_GUARD] Admin access denied: user {user_id}")
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
