"""Regression/documentation test for a 2026-08-25 finding (real-money-readiness goal
session, follow-up on regime_manager.py's "regime-adaptive targets/hold-days never wired
in" finding): the user directed "build a real backtest first" to decide whether to wire
RegimeManager.get_adjusted_config() into ExitEngine. This is not achievable locally today -
not a judgment call, a hard data-availability wall, checked concretely against the real local
`stocks` dev DB (NOT the near-empty `algo_trading` DB this test suite's own conftest.py points
DB_NAME at - see CLAUDE.md's "DB_NAME there must be stocks" note - so the live facts below are
pinned as literal constants, same pattern as
test_position_sizer_concentration_dial_inert_under_real_config_20260825.py's
REAL_MAX_POSITION_SIZE_PCT, rather than queried live against whatever DB this suite happens to
be pointed at):

1. `buy_sell_daily` (run_backtest.py's own real entry-signal source) had only ~2.5 months of
   BUY-signal history (2026-06-12 to 2026-08-25) - nowhere near enough real trades to compare
   static vs. regime-scaled exits with any statistical power.
2. The regime dimension itself had no correction/caution representation anywhere available to
   test against: `market_exposure_daily`'s full stored history (28 days) showed only
   confirmed_uptrend/uptrend_under_pressure days, zero correction/caution.

Both had to independently hold for the "can't backtest this" conclusion. If a future session
re-checks the real `stocks` DB and finds either has changed (buy_sell_daily has accumulated
real multi-year history, OR a correction/caution regime day now exists), that's the signal to
revisit regime_manager.py's get_adjusted_config() decision with a real backtest - update this
test's constants (and the "RESOLVED 2026-08-25" comments in regime_manager.py and
position_sizer.py) to match, don't just assume this file is still accurate.

Same underlying data constraint also closed out the position_sizer.py concentration-dial
question (see position_sizer.py's own "RESOLVED 2026-08-25" comment at the concentration-check
site) - a real backtest could not have arbitrated between the static max_position_size_pct cap
and the EXPOSURE_TIERS max_concentration_pct values either, for the identical reason.
"""

from datetime import date

# Live-confirmed via direct query against the real local `stocks` DB, 2026-08-25 (not schema
# defaults or a mock - the actual live-verified span/regime set on that date).
BUY_SELL_DAILY_BUY_MIN_DATE = date(2026, 6, 12)
BUY_SELL_DAILY_BUY_MAX_DATE = date(2026, 8, 25)
MARKET_EXPOSURE_DAILY_OBSERVED_REGIMES = frozenset({"uptrend_under_pressure", "confirmed_uptrend"})


class TestRegimeAdaptiveExitsBacktestInfeasible:
    def test_buy_sell_daily_history_was_too_short_for_a_real_backtest(self) -> None:
        """The real BUY-signal history span (live-confirmed 2026-08-25) must be well under a
        year - the fact that made comparing static vs. regime-scaled exits statistically
        meaningless. Not a live DB check (see module docstring for why) - a pinned fact that
        should be manually re-verified against the real `stocks` DB before being trusted as
        still current, and updated here (with the accompanying decision comments) if it no
        longer holds."""
        span_days = (BUY_SELL_DAILY_BUY_MAX_DATE - BUY_SELL_DAILY_BUY_MIN_DATE).days
        assert span_days < 365, (
            f"pinned buy_sell_daily BUY-signal span is {span_days} days, not under a year - "
            f"this test's own constants are internally inconsistent with the finding they're "
            f"supposed to document. Fix the constants or the assertion."
        )

    def test_market_exposure_daily_observed_regimes_excluded_correction_and_caution(self) -> None:
        """The real regime set observed in market_exposure_daily's full history (live-
        confirmed 2026-08-25) must not include correction/caution - the second half of the
        data constraint. Not a live DB check (see module docstring) - re-verify against the
        real `stocks` DB and update this constant if a future session needs to know whether
        this still holds."""
        stressed_regimes = MARKET_EXPOSURE_DAILY_OBSERVED_REGIMES & {"correction", "caution"}
        assert not stressed_regimes, (
            f"pinned MARKET_EXPOSURE_DAILY_OBSERVED_REGIMES includes {stressed_regimes} - "
            f"contradicts the finding this test documents (zero correction/caution days "
            f"observed on 2026-08-25). Fix the constant to match what was actually verified, "
            f"or re-verify against the real DB if the pinned value is now known to be stale."
        )
