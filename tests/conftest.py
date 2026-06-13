"""Pytest configuration for all tests.

This file helps pytest discover and import project modules correctly.
With proper package installation (pip install -e .), explicit path setup shouldn't be needed,
but this provides a safety net for different test execution contexts.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path for imports to work
_test_dir = Path(__file__).parent
_project_root = _test_dir.parent

if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Also add lambda/api for Lambda-specific tests
_lambda_api = _project_root / "lambda" / "api"
if str(_lambda_api) not in sys.path:
    sys.path.insert(0, str(_lambda_api))
