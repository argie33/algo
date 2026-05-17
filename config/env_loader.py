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
    """Initialize environment (no .env file loading).

    This function does nothing except mark initialization complete.
    All credentials must come from environment variables or AWS Secrets Manager.
    """
    global _env_initialized

    if _env_initialized:
        return

    # Just mark as initialized
    # NO .env.local loading - that was the security hole
    # Credentials MUST come from environment variables
    _env_initialized = True
