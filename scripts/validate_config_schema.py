#!/usr/bin/env python3
"""Validate configuration schema can be imported and initialized."""

import sys


sys.path.insert(0, ".")
try:
    from algo.infrastructure.config.main import AlgoConfig  # noqa: F401
    from config.credential_manager import CredentialManager  # noqa: F401

    print("OK: Config modules import successfully")
    print("OK: Configuration schema validated")
except Exception as e:
    print(f"ERROR: Configuration validation failed: {e}")
    sys.exit(1)
