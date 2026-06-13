"""Algo route handlers - re-export handle function from algo.py module.

This __init__.py MUST export 'handle' so that api_router.py can do:
    from routes import algo
    algo.handle(...)
"""
import sys
from pathlib import Path
import importlib.util

# Get paths
_algo_init = Path(__file__)
_routes_dir = _algo_init.parent.parent.absolute()  # routes directory
_api_dir = _algo_init.parent.parent.parent.absolute()  # api directory
_root_dir = _algo_init.parent.parent.parent.parent.parent.absolute()  # project root

# Add to sys.path
for _dir in [str(_api_dir), str(_root_dir)]:
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

# Import handle from algo.py module (not this package) using importlib to avoid circular import
_algo_py_path = str(_routes_dir / "algo.py")
_spec = importlib.util.spec_from_file_location("algo_module", _algo_py_path)
_algo_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_algo_module)
handle = _algo_module.handle

# Also import submodules for modular organization
from . import dashboard, metrics, admin, analysis, config, market, notifications, orchestrator, external

__all__ = ['handle', 'dashboard', 'metrics', 'admin', 'analysis', 'config', 'market', 'notifications', 'orchestrator', 'external']
