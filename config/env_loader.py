#!/usr/bin/env python3
"""
Environment initialization — NO file loading.

All credentials must come from:
1. AWS Secrets Manager (recommended for local dev + production)
2. Environment variables (set before running, for CI only)

For local development: See LOCAL_CRED_SETUP.md
"""

import logging

logger = logging.getLogger(__name__)

_env_initialized = False


def load_env():
    """Mark environment as initialized.

    Credentials must come from:
    1. AWS Secrets Manager (recommended)
    2. Environment variables (set in shell profile)

    Does NOT load .env files to prevent accidental git commits.
    """
    global _env_initialized

    if _env_initialized:
        return

    _env_initialized = True
