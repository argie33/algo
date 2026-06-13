"""Market handlers - exposure, regime, factors."""
import sys
from pathlib import Path
_routes_dir = str(Path(__file__).parent.parent)
if _routes_dir not in sys.path:
    sys.path.insert(0, _routes_dir)

from algo_original import (
    _get_markets, _get_market, _get_market_factors
)

handle_markets = _get_markets
handle_market = _get_market
handle_market_factors = _get_market_factors

__all__ = ['handle_markets', 'handle_market', 'handle_market_factors']
