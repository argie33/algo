#!/usr/bin/env python3
"""
Environment variable validation and initialization.

CRITICAL: This file does NOT load .env.local or any .env files.
All credentials must come from:
1. Environment variables (set before running code)
2. AWS Secrets Manager (production Lambda/ECS)

Before running code, ensure required environment variables are set:
- Database: DB_PASSWORD, DB_HOST, DB_PORT, DB_USER, DB_NAME
- Trading: APCA_API_KEY_ID, APCA_API_SECRET_KEY
- Logging: LOG_LEVEL (optional)

See CLAUDE.md for setup instructions.
"""

import logging

logger = logging.getLogger(__name__)

_env_initialized = False


def load_env():
    """Initialize environment by loading .env.local for local development.

    Priority:
    1. .env.local (for local development)
    2. Environment variables (for AWS/production)
    3. AWS Secrets Manager (production only)
    """
    global _env_initialized

    if _env_initialized:
        return

    # Load .env.local for local development
    import os
    from pathlib import Path

    env_file = Path(__file__).parent.parent / '.env.local'
    if env_file.exists():
        logger.debug(f"Loading .env.local from {env_file}")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")
        logger.debug("Loaded environment from .env.local")

    _env_initialized = True
