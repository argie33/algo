#!/usr/bin/env python3
"""
Market Regime Detection and Dynamic Scoring Weights.

Detects whether market is in BULL, BEAR, or SIDEWAYS regime,
then adjusts composite score weighting accordingly.

Regimes:
- BULL: SPY > 200-day SMA, positive momentum → favor growth/momentum
- BEAR: SPY < 200-day SMA, negative momentum → favor quality/stability
- SIDEWAYS: Range-bound → neutral/balanced weights
"""

from datetime import date, timedelta
from typing import Dict, Optional, Literal
import logging

logger = logging.getLogger(__name__)

# Default weights (neutral/sideways)
DEFAULT_WEIGHTS = {
    'momentum': 0.20,
    'growth': 0.19,
    'stability': 0.19,
    'value': 0.12,
    'positioning': 0.15,
    'quality': 0.15,
}

# Bull market weights: favor momentum and growth
BULL_WEIGHTS = {
    'momentum': 0.25,       # +5% (higher momentum in uptrends)
    'growth': 0.22,        # +3%
    'positioning': 0.18,   # +3%
    'stability': 0.12,     # -7% (less protective needed)
    'value': 0.10,         # -2% (less focus on bargains)
    'quality': 0.13,       # -2%
}

# Bear market weights: favor stability and quality
BEAR_WEIGHTS = {
    'momentum': 0.12,      # -8% (lower in downtrends)
    'growth': 0.12,        # -7%
    'stability': 0.25,     # +6% (capital preservation)
    'quality': 0.22,       # +7% (strong fundamentals protect)
    'value': 0.14,         # +2% (bargains available)
    'positioning': 0.15,   # (unchanged)
}

# Sideways market weights: balanced
SIDEWAYS_WEIGHTS = DEFAULT_WEIGHTS


class MarketRegimeDetector:
    """Detects market regime from price/indicator data."""

    def __init__(self, cur=None):
        self.cur = cur
        self._regime_cache = {}

    def detect_regime(self, eval_date: date, lookback_sma: int = 200, lookback_momentum: int = 60) -> Literal['BULL', 'BEAR', 'SIDEWAYS']:
        """
        Detect market regime based on:
        1. SPY price vs its 200-day SMA
        2. SPY momentum (price change over last 60 days)
        3. Volatility trend

        Returns: 'BULL', 'BEAR', or 'SIDEWAYS'
        """
        cache_key = str(eval_date)
        if cache_key in self._regime_cache:
            return self._regime_cache[cache_key]

        try:
            if not self.cur:
                return 'SIDEWAYS'  # Default if no DB connection

            # Get SPY data
            self.cur.execute("""
                SELECT date, close FROM price_daily
                WHERE symbol = 'SPY' AND date <= %s
                ORDER BY date DESC LIMIT %s
            """, (eval_date, max(lookback_sma, lookback_momentum) + 10))

            rows = list(reversed(self.cur.fetchall()))
            if len(rows) < lookback_sma:
                return 'SIDEWAYS'

            closes = [float(r[1]) for r in rows]
            current_price = closes[-1]

            # Calculate 200-day SMA
            sma_200 = sum(closes[-lookback_sma:]) / lookback_sma if len(closes) >= lookback_sma else current_price

            # Calculate 60-day momentum
            momentum_val = (closes[-1] / closes[-lookback_momentum] - 1) * 100 if len(closes) >= lookback_momentum else 0

            # Determine regime
            is_above_sma = current_price > sma_200
            is_positive_momentum = momentum_val > 2  # > 2% gain over 60 days

            if is_above_sma and is_positive_momentum:
                regime = 'BULL'
            elif not is_above_sma and momentum_val < -2:  # < -2% loss
                regime = 'BEAR'
            else:
                regime = 'SIDEWAYS'

            logger.info(f"Market regime for {eval_date}: {regime} (SPY: {current_price:.2f}, SMA200: {sma_200:.2f}, 60d momentum: {momentum_val:.1f}%)")

            self._regime_cache[cache_key] = regime
            return regime

        except Exception as e:
            logger.debug(f"Could not detect market regime: {e}")
            return 'SIDEWAYS'

    def get_weights(self, regime: Optional[str] = None, eval_date: Optional[date] = None) -> Dict[str, float]:
        """
        Get composite score weights for the given regime.

        If regime not specified, will detect it from eval_date.
        """
        if regime is None:
            regime = self.detect_regime(eval_date or date.today())

        weights_map = {
            'BULL': BULL_WEIGHTS,
            'BEAR': BEAR_WEIGHTS,
            'SIDEWAYS': SIDEWAYS_WEIGHTS,
        }

        return weights_map.get(regime, DEFAULT_WEIGHTS)


def get_dynamic_weights(eval_date: date, cur=None) -> Dict[str, float]:
    """
    Convenience function: detect regime and return appropriate weights.

    Returns a dict with keys: momentum, growth, stability, value, positioning, quality
    All values sum to 1.0.
    """
    detector = MarketRegimeDetector(cur=cur)
    regime = detector.detect_regime(eval_date)
    return detector.get_weights(regime)
