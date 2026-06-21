#!/usr/bin/env python3

"""
Regime Manager — Single authoritative source for market regime and parameter adaptation.

Reads from market_exposure_daily.regime (computed by algo_market_exposure.py).
Maps regime to config multipliers that flow into PositionSizer, ExposurePolicy, SwingTraderScore.
"""

import logging
from datetime import date as _date
from datetime import timedelta
from typing import Any, ClassVar, cast

import psycopg2

from algo.infrastructure.constants import (
    REGIME_HOLD_DAYS_CAUTION,
    REGIME_HOLD_DAYS_CONFIRMED_UPTREND,
    REGIME_HOLD_DAYS_CORRECTION,
    REGIME_HOLD_DAYS_UPTREND_UNDER_PRESSURE,
    REGIME_MIN_SWING_SCORE_CAUTION,
    REGIME_MIN_SWING_SCORE_CONFIRMED_UPTREND,
    REGIME_MIN_SWING_SCORE_CORRECTION,
    REGIME_MIN_SWING_SCORE_UPTREND_UNDER_PRESSURE,
    REGIME_POSITION_SIZE_CAUTION,
    REGIME_POSITION_SIZE_CONFIRMED_UPTREND,
    REGIME_POSITION_SIZE_CORRECTION,
    REGIME_POSITION_SIZE_UPTREND_UNDER_PRESSURE,
    REGIME_TARGET_CAUTION,
    REGIME_TARGET_CONFIRMED_UPTREND,
    REGIME_TARGET_CORRECTION,
    REGIME_TARGET_UPTREND_UNDER_PRESSURE,
    REGIME_WEIGHT_UPDATE_ALPHA_CAUTION,
    REGIME_WEIGHT_UPDATE_ALPHA_CONFIRMED_UPTREND,
    REGIME_WEIGHT_UPDATE_ALPHA_CORRECTION,
    REGIME_WEIGHT_UPDATE_ALPHA_UPTREND_UNDER_PRESSURE,
)
from utils.db import DatabaseContext


logger = logging.getLogger(__name__)


