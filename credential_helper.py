#!/usr/bin/env python3
"""
Unified credential handling with proper fallbacks.

Supports multiple environments:
- CI (GitHub Actions): Uses DB_PASSWORD env variable
- Local dev: Uses credential_manager (AWS Secrets Manager wrapper)
- Testing: Uses defaults
- Lambda: Uses DATABASE_SECRET_ARN for Secrets Manager
"""

import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_CACHED_CREDS: Optional[Dict] = None


def get_db_password() -> str:
    """Get database password with proper fallbacks (environment-aware).

    Priority:
    1. DB_PASSWORD environment variable (CI, Lambda env injection)
    2. credential_manager (local dev, AWS Secrets Manager)
    3. Fallback (testing, local dev without creds)

    Returns:
        str: Database password
    """
    # 1. Try environment variable first (CI/Lambda)
    password = os.getenv("DB_PASSWORD")
    if password:
        return password

    # 2. Try credential_manager (local dev with AWS access)
    try:
        from credential_manager import get_credential_manager
        cm = get_credential_manager()
        if cm:
            creds = cm.get_db_credentials()
            if creds and isinstance(creds, dict):
                pwd = creds.get("password")
                if pwd:
                    return pwd
    except Exception as e:
        logger.debug(f"credential_manager failed (expected in some environments): {e}")

    # 3. No fallback — require explicit configuration
    password_fallback = os.getenv("DB_PASSWORD_FALLBACK")
    if password_fallback:
        return password_fallback

    raise ValueError(
        "Database password not available. Please set: "
        "DB_PASSWORD (env), DB_PASSWORD_FALLBACK (env), or configure AWS Secrets Manager"
    )


def get_db_config() -> Dict[str, any]:
    """Get full database configuration with proper fallbacks.

    Returns:
        dict: Database configuration with host, port, user, password, database
    """
    global _CACHED_CREDS

    if _CACHED_CREDS:
        return _CACHED_CREDS

    config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": get_db_password(),
        "database": os.getenv("DB_NAME", "stocks"),
    }

    _CACHED_CREDS = config
    return config


def clear_cache():
    """Clear cached credentials (useful for testing)."""
    global _CACHED_CREDS
    _CACHED_CREDS = None


if __name__ == "__main__":
    config = get_db_config()
    print(f"DB Config: {config['host']}:{config['port']}/{config['database']}")
