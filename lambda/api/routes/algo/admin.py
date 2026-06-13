"""Admin handlers - patrol, audit logs."""
import sys
from pathlib import Path
_routes_dir = str(Path(__file__).parent.parent)
if _routes_dir not in sys.path:
    sys.path.insert(0, _routes_dir)

from algo_original import (
    _trigger_data_patrol, _get_patrol_log, _get_algo_audit_log
)

handle_trigger_patrol = _trigger_data_patrol
handle_patrol_log = _get_patrol_log
handle_audit_log = _get_algo_audit_log

__all__ = ['handle_trigger_patrol', 'handle_patrol_log', 'handle_audit_log']
