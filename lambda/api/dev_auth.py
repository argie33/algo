"""
Development Authentication Context

SECURITY: This module is ONLY for local development (dev_server.py).
It is automatically disabled in production Lambda because Cognito is always configured.

Dev mode allows testing without Cognito JWT tokens.
In production, this code path is unreachable because COGNITO_USER_POOL_ID is always set.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def is_local_dev_mode() -> bool:
    """
    Check if we're in local development mode (NOT Lambda).

    Returns True if:
    1. ALLOW_DEV_TOKENS_TEST override is set (for integration testing)
    2. OR ENVIRONMENT=development (dev_server.py sets this)
    3. OR we're NOT in AWS Lambda AND Cognito NOT configured

    Activates dev mode for local dev_server automatically.
    """
    allow_dev_test = os.getenv("ALLOW_DEV_TOKENS_TEST", "").lower() == "true"
    if allow_dev_test:
        logger.warning("[DEV_AUTH] Testing mode enabled: accepting dev tokens! This is ONLY for integration testing.")
        return True

    if os.getenv("ENVIRONMENT", "").lower() == "development":
        logger.info("[DEV_AUTH] Local development mode enabled (ENVIRONMENT=development)")
        return True

    is_lambda = "AWS_LAMBDA_FUNCTION_NAME" in os.environ
    cognito_configured = bool(os.getenv("COGNITO_USER_POOL_ID", "").strip())
    is_dev = (not is_lambda) and (not cognito_configured)
    if is_dev:
        logger.info("[DEV_AUTH] Local development mode enabled (Cognito not configured)")
    return is_dev


def get_dev_claims(token: str | None) -> dict[str, Any] | None:
    """
    Generate development claims for testing without Cognito.

    Returns None if not in dev mode (this will be the case in production Lambda).

    SECURITY FIX: Dev tokens now include exp claim (24-hour expiration)
    to prevent indefinite token validity if leaked.

    Args:
        token: Optional bearer token (can be 'dev-user', 'dev-admin', etc.)

    Returns:
        Dict with Cognito-compatible claims, or None if not in dev mode
    """
    if not is_local_dev_mode():
        return None

    if not token or not token.startswith("dev-"):
        return None

    # Extract role from token (e.g., 'dev-admin' -> 'admin')
    token_parts = token.split("-", 1)
    role = token_parts[1] if len(token_parts) > 1 else "user"

    # Normalize to valid group names
    valid_roles = {"admin", "user", "trader"}
    groups = [role] if role in valid_roles else ["user"]

    # SECURITY FIX: Add exp claim (24 hours from now, in seconds since epoch)
    now = int(time.time())
    expiration = now + (24 * 60 * 60)  # 24-hour expiration

    claims = {
        "sub": f"dev-{role}",
        "cognito:groups": groups,
        "email": f"dev-{role}@localhost",
        "aud": "dev-client",
        "token_use": "id",
        "exp": expiration,  # Expiration in 24 hours
        "iat": now,  # Issued at timestamp
    }

    logger.info(f"[DEV_AUTH] Generated dev claims for token: {token[:10]}..., groups: {groups}, expires at {expiration}")
    return claims


def validate_dev_token(
    token: str | None,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    """
    Validate a development token (only works in local dev mode).

    SECURITY FIX: Now validates expiration claim to prevent indefinite token validity.

    Returns:
        (is_valid: bool, claims: dict or None, error: str or None)
    """
    if not is_local_dev_mode():
        return (False, None, "Dev mode not enabled (not in local development)")

    if not token:
        return (False, None, "No token provided")

    if not token.startswith("dev-"):
        return (
            False,
            None,
            "Dev token must start with 'dev-' (e.g., 'dev-user', 'dev-admin')",
        )

    claims = get_dev_claims(token)
    if not claims:
        return (False, None, "Failed to generate dev claims")

    # SECURITY FIX: Validate expiration claim
    if "exp" in claims:
        now = int(time.time())
        if now > claims["exp"]:
            return (False, None, f"Dev token expired (exp={claims['exp']}, now={now})")

    return (True, claims, None)
