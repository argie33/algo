from __future__ import annotations

# Set up imports for Lambda API - ensures routes and api_utils are importable
import sys
from pathlib import Path

_lambda_api_dir = Path(__file__).parent
_project_root = _lambda_api_dir.parent.parent

_paths_to_add = [
    str(_lambda_api_dir),
    str(_project_root),
    "/var/task",
]

for path in _paths_to_add:
    if path not in sys.path:
        sys.path.insert(0, path)
