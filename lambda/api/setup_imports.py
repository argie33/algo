"""
Lambda API import setup helper.

This module handles setting up sys.path once for the Lambda API runtime.
All Lambda API modules should import this at the module level to ensure proper import resolution.
"""

import sys
from pathlib import Path


# Determine the project root based on this file's location
# File location: /lambda/api/setup_imports.py
# Project root: /
_lambda_api_dir = Path(__file__).parent
_project_root = _lambda_api_dir.parent.parent

# Ensure lambda/api and project root are in sys.path for imports to work
# Order matters: lambda/api first (for local routes and api_utils), then project root (for utils, algo, etc.)
_paths_to_add = [
    str(_lambda_api_dir),  # /lambda/api - for routes, api_utils modules
    str(_project_root),  # / - for utils, algo, and other packages
    "/var/task",  # Lambda runtime path (AWS adds this, but explicit for clarity)
]

for path in _paths_to_add:
    if path not in sys.path:
        sys.path.insert(0, path)
