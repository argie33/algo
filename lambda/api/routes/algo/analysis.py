"""Analysis handlers - swing scores, rejection funnel, sector analysis, pre-trade impact."""
import sys
from pathlib import Path
_routes_dir = str(Path(__file__).parent.parent)
if _routes_dir not in sys.path:
    sys.path.insert(0, _routes_dir)

from algo_original import (
    _get_swing_scores, _get_swing_scores_history, _get_rejection_funnel,
    _get_sector_rotation, _get_sector_breadth, _get_sector_position_warnings,
    _analyze_pre_trade_impact, _get_sector_stage2, _get_rejection_reason_description
)

handle_swing_scores = _get_swing_scores
handle_swing_scores_history = _get_swing_scores_history
handle_rejection_funnel = _get_rejection_funnel
handle_sector_rotation = _get_sector_rotation
handle_sector_breadth = _get_sector_breadth
handle_sector_position_warnings = _get_sector_position_warnings
handle_pre_trade_impact = _analyze_pre_trade_impact
handle_sector_stage2 = _get_sector_stage2

__all__ = [
    'handle_swing_scores', 'handle_swing_scores_history', 'handle_rejection_funnel',
    'handle_sector_rotation', 'handle_sector_breadth', 'handle_sector_position_warnings',
    'handle_pre_trade_impact', 'handle_sector_stage2'
]
