"""
Development Authentication Context

SECURITY: This module is ONLY for local development (dev_server.py).
It is automatically disabled in production Lambda because Cognito is always configured.

Dev mode allows testing without Cognito JWT tokens.
In production, this code path is unreachable because COGNITO_USER_POOL_ID is always set.
"""

import os
import logging
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)

def is_local_dev_mode() -> bool:
    """
    Check if we're in local development mode (NOT Lambda).

    Returns True ONLY if:
    1. We're NOT in AWS Lambda (no AWS_LAMBDA_FUNCTION_NAME)
    2. COGNITO_USER_POOL_ID is NOT configured

    This ensures dev mode is IMPOSSIBLE in production Lambda.
    """
    is_lambda = "AWS_LAMBDA_FUNCTION_NAME" in os.environ
    cognito_configured = bool(os.getenv("COGNITO_USER_POOL_ID", "").strip())

    # Dev mode ONLY if: NOT in Lambda AND Cognito NOT configured
    is_dev = (not is_lambda) and (not cognito_configured)

    if is_dev:
        logger.info(
            "[DEV_AUTH] Local development mode enabled (Cognito not configured)"
        )

    return is_dev

def get_dev_claims(token: Optional[str]) -> Optional[Dict]:
    """
    Generate development claims for testing without Cognito.

    Returns None if not in dev mode (this will be the case in production Lambda).

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

    claims = {
        "sub": f"dev-{role}",
        "cognito:groups": groups,
        "email": f"dev-{role}@localhost",
        "aud": "dev-client",
        "token_use": "id",
    }

    logger.info(
        f"[DEV_AUTH] Generated dev claims for token: {token[:10]}..., groups: {groups}"
    )
    return claims

def validate_dev_token(
    token: Optional[str],
) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Validate a development token (only works in local dev mode).

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

    return (True, claims, None)
