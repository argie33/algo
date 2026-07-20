"""Load environment variables from .env.local for local development.

This ensures local development credentials are available without
requiring users to manually source the .env.local file or set
environment variables manually.

CRITICAL: Must be imported BEFORE any boto3/AWS calls.
"""

import os
import sys
from pathlib import Path


def load_env_local() -> None:
    """Load .env.local file into environment variables.

    Supports both line-by-line loading (if python-dotenv not available)
    and dotenv library loading (if available).

    Safely handles:
    - Comments (#)
    - Empty lines
    - Values with spaces
    - Missing .env.local (no-op)
    """

    env_local_path = Path(__file__).parent.parent / ".env.local"

    if not env_local_path.exists():
        return

    # Try using dotenv library first (most robust)
    try:
        from dotenv import load_dotenv
        load_dotenv(env_local_path, override=False)
        return
    except ImportError:
        pass

    # Fallback: manual parsing (handles most cases)
    try:
        with open(env_local_path) as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                # Parse KEY=VALUE
                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                # Don't override existing environment variables
                if key and key not in os.environ:
                    os.environ[key] = value

    except Exception:
        pass


# Load immediately on import
load_env_local()
