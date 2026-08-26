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
    # position_size_mult (2026-08-24): NOT dead - algo/reporting/daily_report.py's
    # _fetch_regime() reads this key directly via get_regime_params() for report display.
    # get_position_size_multiplier() (the wrapper method) and get_adjusted_config()'s
    # write-only config["_regime_position_size_mult"] WERE dead (their only real consumer,
    # get_position_size_multiplier_from_regime() in algo/trading/position_sizer.py, was
    # deleted the same day for double-counting exposure_pct against
    # get_market_exposure_multiplier() - see test_position_sizer_no_regime_double_count_20260824.py)
    # and were removed; this dict key and its REGIME_POSITION_SIZE_* constants were not.
    #
    # max_hold_days_mult/target_1-3_mult (REGIME_TARGET_*/REGIME_HOLD_DAYS_* -
    # _regime_target_hold_days_inert, RESOLVED 2026-08-25): same shape as position_size_mult
    # above in that get_adjusted_config() (the only place these get applied) has zero real
    # callers, but a DIFFERENT resolution - not double-counting like position_size_mult, but a
    # hard data-availability wall: validating whether regime-scaled exits actually help would
    # need real trade history across at least one correction/caution regime, and none exists
    # locally (buy_sell_daily's real entry-signal history only goes back to 2026-06-12; every
    # available window shows confirmed_uptrend/uptrend_under_pressure only). See
    # get_adjusted_config()'s own docstring for the full writeup. Intentionally left un-wired,
    # not an accidental bug - revisit once real correction/caution-regime trade history exists.
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

        STRUCTURAL FINDING 2026-08-25 (real-money-readiness goal session, targets/position-
        sizing audit): this method - the one place max_hold_days/t1-3_target_r_multiple get
        regime-scaled - has ZERO real callers anywhere in this codebase (confirmed via a
        repo-wide grep for `get_adjusted_config(`: only this docstring and the class comment
        above reference it; RegimeManager itself is only ever instantiated by
        phase9_reconciliation.py, daily_report.py, and this file's own __main__ block, and
        none of those call this method - only get_current_regime/get_regime_params/
        regime_history). exit_engine.py's check_time_exit/check_target_t1/t2/t3 read
        max_hold_days/t1-3_target_r_multiple straight off the config object phase6_exit_
        execution.py passes to `ExitEngine(config)` - the RAW AlgoConfig, never routed
        through this method. So unlike position_size_mult (documented above as deliberately
        display-only after its consumer was removed 2026-08-24 for double-counting
        exposure_pct), REGIME_TARGET_*/REGIME_HOLD_DAYS_* have no such "intentionally
        disconnected" note anywhere - this looks like an unfinished wire-up, not a deliberate
        design choice, but there is also no backtest evidence (unlike vol_managed_multiplier
        in market_exposure.py, which stayed pinned inert until a real SPY/QQQ backtest
        justified activating it) that regime-scaling targets/hold-days actually helps. Not
        wired in here: doing so would materially change live exit behavior for real money
        (e.g. correction regime would cut T1 from 2.0R to 1.2R and max_hold_days from 20 to
        10) without that same evidentiary bar this codebase applies to comparable live
        activations elsewhere. Left for explicit user direction: either (a) wire
        get_adjusted_config()'s output into ExitEngine's config after backtesting it the same
        way vol_managed_multiplier was validated, or (b) mark this display-only like
        position_size_mult and stop implying it's live, or (c) leave as documented dead code.

        RESOLVED 2026-08-25 (same day, user directed: "build a real backtest first"): option
        (a) is not achievable with data that exists locally today - checked concretely, not
        assumed. `run_backtest.py`'s own real entry-signal source, `buy_sell_daily`, has only
        2.5 months of history (2026-06-12 to 2026-08-25, live-queried) - nowhere near enough
        trades to compare static vs. regime-scaled exits with any statistical power. Worse:
        the regime dimension itself has no correction/caution representation to test against
        in ANY available window - `market_exposure_daily`'s full history (28 days) shows only
        confirmed_uptrend/uptrend_under_pressure, zero correction/caution days. (SPY's own
        30-week-trend + realized-vol history goes back to 1993 and could reconstruct `regime`
        for decades without the DB table - the real blocker is pairing that with actual stock-
        level trade entries, which `buy_sell_daily` cannot supply before 2026-06-12.) Building
        a backtest anyway (e.g. on synthetic entries) would produce a number that LOOKS like
        evidence but isn't - exactly the failure mode this file's own bar (vol_managed_multiplier
        stayed inert until real evidence existed) is designed to prevent.

        DECISION: keep this method un-wired (option (c), effectively also (b) - see the
        `_regime_target_hold_days_inert` marker on the class-level comment above, added to
        make this an intentional, monitored state rather than an implicit one). Revisit ONLY
        when `buy_sell_daily` (or an equivalent real entry-signal history) accumulates enough
        history to include at least one real correction or caution regime - until then, no
        amount of engineering effort here produces trustworthy evidence either way. Pinned by
        tests/unit/test_regime_manager_adjusted_config_never_wired_20260825.py plus
        tests/unit/test_regime_adaptive_exits_backtest_infeasible_20260825.py (the data-
        constraint finding above, so a future session with more history doesn't have to
        re-derive it).
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
