#!/usr/bin/env python3

"""
Regime Manager — Single authoritative source for market regime and parameter adaptation.

Reads from market_exposure_daily.regime (computed by algo_market_exposure.py).
Maps regime to config multipliers that flow into PositionSizer, FilterPipeline, WeightOptimizer.
"""

import logging
from datetime import date as _date, datetime, timedelta
from typing import Dict, Optional, List, Tuple, Any

from utils.db_connection import get_db_connection
from config.credential_helper import get_db_config, get_db_password

logger = logging.getLogger(__name__)


class RegimeManager:
    """Market regime detection and parameter adaptation."""

    # Regime values from market_exposure_daily
    REGIMES = ['confirmed_uptrend', 'uptrend_under_pressure', 'caution', 'correction']

    # Parameter overrides by regime
    REGIME_PARAMS = {
        'confirmed_uptrend': {
            'position_size_mult': 1.0,    # Full size
            'max_hold_days_mult': 1.5,    # Let winners run (20d × 1.5 = 30d)
            'target_1_mult': 1.0,         # Standard 1.5R target
            'target_2_mult': 1.0,         # Standard 3.0R target
            'target_3_mult': 1.0,         # Standard 4.0R target
            'min_swing_score': 55,        # Standard bar
            'weight_update_alpha': 0.10,  # Normal adaptation speed
            'description': 'Bull market: full size, longer holds, aggressive targets',
        },
        'uptrend_under_pressure': {
            'position_size_mult': 0.75,   # Reduce size
            'max_hold_days_mult': 1.0,    # Standard hold (20d)
            'target_1_mult': 1.0,         # Standard targets
            'target_2_mult': 1.0,
            'target_3_mult': 1.0,
            'min_swing_score': 62,        # Higher bar
            'weight_update_alpha': 0.05,  # Slower adaptation
            'description': 'Uptrend weakening: reduce size, standard exits',
        },
        'caution': {
            'position_size_mult': 0.50,   # Half size
            'max_hold_days_mult': 0.75,   # Shorter holds (15d)
            'target_1_mult': 0.8,         # Lower targets
            'target_2_mult': 0.8,
            'target_3_mult': 0.8,
            'min_swing_score': 70,        # High bar only
            'weight_update_alpha': 0.05,  # Slow adaptation
            'description': 'VIX elevated or distribution days: defensive positioning',
        },
        'correction': {
            'position_size_mult': 0.0,    # No new entries
            'max_hold_days_mult': 0.5,    # Get out fast (10d)
            'target_1_mult': 0.6,         # Quick profit targets
            'target_2_mult': 0.6,
            'target_3_mult': 0.6,
            'min_swing_score': 80,        # Impossible bar
            'weight_update_alpha': 0.0,   # Freeze weights
            'description': 'Bear market: halt new entries, tight stops, quick exits',
        },
    }

    def __init__(self):
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        if not self.conn:
            self.conn = get_db_connection()
            self.cur = self.conn.cursor()

    def disconnect(self):
        """Close connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def get_current_regime(self, as_of_date: Optional[_date] = None) -> str:
        """
        Get current market regime.

        Reads from market_exposure_daily.regime (as_of_date or latest).

        Returns: 'confirmed_uptrend'|'uptrend_under_pressure'|'caution'|'correction'
        """
        self.connect()
        try:
            if as_of_date is None:
                as_of_date = _date.today()

            self.cur.execute(
                """SELECT regime FROM market_exposure_daily
                   WHERE date <= %s AND regime IS NOT NULL
                   ORDER BY date DESC LIMIT 1""",
                (as_of_date,),
            )
            row = self.cur.fetchone()
            regime = str(row[0]) if row and row[0] else 'confirmed_uptrend'

            if regime not in self.REGIMES:
                logger.warning(f"Unknown regime '{regime}', defaulting to confirmed_uptrend")
                regime = 'confirmed_uptrend'

            return regime

        except Exception as e:
            logger.warning(f"Could not fetch regime: {e}. Defaulting to confirmed_uptrend")
            return 'confirmed_uptrend'
        finally:
            self.disconnect()

    def get_regime_params(self, as_of_date: Optional[_date] = None) -> Dict[str, Any]:
        """Get parameter overrides for current regime."""
        regime = self.get_current_regime(as_of_date)
        return self.REGIME_PARAMS.get(regime, self.REGIME_PARAMS['confirmed_uptrend'])

    def get_position_size_multiplier(self, as_of_date: Optional[_date] = None) -> float:
        """Get position size multiplier (0.0 - 1.0)."""
        params = self.get_regime_params(as_of_date)
        return float(params['position_size_mult'])

    def get_adjusted_config(
        self,
        base_config: Dict[str, Any],
        as_of_date: Optional[_date] = None,
    ) -> Dict[str, Any]:
        """
        Return modified config dict with regime adjustments applied.

        Args:
            base_config: Base config dict (from AlgoConfig)
            as_of_date: Date for regime lookup

        Returns:
            Modified config dict with regime overrides
        """
        params = self.get_regime_params(as_of_date)
        config = base_config.copy()

        # Apply multipliers and overrides
        base_max_hold = int(config.get('max_hold_days', 20))
        config['max_hold_days'] = int(base_max_hold * params['max_hold_days_mult'])

        # Adjust target R-multiples
        config['t1_target_r_multiple'] = (
            float(config.get('t1_target_r_multiple', 1.5)) * params['target_1_mult']
        )
        config['t2_target_r_multiple'] = (
            float(config.get('t2_target_r_multiple', 3.0)) * params['target_2_mult']
        )
        config['t3_target_r_multiple'] = (
            float(config.get('t3_target_r_multiple', 4.0)) * params['target_3_mult']
        )

        # Override min swing score
        config['min_swing_score'] = params['min_swing_score']

        # Add metadata
        config['_regime_adjusted'] = True
        config['_regime'] = self.get_current_regime(as_of_date)
        config['_regime_position_size_mult'] = params['position_size_mult']
        config['_regime_weight_update_alpha'] = params['weight_update_alpha']

        return config

    def regime_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get regime history and transitions.

        Returns:
            [
                {
                    'date': date,
                    'regime': str,
                    'days_in_regime': int,
                    'transition': bool (True if regime changed from prior day),
                },
                ...
            ]
        """
        self.connect()
        try:
            start_date = _date.today() - timedelta(days=days)

            self.cur.execute(
                """
                SELECT DISTINCT ON (date) date, regime FROM market_exposure_daily
                WHERE date >= %s AND regime IS NOT NULL
                ORDER BY date DESC, created_at DESC
                """,
                (start_date,),
            )
            rows = self.cur.fetchall()

            history = []
            prev_regime = None
            days_in_regime = 0

            for date_val, regime in reversed(rows):
                transition = prev_regime is not None and prev_regime != regime
                if transition:
                    days_in_regime = 1
                else:
                    days_in_regime += 1

                history.append(
                    {
                        'date': date_val,
                        'regime': regime,
                        'days_in_regime': days_in_regime,
                        'transition': transition,
                    }
                )

                prev_regime = regime

            return history

        except Exception as e:
            logger.warning(f"Could not fetch regime history: {e}")
            return []
        finally:
            self.disconnect()

    def get_regime_strength(self, as_of_date: Optional[_date] = None) -> float:
        """
        Get confidence level (0-1) in current regime classification.

        Reads from market_exposure_daily.raw_score (0-100 scale).
        Returns: 0-1 confidence.
        """
        self.connect()
        try:
            if as_of_date is None:
                as_of_date = _date.today()

            self.cur.execute(
                """SELECT raw_score FROM market_exposure_daily
                   WHERE date <= %s AND raw_score IS NOT NULL
                   ORDER BY date DESC LIMIT 1""",
                (as_of_date,),
            )
            row = self.cur.fetchone()
            if row and row[0]:
                score = float(row[0])
                return min(1.0, max(0.0, score / 100.0))
            return 0.5  # Default to neutral confidence
        except Exception:
            return 0.5
        finally:
            self.disconnect()


if __name__ == "__main__":
    rm = RegimeManager()
    regime = rm.get_current_regime()
    params = rm.get_regime_params()
    logger.info(f"Current regime: {regime}")
    logger.info(f"Params: {params}")
    logger.info(f"Position size mult: {rm.get_position_size_multiplier()}")
