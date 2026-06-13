"""Algo route handler package.

This __init__.py re-exports the handle() function from the parent routes/algo.py module.
When Python imports 'routes.algo', it loads this __init__.py which makes handle() available.
"""
import sys
from pathlib import Path
import importlib.util

# Get directories - add to sys.path ONLY api and root, NOT routes
# (routes/utils.py would shadow root/utils package if routes is in path)
_routes_dir = Path(__file__).parent.parent
_api_dir = _routes_dir.parent
_root_dir = _api_dir.parent.parent

# Setup sys.path for proper import resolution
for _path in [str(_root_dir), str(_api_dir)]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Load algo.py using importlib with proper import path
# Use a synthetic module that won't conflict with the package name
_algo_py_path = str(_routes_dir / "algo.py")
_spec = importlib.util.spec_from_file_location("algo_module_impl", _algo_py_path)
if _spec and _spec.loader:
    _algo_module = importlib.util.module_from_spec(_spec)
    # Set module attributes so imports within algo.py work correctly
    _algo_module.__path__ = [str(_routes_dir)]
    _spec.loader.exec_module(_algo_module)
    handle = _algo_module.handle
else:
    raise ImportError(f"Could not load algo.py from {_algo_py_path}")

__all__ = ['handle']
