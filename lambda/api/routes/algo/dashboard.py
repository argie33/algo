"""Dashboard endpoint handlers - status, trades, positions, performance, circuit breakers."""
import sys
from pathlib import Path
_routes_dir = str(Path(__file__).parent.parent)
if _routes_dir not in sys.path:
    sys.path.insert(0, _routes_dir)

from algo_original import (
    _get_last_run, _get_algo_status, _get_algo_trades, _get_algo_positions,
    _get_algo_performance, _get_circuit_breakers, _get_equity_curve, _get_data_status,
    _get_dashboard_signals
)

# Handler aliases that wrap the original functions
handle_last_run = _get_last_run
handle_status = _get_algo_status
handle_trades = _get_algo_trades
handle_positions = _get_algo_positions
handle_performance = _get_algo_performance
handle_circuit_breakers = _get_circuit_breakers
handle_equity_curve = _get_equity_curve
handle_data_status = _get_data_status
handle_dashboard_signals = _get_dashboard_signals

__all__ = [
    'handle_last_run', 'handle_status', 'handle_trades', 'handle_positions',
    'handle_performance', 'handle_circuit_breakers', 'handle_equity_curve',
    'handle_data_status', 'handle_dashboard_signals'
]