class RegimeManager:
    """Market regime detection and parameter adaptation."""

    # Regime values from market_exposure_daily
    REGIMES: ClassVar[list[str]] = [
        "confirmed_uptrend",
        "uptrend_under_pressure",
        "caution",
        "correction",
    ]

    # Parameter overrides by regime (see algo.infrastructure.constants for values and rationale)
    REGIME_PARAMS: ClassVar[dict[str, Any]] = {
        "confirmed_uptrend": {
            "position_size_mult": REGIME_POSITION_SIZE_CONFIRMED_UPTREND,
            "max_hold_days_mult": REGIME_HOLD_DAYS_CONFIRMED_UPTREND,
            "target_1_mult": REGIME_TARGET_CONFIRMED_UPTREND,
            "target_2_mult": REGIME_TARGET_CONFIRMED_UPTREND,
            "target_3_mult": REGIME_TARGET_CONFIRMED_UPTREND,
            "min_swing_score": REGIME_MIN_SWING_SCORE_CONFIRMED_UPTREND,
            "weight_update_alpha": REGIME_WEIGHT_UPDATE_ALPHA_CONFIRMED_UPTREND,
            "description": "Bull market: full size, longer holds, aggressive targets",
        },
        "uptrend_under_pressure": {
            "position_size_mult": REGIME_POSITION_SIZE_UPTREND_UNDER_PRESSURE,
            "max_hold_days_mult": REGIME_HOLD_DAYS_UPTREND_UNDER_PRESSURE,
            "target_1_mult": REGIME_TARGET_UPTREND_UNDER_PRESSURE,
            "target_2_mult": REGIME_TARGET_UPTREND_UNDER_PRESSURE,
            "target_3_mult": REGIME_TARGET_UPTREND_UNDER_PRESSURE,
            "min_swing_score": REGIME_MIN_SWING_SCORE_UPTREND_UNDER_PRESSURE,
            "weight_update_alpha": REGIME_WEIGHT_UPDATE_ALPHA_UPTREND_UNDER_PRESSURE,
            "description": "Uptrend weakening: reduce size, standard exits",
        },
        "caution": {
            "position_size_mult": REGIME_POSITION_SIZE_CAUTION,
            "max_hold_days_mult": REGIME_HOLD_DAYS_CAUTION,
            "target_1_mult": REGIME_TARGET_CAUTION,
            "target_2_mult": REGIME_TARGET_CAUTION,
            "target_3_mult": REGIME_TARGET_CAUTION,
            "min_swing_score": REGIME_MIN_SWING_SCORE_CAUTION,
            "weight_update_alpha": REGIME_WEIGHT_UPDATE_ALPHA_CAUTION,
            "description": "VIX elevated or distribution days: defensive positioning",
        },
        "correction": {
            "position_size_mult": REGIME_POSITION_SIZE_CORRECTION,
            "max_hold_days_mult": REGIME_HOLD_DAYS_CORRECTION,
            "target_1_mult": REGIME_TARGET_CORRECTION,
            "target_2_mult": REGIME_TARGET_CORRECTION,
            "target_3_mult": REGIME_TARGET_CORRECTION,
            "min_swing_score": REGIME_MIN_SWING_SCORE_CORRECTION,
            "weight_update_alpha": REGIME_WEIGHT_UPDATE_ALPHA_CORRECTION,
            "description": "Bear market: halt new entries, tight stops, quick exits",
        },
    }

    def get_current_regime(self, as_of_date: _date | None = None) -> str:
        """
        Get current market regime.

        Reads from market_exposure_daily.regime (as_of_date or latest).

        Returns: 'confirmed_uptrend'|'uptrend_under_pressure'|'caution'|'correction'
        """
        try:
            if as_of_date is None:
                as_of_date = _date.today()

            with DatabaseContext("read") as cur:
                cur.execute(
                    """SELECT regime FROM market_exposure_daily
                       WHERE date <= %s AND regime IS NOT NULL
                       ORDER BY date DESC LIMIT 1""",
                    (as_of_date,),
                )
                row = cur.fetchone()

            regime = str(row[0]) if row is not None and row[0] is not None else "caution"

            if regime not in self.REGIMES:
                logger.warning(f"Unknown regime '{regime}', defaulting to caution (conservative)")
                regime = "caution"

            return regime

        except (OSError, RuntimeError, ValueError) as e:
            logger.warning(f"Could not fetch regime: {e}. Defaulting to caution (conservative)")
            return "caution"

    def get_regime_params(self, as_of_date: _date | None = None) -> dict[str, Any]:
        """Get parameter overrides for current regime."""
        regime = self.get_current_regime(as_of_date)
        return cast(dict[str, Any], self.REGIME_PARAMS.get(regime, self.REGIME_PARAMS["caution"]))

    def get_position_size_multiplier(self, as_of_date: _date | None = None) -> float:
        """Get position size multiplier (0.0 - 1.0)."""
        params = self.get_regime_params(as_of_date)
        return float(params["position_size_mult"])

    def get_adjusted_config(
        self,
        base_config: dict[str, Any],
        as_of_date: _date | None = None,
    ) -> dict[str, Any]:
        """
        Return modified config dict with regime adjustments applied.

        Args:
            base_config: Base config dict (from AlgoConfig, must already have critical values)
            as_of_date: Date for regime lookup

        Returns:
            Modified config dict with regime overrides
        """
        # Fail-fast: base_config must have critical values (validated at init time)
        if "max_hold_days" not in base_config or base_config["max_hold_days"] is None:
            raise ValueError(
                "CRITICAL: max_hold_days missing from base config. "
                "Config must be validated before regime adaptation."
            )
        if "t1_target_r_multiple" not in base_config or base_config["t1_target_r_multiple"] is None:
            raise ValueError(
                "CRITICAL: t1_target_r_multiple missing from base config. "
                "Config must be validated before regime adaptation."
            )
        if "t2_target_r_multiple" not in base_config or base_config["t2_target_r_multiple"] is None:
            raise ValueError(
                "CRITICAL: t2_target_r_multiple missing from base config. "
                "Config must be validated before regime adaptation."
            )
        if "t3_target_r_multiple" not in base_config or base_config["t3_target_r_multiple"] is None:
            raise ValueError(
                "CRITICAL: t3_target_r_multiple missing from base config. "
                "Config must be validated before regime adaptation."
            )

        params = self.get_regime_params(as_of_date)
        config = base_config.copy()

        # Apply multipliers and overrides (using validated base values, no defaults)
        base_max_hold = int(base_config["max_hold_days"])
        config["max_hold_days"] = int(base_max_hold * params["max_hold_days_mult"])

        # Adjust target R-multiples (using validated base values, no defaults)
        config["t1_target_r_multiple"] = float(base_config["t1_target_r_multiple"]) * params["target_1_mult"]
        config["t2_target_r_multiple"] = float(base_config["t2_target_r_multiple"]) * params["target_2_mult"]
        config["t3_target_r_multiple"] = float(base_config["t3_target_r_multiple"]) * params["target_3_mult"]

        # Override min swing score
        config["min_swing_score"] = params["min_swing_score"]

        # Add metadata
        config["_regime_adjusted"] = True
        config["_regime"] = self.get_current_regime(as_of_date)
        config["_regime_position_size_mult"] = params["position_size_mult"]
        config["_regime_weight_update_alpha"] = params["weight_update_alpha"]

        return config

    def regime_history(self, days: int = 30) -> list[dict[str, Any]]:
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
        try:
            start_date = _date.today() - timedelta(days=days)

            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (date) date, regime FROM market_exposure_daily
                    WHERE date >= %s AND regime IS NOT NULL
                    ORDER BY date DESC, created_at DESC
                    """,
                    (start_date,),
                )
                rows = cur.fetchall()

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
                        "date": date_val,
                        "regime": regime,
                        "days_in_regime": days_in_regime,
                        "transition": transition,
                    }
                )

                prev_regime = regime

            return history

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"Failed to fetch regime history: {e}. Cannot compute regime transitions without historical data."
            ) from e

    def get_regime_strength(self, as_of_date: _date | None = None) -> float:
        """
        Get confidence level (0-1) in current regime classification.

        Reads from market_exposure_daily.raw_score (0-100 scale).
        Returns: 0-1 confidence.
        """
        try:
            if as_of_date is None:
                as_of_date = _date.today()

            with DatabaseContext("read") as cur:
                cur.execute(
                    """SELECT raw_score FROM market_exposure_daily
                       WHERE date <= %s AND raw_score IS NOT NULL
                       ORDER BY date DESC LIMIT 1""",
                    (as_of_date,),
                )
                row = cur.fetchone()

            if row is not None and row[0] is not None:
                score = float(row[0])
                return min(1.0, max(0.0, score / 100.0))
            raise RuntimeError(
                f"Market exposure score unavailable as of {as_of_date}. "
                "market_exposure_daily table empty or stale. "
                "Position sizing and entry thresholds cannot proceed without market regime data. "
                "Verify market_exposure_daily loader succeeded."
            )
        except RuntimeError:
            raise
        except (OSError, ValueError, KeyError) as e:
            raise RuntimeError(
                f"Failed to fetch market exposure confidence: {e}. "
                "Cannot compute position size multipliers without regime data."
            ) from e


if __name__ == "__main__":
    rm = RegimeManager()
    regime = rm.get_current_regime()
    params = rm.get_regime_params()
    logger.info(f"Current regime: {regime}")
    logger.info(f"Params: {params}")
    logger.info(f"Position size mult: {rm.get_position_size_multiplier()}")
