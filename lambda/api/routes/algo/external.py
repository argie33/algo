"""External data handlers - sentiment, economic calendar, evaluation, data quality, exposure policy."""
import sys
from pathlib import Path
_routes_dir = str(Path(__file__).parent.parent)
if _routes_dir not in sys.path:
    sys.path.insert(0, _routes_dir)

from algo_original import (
    _get_sentiment, _get_economic_calendar, _get_algo_evaluate,
    _get_data_quality, _get_exposure_policy
)

handle_sentiment = _get_sentiment
handle_economic_calendar = _get_economic_calendar
handle_evaluate = _get_algo_evaluate
handle_data_quality = _get_data_quality
handle_exposure_policy = _get_exposure_policy

__all__ = [
    'handle_sentiment', 'handle_economic_calendar', 'handle_evaluate',
    'handle_data_quality', 'handle_exposure_policy'
]
