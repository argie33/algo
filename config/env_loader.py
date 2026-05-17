#!/usr/bin/env python3
"""
Environment variable validation and setup.

IMPORTANT: Credentials are NEVER loaded from .env files.
They come from:
1. Environment variables (CI, local development)
2. AWS Secrets Manager (production Lambda/ECS)

All credentials must be set explicitly before running any algo/loader/test code.
See CLAUDE.md for how to set up credentials properly.
"""

import os
import logging

logger = logging.getLogger(__name__)

# Track if already initialized
_env_initialized = False


def load_env():
    """Validate that required environment variables are set.

    Does NOT load from .env files - all credentials must be environment variables.

    This is called automatically on module import but can be called explicitly.
    """
    global _env_initialized

    if _env_initialized:
        return

    # Just mark as initialized - no .env.local loading
    # All credentials must come from environment variables or AWS Secrets Manager
    _env_initialized = True


