#!/usr/bin/env python3
"""
Environment initialization (NO .env file loading).

IMPORTANT: This does NOT load .env.local files.
All credentials must come from:
1. Environment variables (set before running)
2. AWS Secrets Manager (production Lambda/ECS)

This prevents accidental credential commits into git.
"""

import logging

logger = logging.getLogger(__name__)

_env_initialized = False


def load_env():
    """Initialize environment - does NOT load .env files.

    All credentials must be set explicitly via environment variables
    or provided by AWS Secrets Manager in production.
    """
    global _env_initialized

    if _env_initialized:
        return

    # Just mark as initialized
    # No .env.local loading - credentials come from env vars or Secrets Manager
    _env_initialized = True


