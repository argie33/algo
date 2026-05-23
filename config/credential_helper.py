#!/usr/bin/env python3
"""
Unified credential handling with proper fallbacks.

Supports multiple environments:
- CI (GitHub Actions): Uses DB_PASSWORD env variable
- Local dev: Uses .env.local (auto-loaded) or credential_manager (AWS Secrets Manager wrapper)
- Testing: Uses defaults
- Lambda: Uses DATABASE_SECRET_ARN for Secrets Manager
"""

import os
import logging
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Auto-load .env.local for local development ONLY
# Production MUST use AWS Secrets Manager or explicit environment variables
def _load_env_local():
    """Load .env.local file only in local development (never in CI/Lambda/Prod).

    This is ONLY for local convenience. Production environments MUST NOT rely on .env files.
    Use AWS Secrets Manager or explicit environment variables instead.
    """
    # Only load .env.local in local development mode
    # Skip if running in: Lambda (AWS_LAMBDA_FUNCTION_NAME), CI (CI=true), or explicit env override
    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME') or \
       os.environ.get('CI') or \
       os.environ.get('DISABLE_ENV_LOCAL_LOADING'):
        return  # Skip .env.local in production environments

    env_local_paths = [
        Path.cwd() / ".env.local",  # Current directory
        Path(__file__).parent.parent / ".env.local",  # Project root
    ]

    for env_path in env_local_paths:
        if env_path.exists():
            try:
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            key, _, value = line.partition("=")
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            if key and key not in os.environ:
                                os.environ[key] = value
                logger.debug(f"Loaded .env.local from {env_path} (LOCAL DEV ONLY)")
                break
            except Exception as e:
                logger.debug(f"Failed to load {env_path}: {e}")

_load_env_local()

_CACHED_CREDS: Optional[Dict] = None

# Database configuration - all from environment, no silent defaults for safety
# These MUST be explicitly set before credential_helper is used
DEFAULT_DB_PORT = "5432"  # Port has a sensible default
DEFAULT_DB_USER = "stocks"  # User has a sensible default
DEFAULT_DB_NAME = "stocks"  # Database name has a sensible default
# NOTE: DB_HOST does NOT have a default - must be explicitly set per CLAUDE.md rules


def get_db_password() -> str:
    """Get database password with proper fallbacks (environment-aware).

    Priority:
    1. credential_manager via DATABASE_SECRET_ARN (Lambda/production, reads latest from Secrets Manager)
    2. credential_manager fallback (local dev, AWS Secrets Manager)
    3. DB_PASSWORD environment variable (CI fallback, legacy)
    4. Fallback (testing, local dev without creds)

    Returns:
        str: Database password
    """
    # 1. Try credential_manager via DATABASE_SECRET_ARN (highest priority - always fresh from Secrets Manager)
    try:
        from config.credential_manager import get_credential_manager
        cm = get_credential_manager()
        if cm:
            creds = cm.get_db_credentials()
            if creds and isinstance(creds, dict):
                pwd = creds.get("password")
                if pwd:
                    return pwd
    except Exception as e:
        logger.debug(f"credential_manager failed (expected in some environments): {e}")

    # 2. Try environment variable as fallback (CI, legacy Lambda deployments)
    password = os.getenv("DB_PASSWORD")
    if password is not None:
        logger.debug("Using DB_PASSWORD env var (legacy fallback - consider using DATABASE_SECRET_ARN)")
        return password

    # 3. Fallback for testing
    password_fallback = os.getenv("DB_PASSWORD_FALLBACK")
    if password_fallback:
        return password_fallback

    raise ValueError(
        "Database password not available. Please set: "
        "DATABASE_SECRET_ARN (Lambda/AWS), DB_PASSWORD (env fallback), or configure AWS Secrets Manager"
    )


def get_db_config() -> Dict[str, any]:
    """Get full database configuration with proper fallbacks.

    Returns:
        dict: Database configuration with host, port, user, password, database

    Raises:
        ValueError: If DB_HOST is not explicitly set
    """
    global _CACHED_CREDS

    if _CACHED_CREDS:
        return _CACHED_CREDS

    # DB_HOST is REQUIRED - no default to localhost for safety
    db_host = os.getenv("DB_HOST")
    if not db_host:
        raise ValueError(
            "DB_HOST environment variable is required but not set. "
            "Please set DB_HOST to your database hostname before using credential_helper."
        )

    # Parse DB_HOST in case it includes port (e.g., "hostname:5432")
    # Extract just the hostname for DNS resolution
    if ":" in db_host:
        parsed_host, parsed_port = db_host.rsplit(":", 1)
        try:
            # If port was provided in hostname, use it
            parsed_port = int(parsed_port)
        except ValueError:
            # Not a valid port number, treat whole thing as hostname
            parsed_host = db_host
            parsed_port = int(os.getenv("DB_PORT", DEFAULT_DB_PORT))
    else:
        parsed_host = db_host
        parsed_port = int(os.getenv("DB_PORT", DEFAULT_DB_PORT))

    # Override port from env var if explicitly provided
    if os.getenv("DB_PORT"):
        parsed_port = int(os.getenv("DB_PORT"))

    config = {
        "host": parsed_host,
        "port": parsed_port,
        "user": os.getenv("DB_USER", DEFAULT_DB_USER),
        "password": get_db_password(),
        "database": os.getenv("DB_NAME", DEFAULT_DB_NAME),
    }

    # RDS Proxy and SSL configuration
    # Use 'prefer' for RDS Proxy to attempt SSL but allow fallback to unencrypted
    # This avoids certificate validation issues while maintaining security where available
    if "proxy-" in parsed_host:
        config["sslmode"] = "prefer"  # Try SSL, but don't fail if unavailable
    elif os.getenv("DB_SSL", "").lower() in ("true", "require"):
        config["sslmode"] = "require"

    _CACHED_CREDS = config
    return config


def clear_cache():
    """Clear cached credentials (useful for testing)."""
    global _CACHED_CREDS
    _CACHED_CREDS = None


if __name__ == "__main__":
    config = get_db_config()
    logger.info(f"DB Config: {config['host']}:{config['port']}/{config['database']}")
