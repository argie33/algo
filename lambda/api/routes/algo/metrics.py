"""Metrics handlers - portfolio, risk, performance analytics."""
import sys
from pathlib import Path
_routes_dir = str(Path(__file__).parent.parent)
if _routes_dir not in sys.path:
    sys.path.insert(0, _routes_dir)

from algo_original import (
    _get_algo_portfolio, _get_algo_metrics, _get_risk_metrics, _get_performance_analytics
)

handle_portfolio = _get_algo_portfolio
handle_metrics = _get_algo_metrics
handle_risk_metrics = _get_risk_metrics
handle_performance_analytics = _get_performance_analytics

__all__ = [
    'handle_portfolio', 'handle_metrics', 'handle_risk_metrics', 'handle_performance_analytics'
]
