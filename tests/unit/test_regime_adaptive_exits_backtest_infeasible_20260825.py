"""Regression/documentation test for a 2026-08-25 finding (real-money-readiness goal
session, follow-up on regime_manager.py's "regime-adaptive targets/hold-days never wired
in" finding), CORRECTED 2026-09-04 after the original premise turned out to be wrong in an
important way - read the whole history below, don't trust only the latest section:

ORIGINAL 2026-08-25 FINDING (superseded, kept for context): the user directed "build a real
backtest first" to decide whether to wire RegimeManager.get_adjusted_config() into
ExitEngine. Concluded infeasible based on two facts checked against the real local `stocks`
dev DB (NOT the near-empty `algo_trading` DB this test suite's own conftest.py points
DB_NAME at - see CLAUDE.md's "DB_NAME there must be stocks" note):
1. `buy_sell_daily` had only ~2.5 months of BUY-signal history.
2. `market_exposure_daily`'s full stored history (28 days) showed only
   confirmed_uptrend/uptrend_under_pressure, zero correction/caution.
RE-VERIFIED 2026-09-04, both facts still literally true (buy_sell_daily span now ~83 days,
market_exposure_daily now 36 days, still zero correction/caution) - see git history of this
file for the intermediate version.

CORRECTED 2026-09-04 (same session, user pushback: "isn't the limit self-imposed? we should
get all the data we need"): fact #2 above was TRUE BUT MISLEADING. `market_exposure_daily` is
a live production table that only ever computes "today's" snapshot - its shallow window
reflects how long the production loader has been running, not how much regime history
actually exists or is reconstructable. The underlying inputs (price_daily's SPY/^VIX history
back to 1992-93, FRED's HY OAS credit spread series, price_daily's broad stock-universe
history for breadth/selling-pressure) are far deeper. Built
`scripts/backtest_regime_reconstruction.py` (standalone, read-only, analysis-only - does not
touch any production table) that replicates market_exposure.py's exact scoring/veto logic
against that deeper history at weekly cadence, 1993-01-25 to 2026-08-31 (1,753 weeks).
Result: correction 466 weeks (27%), caution 693 weeks (40%), uptrend_under_pressure 132
weeks (8%), confirmed_uptrend 462 weeks (26%) - correction+caution are 66% of market
history, not "zero ever observed." Sanity-checked against known dates with no cherry-picking:
2008-10-06 (GFC, VIX 52.0) -> correction, 2009-03-02 (GFC trough) -> correction, 2020-03-16
(COVID crash, VIX 57.8) -> correction, 2022-06-13 (2022 bear low) -> correction, 2002-09-30
(dot-com trough) -> correction, 2000-03-20 (dot-com peak, SPY still above 30wk MA at that
exact date) -> caution not correction (correctly NOT full correction - the classifier isn't
just guessing bearish near known crashes, it's tracking the real signal). One real, permanent
gap found along the way: FRED's ICE BofA HY OAS series (`BAMLH0A0HYM2`) only serves a rolling
~3-year window as of an April 2026 distribution-policy change - not fixable by asking for a
wider range - so credit-spread veto is marked "not evaluated" (not "passed") before
2023-08-22; this doesn't undermine the correction/caution classifications above, all of which
triggered on VIX/selling-pressure/trend alone.

REMAINING BLOCKER (still real, not yet resolved): regime *labels* are now well-supported
historically, but validating regime-ADAPTIVE EXITS needs real historical *trades* (entries/
exits actually taken under each regime), not just regime labels on a calendar. `buy_sell_daily`
(the algo's own entry-signal table) is still only ~83 days deep because that's a live
production table - getting a real trade history under real historical regimes means replaying
the full stock-scoring + entry-signal pipeline (fundamentals-dependent, not just price) across
decades: a substantially larger, separate undertaking from the regime reconstruction built
here, not yet attempted. Until that's built, get_adjusted_config() stays unwired - now because
the trade-history piece is missing, NOT because regime data is scarce (that framing is now
false and must not be used to justify staying unwired going forward).

If a future session builds the signal-replay backtest and validates (or invalidates) regime-
adaptive exits against real historical trades, that's the signal to revisit this decision -
update this file's constants/assertions and regime_manager.py's/position_sizer.py's
"unwired" comments to match, don't just assume this file is still accurate.

Same underlying data constraint (buy_sell_daily's shallow production history) also closed out
the position_sizer.py concentration-dial question (see position_sizer.py's own "RESOLVED
2026-08-25" comment at the concentration-check site) - a real backtest could not have
arbitrated between the static max_position_size_pct cap and the EXPOSURE_TIERS
max_concentration_pct values either, for the identical reason. That conclusion is NOT
reopened by this file's correction - it depends only on the buy_sell_daily fact, which is
still true, not the regime-label fact, which was wrong.
"""

