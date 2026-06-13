"""Algo route handlers - modular architecture."""
import sys
import os
from pathlib import Path

# Add parent routes directory to path so algo_original can import routes.utils
_this_dir = Path(__file__).parent
_routes_dir = _this_dir.parent
if str(_routes_dir) not in sys.path:
    sys.path.insert(0, str(_routes_dir))

# Import all handler modules
from . import dashboard
from . import metrics
from . import admin
from . import analysis
from . import config
from . import market
from . import notifications
from . import orchestrator
from . import external

__all__ = [
    'dashboard',
    'metrics',
    'admin',
    'analysis',
    'config',
    'market',
    'notifications',
    'orchestrator',
    'external',
]
