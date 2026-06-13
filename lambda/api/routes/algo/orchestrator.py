"""Orchestrator handlers - execution history, patterns, stats."""
import sys
from pathlib import Path
_routes_dir = str(Path(__file__).parent.parent)
if _routes_dir not in sys.path:
    sys.path.insert(0, _routes_dir)

from algo_original import (
    _get_orchestrator_execution_recent, _get_orchestrator_execution_failed,
    _get_orchestrator_execution_details, _get_orchestrator_execution_patterns,
    _get_orchestrator_execution_stats
)

handle_execution_recent = _get_orchestrator_execution_recent
handle_execution_failed = _get_orchestrator_execution_failed
handle_execution_details = _get_orchestrator_execution_details
handle_execution_patterns = _get_orchestrator_execution_patterns
handle_execution_stats = _get_orchestrator_execution_stats

__all__ = [
    'handle_execution_recent', 'handle_execution_failed', 'handle_execution_details',
    'handle_execution_patterns', 'handle_execution_stats'
]
