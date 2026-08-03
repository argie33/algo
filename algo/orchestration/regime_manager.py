#!/usr/bin/env python3

"""
Regime Manager - Single authoritative source for market regime and parameter adaptation.

Reads from market_exposure_daily.regime (computed by algo_market_exposure.py).
Maps regime to config multipliers that flow into PositionSizer and ExposurePolicy.
"""

import logging
from datetime import date as _date
from datetime import datetime as _datetime
from datetime import timedelta
from typing import Any, ClassVar, cast

import psycopg2

from algo.infrastructure import MarketCalendar
from algo.infrastructure.constants import (
    REGIME_HOLD_DAYS_CAUTION,
    REGIME_HOLD_DAYS_CONFIRMED_UPTREND,
    REGIME_HOLD_DAYS_CORRECTION,
    REGIME_HOLD_DAYS_UPTREND_UNDER_PRESSURE,
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
from utils.infrastructure.timezone import EASTERN_TZ

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
            "weight_update_alpha": REGIME_WEIGHT_UPDATE_ALPHA_CONFIRMED_UPTREND,
            "description": "Bull market: full size, longer holds, aggressive targets",
        },
        "uptrend_under_pressure": {
            "position_size_mult": REGIME_POSITION_SIZE_UPTREND_UNDER_PRESSURE,
            "max_hold_days_mult": REGIME_HOLD_DAYS_UPTREND_UNDER_PRESSURE,
            "target_1_mult": REGIME_TARGET_UPTREND_UNDER_PRESSURE,
            "target_2_mult": REGIME_TARGET_UPTREND_UNDER_PRESSURE,
            "target_3_mult": REGIME_TARGET_UPTREND_UNDER_PRESSURE,
            "weight_update_alpha": REGIME_WEIGHT_UPDATE_ALPHA_UPTREND_UNDER_PRESSURE,
            "description": "Uptrend weakening: reduce size, standard exits",
        },
        "caution": {
            "position_size_mult": REGIME_POSITION_SIZE_CAUTION,
            "max_hold_days_mult": REGIME_HOLD_DAYS_CAUTION,
            "target_1_mult": REGIME_TARGET_CAUTION,
            "target_2_mult": REGIME_TARGET_CAUTION,
            "target_3_mult": REGIME_TARGET_CAUTION,
            "weight_update_alpha": REGIME_WEIGHT_UPDATE_ALPHA_CAUTION,
            "description": "VIX elevated or distribution days: defensive positioning",
        },
        "correction": {
            "position_size_mult": REGIME_POSITION_SIZE_CORRECTION,
            "max_hold_days_mult": REGIME_HOLD_DAYS_CORRECTION,
            "target_1_mult": REGIME_TARGET_CORRECTION,
            "target_2_mult": REGIME_TARGET_CORRECTION,
            "target_3_mult": REGIME_TARGET_CORRECTION,
            "weight_update_alpha": REGIME_WEIGHT_UPDATE_ALPHA_CORRECTION,
            "description": "Bear market: halt new entries, tight stops, quick exits",
        },
    }

    @staticmethod
    def _expected_regime_date(as_of_date: _date) -> _date:
        """Most recent trading day whose market_exposure_daily row should already exist.

        market_exposure_daily is written once per trading day by the EOD loader (~4:05 PM ET).
        A naive "must be <=1 calendar day old" check false-halts every Monday (Friday's data is
        3 calendar days old) and after any holiday - mirrors the trading-day-aware fix already
        applied to price_daily freshness checks in phase1_data_freshness.py (Session 239/288).
        """
        now_et = _datetime.now(EASTERN_TZ)
        if as_of_date == now_et.date() and MarketCalendar.is_trading_day(as_of_date) and now_et.hour < 16:
            # Same trading day, before EOD close: today's row isn't published yet - the most
            # recent COMPLETE row is the prior trading day's.
            candidate = as_of_date - timedelta(days=1)
        else:
            candidate = as_of_date

        while not MarketCalendar.is_trading_day(candidate):
            candidate -= timedelta(days=1)
        return candidate

    def get_current_regime(self, as_of_date: _date | None = None) -> str:
        """
        Get current market regime.

        Reads from market_exposure_daily.regime (as_of_date or latest).

        Returns: 'confirmed_uptrend'|'uptrend_under_pressure'|'caution'|'correction'

        FAIL-FAST: Raises RuntimeError if market exposure regime data is unavailable.
        Market regime is critical for position sizing - missing data must halt trading.
        """
        try:
            if as_of_date is None:
                # Eastern Time, not system-local date.today() - same bug class already fixed
                # elsewhere in this codebase (see algo/trading/pretrade_checks.py, and prior
                # sessions' "N more date.today()-instead-of-Eastern-Time instances" fixes).
                # This file already uses _datetime.now(EASTERN_TZ) correctly in _expected_regime_date()
                # above; a server not running in America/New_York (UTC in AWS, Central on this
                # dev machine) could resolve "today" to the wrong calendar day near midnight ET,
                # looking up the wrong day's regime and feeding a stale/wrong position-size
                # multiplier into position sizing.
                as_of_date = _datetime.now(EASTERN_TZ).date()

            with DatabaseContext("read") as cur:
                # GOVERNANCE: Must check data_unavailable flag before using regime data
                cur.execute(
                    """SELECT regime, date, data_unavailable, reason FROM market_exposure_daily
                       WHERE date <= %s AND regime IS NOT NULL
                       ORDER BY date DESC LIMIT 1""",
                    (as_of_date,),
                )
                row = cur.fetchone()

            if row is None or row[0] is None:
                raise RuntimeError(
                    f"Market regime data unavailable for {as_of_date}. "
                    f"market_exposure_daily table has no regime computed. "
                    f"Phase 4 (market exposure calculation) must complete successfully before trading."
                )

            # GOVERNANCE ENFORCEMENT: Fail-fast if data marked unavailable
            regime_str, data_date, data_unavailable, reason = row[0], row[1], row[2], row[3]
            if data_unavailable:
                raise RuntimeError(
                    f"Market regime data marked unavailable for {data_date}: {reason or 'no reason provided'}. "
                    f"Cannot determine trading regime without valid market exposure analysis."
                )

            regime = str(regime_str)
            expected_date = self._expected_regime_date(as_of_date)
            if data_date < expected_date:
                age_days = (as_of_date - data_date).days
                raise RuntimeError(
                    f"Market regime data too stale: latest is {data_date} ({age_days} calendar day(s) old), "
                    f"expected data for {expected_date} or later (trading-day aware). "
                    f"EOD loader must run to provide fresh market exposure analysis."
                )

            if regime not in self.REGIMES:
                raise RuntimeError(
                    f"Market regime '{regime}' is invalid. "
                    f"Expected one of: {', '.join(self.REGIMES)}. "
                    f"Check market_exposure_daily computation - regime field corrupt."
                )

            return regime

        except (OSError, RuntimeError, ValueError, psycopg2.Error) as e:
            logger.critical(f"Regime fetch CRITICAL FAILURE: {e}")
            raise RuntimeError(f"[REGIME] Failed to determine market regime (cannot trade without regime): {e}") from e

    def get_regime_params(self, as_of_date: _date | None = None) -> dict[str, Any]:
        """Get parameter overrides for current regime.

        FAIL-FAST: Raises KeyError if regime is not in REGIME_PARAMS.
        All valid regimes must be defined in REGIME_PARAMS.
        """
        regime = self.get_current_regime(as_of_date)
        if regime not in self.REGIME_PARAMS:
            raise RuntimeError(
                f"CRITICAL: Regime '{regime}' exists in market_exposure_daily but has no parameter mapping. "
                f"REGIME_PARAMS must define parameters for all valid regimes: {list(self.REGIME_PARAMS.keys())}"
            )
        return cast(
            dict[str, Any],
            self.REGIME_PARAMS[regime],
        )

    def get_position_size_multiplier(self, as_of_date: _date | None = None) -> float:
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
                "CRITICAL: max_hold_days missing from base config. Config must be validated before regime adaptation."
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

        # Add metadata
        config["_regime_adjusted"] = True
        config["_regime"] = self.get_current_regime(as_of_date)
        config["_regime_position_size_mult"] = params["position_size_mult"]
        config["_regime_weight_update_alpha"] = params["weight_update_alpha"]

        return config

    def regime_history(self, days: int = 30) -> list[dict[str, Any]]:
        try:
            start_date = _datetime.now(EASTERN_TZ).date() - timedelta(days=days)

            with DatabaseContext("read") as cur:
                # GOVERNANCE: Select data_unavailable to filter out invalid rows
                cur.execute(
                    """
                    SELECT DISTINCT ON (date) date, regime, data_unavailable FROM market_exposure_daily
                    WHERE date >= %s AND regime IS NOT NULL
                    ORDER BY date DESC, created_at DESC
                    """,
                    (start_date,),
                )
                rows = cur.fetchall()

            history = []
            prev_regime = None
            days_in_regime = 0

            for date_val, regime, data_unavailable in reversed(rows):
                # GOVERNANCE: Skip rows marked unavailable
                if data_unavailable:
                    continue
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
                # Eastern Time, not system-local date.today() - see get_current_regime() above.
                as_of_date = _datetime.now(EASTERN_TZ).date()

            with DatabaseContext("read") as cur:
                # GOVERNANCE: Check data_unavailable flag before using score
                cur.execute(
                    """SELECT raw_score, data_unavailable, reason FROM market_exposure_daily
                       WHERE date <= %s AND raw_score IS NOT NULL
                       ORDER BY date DESC LIMIT 1""",
                    (as_of_date,),
                )
                row = cur.fetchone()

            if row is not None and row[0] is not None:
                score, data_unavailable, reason = row[0], row[1], row[2]
                # GOVERNANCE: Fail if data marked unavailable
                if data_unavailable:
                    raise RuntimeError(
                        f"Market exposure confidence score marked unavailable: {reason or 'no reason provided'}. "
                        f"Cannot assess regime strength without valid exposure analysis."
                    )
                return min(1.0, max(0.0, float(score) / 100.0))
            raise RuntimeError(
                f"Market exposure score unavailable as of {as_of_date}. "
                "market_exposure_daily table empty or stale. "
                "Position sizing and entry thresholds cannot proceed without market regime data. "
                "Verify market_exposure_daily loader succeeded."
            )
        except RuntimeError:
            raise
        except (OSError, ValueError, KeyError, psycopg2.Error) as e:
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
