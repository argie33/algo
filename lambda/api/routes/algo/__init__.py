"""Algo route handler - package structure for modular organization.

This package ensures Python imports this __init__.py when code does:
    from routes import algo
    # or
    module = __import__('routes.algo')

The __init__.py properly exports the handle() function from the main algo module,
fixing the issue where Python imports the package but the handle function wasn't available.
"""

import sys
from pathlib import Path

# Ensure parent routes directory is importable
_parent_routes_dir = str(Path(__file__).parent.parent)
if _parent_routes_dir not in sys.path:
    sys.path.insert(0, _parent_routes_dir)

# Import handle from algo module in parent directory
from algo import handle  # noqa: F401

__all__ = ['handle']
