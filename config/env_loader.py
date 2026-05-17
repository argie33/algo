#!/usr/bin/env python3
"""
Environment variable validation and initialization.

CRITICAL: This does NOT load .env.local (removed for security).
All credentials must come from:
1. Environment variables (set before running code)
2. AWS Secrets Manager (production Lambda/ECS)

Before running code, set required environment variables:
- Database: DB_PASSWORD, DB_HOST, DB_PORT, DB_USER, DB_NAME
- Trading: APCA_API_KEY_ID, APCA_API_SECRET_KEY

See CLAUDE.md for setup instructions.
"""

import logging

logger = logging.getLogger(__name__)

_env_initialized = False


def load_env():
    """Mark environment as initialized.

    Credentials must be set as environment variables before running.
    This does NOT load .env files (removed for security).
    """
    global _env_initialized

    if _env_initialized:
        return

    _env_initialized = True
