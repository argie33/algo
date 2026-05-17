#!/usr/bin/env python3
"""
Centralized environment variable loading.

All modules should use this single source of truth for loading .env files.
Prevents duplicate loading patterns scattered across 20+ loader files.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Track if already loaded to avoid redundant loads
_env_loaded = False


def load_env():
    """Load .env.local from project root or local directory.

    Searches in order:
    1. ./.env.local (current directory)
    2. ../.env.local (parent directory)
    3. ../../.env.local (grandparent directory)

    Called automatically on first import, but can be called explicitly if needed.
    """
    global _env_loaded

    if _env_loaded:
        return

    # Try multiple locations
    search_paths = [
        Path(".env.local"),
        Path(__file__).parent / ".env.local",
        Path(__file__).parent.parent / ".env.local",
        Path(__file__).parent.parent.parent / ".env.local",
    ]

    for env_path in search_paths:
        if env_path.exists():
            load_dotenv(env_path)
            _env_loaded = True
            return

    # Not found, but that's OK - will use environment variables
    _env_loaded = True


# Load on import
load_env()