from datetime import date

# Live-confirmed via direct query against the real local `stocks` DB, 2026-09-04.
BUY_SELL_DAILY_BUY_MIN_DATE = date(2026, 6, 12)
BUY_SELL_DAILY_BUY_MAX_DATE = date(2026, 9, 3)

# Reconstructed via scripts/backtest_regime_reconstruction.py, 1993-01-25 to 2026-08-31,
# weekly cadence (1,753 weeks) - replicates market_exposure.py's real scoring/veto logic
# against price_daily/FRED history, not the shallow market_exposure_daily production table.
RECONSTRUCTED_REGIME_WEEK_COUNTS = {
    "correction": 466,
    "caution": 693,
    "uptrend_under_pressure": 132,
    "confirmed_uptrend": 462,
}


class TestRegimeAdaptiveExitsBacktestInfeasible:
    def test_buy_sell_daily_history_is_still_the_real_remaining_blocker(self) -> None:
        """The real BUY-signal history span (live-confirmed 2026-09-04) is still well under a
        year - this is the ONE remaining fact blocking a real regime-adaptive-exits backtest
        (regime-label scarcity is no longer the blocker, see module docstring). Not a live DB
        check - a pinned fact that should be manually re-verified against the real `stocks`
        DB before being trusted as still current, and updated here if it no longer holds."""
        span_days = (BUY_SELL_DAILY_BUY_MAX_DATE - BUY_SELL_DAILY_BUY_MIN_DATE).days
        assert span_days < 365, (
            f"pinned buy_sell_daily BUY-signal span is {span_days} days, not under a year - "
            f"if this has grown to real multi-year history, the signal-replay blocker "
            f"described in this file's docstring may no longer apply. Re-investigate whether "
            f"a real regime-adaptive-exits backtest is now buildable directly from live data "
            f"rather than needing the harder point-in-time-fundamentals replay."
        )

    def test_reconstructed_regime_history_shows_correction_and_caution_are_common(self) -> None:
        """Regression guard on the 2026-09-04 correction: reconstructed regime history must
        show correction+caution as a substantial fraction of market history, not a rare tail
        event - this is what falsified the original "zero correction/caution ever observed"
        conclusion. If scripts/backtest_regime_reconstruction.py is re-run and this no longer
        holds, something changed (a code fix to market_exposure.py's scoring, a data source
        swap, or a bug) - investigate before updating these constants."""
        total = sum(RECONSTRUCTED_REGIME_WEEK_COUNTS.values())
        stressed = RECONSTRUCTED_REGIME_WEEK_COUNTS["correction"] + RECONSTRUCTED_REGIME_WEEK_COUNTS["caution"]
        stressed_fraction = stressed / total
        assert stressed_fraction > 0.5, (
            f"reconstructed correction+caution fraction is {stressed_fraction:.1%}, not > 50% - "
            f"contradicts the 2026-09-04 finding that regime-label scarcity was a shallow-"
            f"production-table artifact, not a real data wall. Re-verify against a fresh run "
            f"of scripts/backtest_regime_reconstruction.py before trusting either this test or "
            f"the finding it documents."
        )
