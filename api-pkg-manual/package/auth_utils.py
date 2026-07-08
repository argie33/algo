"""Shared authentication utilities for all routes.

Centralizes admin access checks and authentication logic.
This is the SINGLE SOURCE OF TRUTH for auth in the API.
"""

from __future__ import annotations

from typing import Any


def check_admin_access(jwt_claims: dict[str, Any] | Any | None) -> bool:
    """Check if user has admin access from verified JWT claims only.

    Checks the 'cognito:groups' claim for 'admin' group membership.
    Never trust role from query params - only from JWT signature.
    Validates JWT claims structure before checking group membership.

    Args:
        jwt_claims: JWT claims dict or JWTClaims object from verified token

    Returns:
        True if user is admin, False otherwise
    """
    if not jwt_claims:
        return False
    if not isinstance(jwt_claims, dict):
        return False
    groups = jwt_claims.get("cognito:groups", [])
    if isinstance(groups, list):
        return "admin" in groups
    return False
