"""Algo route handler.

This package ensures that Python can import routes.algo correctly.
The handle() function is imported from the main algo.py module in the parent directory.
"""

# Import handle from the algo module that should be in the parent routes directory
# This must be done carefully to avoid circular imports
import sys
import os

# Get the routes directory (parent of this __init__.py's directory)
_this_dir = os.path.dirname(os.path.abspath(__file__))
_routes_dir = os.path.dirname(_this_dir)

# Make sure parent routes dir is in path
if _routes_dir not in sys.path:
    sys.path.insert(0, _routes_dir)

# Import the handle function from algo module
# We use __import__ to explicitly import the algo.py module from the routes directory
try:
    # Load algo.py from the same directory level as this algo/ package
    import importlib.util
    spec = importlib.util.spec_from_file_location("_algo_main", os.path.join(_routes_dir, "algo.py"))
    _algo_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_algo_main)
    handle = _algo_main.handle
except Exception as e:
    raise ImportError(f"Failed to import handle from algo.py: {e}")

__all__ = ['handle']
