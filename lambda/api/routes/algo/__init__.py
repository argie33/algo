"""Algo route handler package.

This __init__.py re-exports the handle() function from the parent routes/algo.py module.
When Python imports 'routes.algo', it loads this __init__.py which makes handle() available.
"""
import sys
from pathlib import Path
import importlib.util

# Get the routes directory (parent of this algo/ package)
_routes_dir = Path(__file__).parent.parent

# Add routes directory to path
_routes_path = str(_routes_dir)
if _routes_path not in sys.path:
    sys.path.insert(0, _routes_path)

# Load the algo.py module from the routes directory using importlib
_algo_py_path = str(_routes_dir / "algo.py")
_spec = importlib.util.spec_from_file_location("_algo_main", _algo_py_path)
if _spec and _spec.loader:
    _algo_module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_algo_module)
    handle = _algo_module.handle
else:
    raise ImportError(f"Could not load algo.py from {_algo_py_path}")

__all__ = ['handle']
