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

    Credentials must be set as environment variables before running.
    This does NOT load .env files (removed for security).

    FAILS LOUDLY if .env.local exists (prevents accidental commits).
    """
    global _env_initialized

    if _env_initialized:
        return

    # SECURITY CHECK: Reject .env.local files (prevent credential leaks)
    import os
    from pathlib import Path
    env_file = Path(__file__).parent.parent / '.env.local'
    if env_file.exists():
        raise RuntimeError(
            f"SECURITY VIOLATION: .env.local file found.\n"
            f"Credentials in files can be accidentally committed to git.\n"
            f"DELETE the file immediately and use AWS Secrets Manager instead.\n"
            f"See LOCAL_CRED_SETUP.md for 5-minute setup."
        )

    _env_initialized = True
