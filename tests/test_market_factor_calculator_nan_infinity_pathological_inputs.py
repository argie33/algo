#!/usr/bin/env python3
"""Regression tests: MarketFactorCalculator silently laundered NaN/Infinity market data
into confident, wrong scores instead of failing fast (algo/risk/market_factor_calculator.py).

Same bug class already found and fixed this session in position_sizer.py, financial.py,
phase8_entry_execution.py, exit_engine.py, order_manager.py, and phase7_signal_generation.py:
`max(0.0, min(100.0, ...))`-style clamps silently launder NaN into a fixed boundary value via
Python's min()/max() short-circuit comparison behavior (`nan < x` is always False), rather than
raising. This is the highest-leverage instance found so far: market_factor_calculator.py feeds
most of the sub-signals behind MarketExposure.compute()'s 3-pillar composite (a few - ad_line,
credit_spread, market_technicals - are MarketExposure's own local methods, not this
calculator's, per its module docstring's "canonical implementations... not yet migrated to
MarketFactorCalculator" comment; see tests/unit/test_market_exposure_nan_guards.py for their
NaN-guard coverage), which gates real-money exposure tier / position sizing for the whole
portfolio - not just a single symbol.

CORRECTION (2026-08-20): this calculator ALSO had its own ad_line()/credit_spread() methods
at the time this file was written, and the TestCreditSpreadRejectsNonFiniteOAS test below
originally covered credit_spread()'s NaN guard - but both methods turned out to be dead code
(confirmed zero callers anywhere, reading from an abandoned/never-loaded table and a
different, wrong table respectively) and were removed. Coverage for the real, live
_credit_spread()'s equivalent NaN guard (added in the same fix, since the live method had
never had one) now lives in test_market_exposure_nan_guards.py instead.

Each factor method already fails fast on NULL/missing data; these tests prove it does the same
for NaN/Infinity, which passes every "is not None" guard silently.
"""

import math
from datetime import date
from unittest.mock import MagicMock

import pytest

from algo.risk.market_factor_calculator import MarketFactorCalculator


class _Row(tuple):
    """A DB row that also looks like it has no surprises for isinstance checks."""


class _FakeCursor:
    """Returns a single fixed row (or none) regardless of query text."""

    def __init__(self, row):
        self._row = row

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return self._row

    def fetchall(self):
        # vix_regime() now pulls up to 6 sessions (today + a real trend comparison point,
        # see market_factor_calculator.py) via fetchall() instead of fetchone() - a single
        # row is enough to exercise the level/NaN-guard logic these tests target, since
        # `rising` gracefully defaults to False without a 6th row.
        return [self._row] if self._row is not None else []


class TestWtPtsRejectsNonFiniteScore:
    def test_nan_score_raises_instead_of_laundering_through_caller_clamp(self):
        calc = MarketFactorCalculator()
        with pytest.raises(ValueError, match="Non-finite score"):
            calc._wt_pts({"name": "fake_factor", "score": float("nan")}, 10.0)

    def test_infinity_score_raises(self):
        calc = MarketFactorCalculator()
        with pytest.raises(ValueError, match="Non-finite score"):
            calc._wt_pts({"name": "fake_factor", "score": float("inf")}, 10.0)

    def test_finite_score_still_works(self):
        calc = MarketFactorCalculator()
        pts, avail = calc._wt_pts({"name": "fake_factor", "score": 50.0}, 10.0)
        assert pts == 5.0
        assert avail == 10.0


class TestTrendRejectsNonFinitePrices:
    def test_nan_spy_close_raises(self):
        calc = MarketFactorCalculator()
        cur = _FakeCursor((float("nan"), 500.0))
        with pytest.raises(RuntimeError, match="Non-finite SPY trend data"):
            calc.trend_30wk(date(2026, 8, 10), cur)

    def test_nan_sma_raises(self):
        calc = MarketFactorCalculator()
        cur = _FakeCursor((500.0, float("nan")))
        with pytest.raises(RuntimeError, match="Non-finite SPY trend data"):
            calc.trend_30wk(date(2026, 8, 10), cur)


class TestMomentumRejectsNonFinitePrices:
    def test_nan_year_ago_bypasses_the_le_zero_guard_without_the_fix(self):
        # NaN <= 0 is False in Python, so the pre-existing "year_ago <= 0" guard alone
        # would NOT catch this - proving the isnan/isinf check is load-bearing, not redundant.
        assert not (float("nan") <= 0)
        calc = MarketFactorCalculator()
        cur = _FakeCursor((500.0, float("nan")))
        with pytest.raises(RuntimeError, match="Non-finite SPY momentum"):
            calc.spy_momentum(date(2026, 8, 10), cur)

    def test_infinity_current_price_raises(self):
        calc = MarketFactorCalculator()
        cur = _FakeCursor((float("inf"), 400.0))
        with pytest.raises(RuntimeError, match="Non-finite SPY momentum"):
            calc.spy_momentum(date(2026, 8, 10), cur)


class TestVixRegimeRejectsNonFiniteLevel:
    def test_nan_vix_level_raises_instead_of_scoring_as_calm_market(self):
        calc = MarketFactorCalculator()
        cur = _FakeCursor((date(2026, 8, 10), float("nan")))
        with pytest.raises(RuntimeError, match="Non-finite VIX level"):
            calc.vix_regime(date(2026, 8, 10), cur)


class TestAaiiRejectsNonFiniteSentiment:
    def test_nan_bullish_raises_instead_of_defaulting_to_neutral(self):
        # Without the fix: NaN fails both `spread < -15` and `spread > 15` comparisons,
        # silently falling through to the "neutral" branch (score=50) - directly
        # contradicting the function's own docstring ("sentiment extremes are key
        # contrarian signals... missing data is a data error, not a skip condition").
        #
        # UPDATED (2026-08-16): a 2026-08-11 fix added an unbounded-staleness guard to
        # aaii() (see its own "BUG FOUND 2026-08-11" comment), which added `date` as a
        # third SELECT column read via row[2] - this fixture predates that and only had 2
        # elements. Third element must be a non-stale date (within 21 days of eval_date) so
        # the staleness check passes and the NaN check under test is what actually fires.
        calc = MarketFactorCalculator()
        cur = _FakeCursor((float("nan"), 30.0, date(2026, 8, 10)))
        with pytest.raises(RuntimeError, match="Non-finite AAII sentiment"):
            calc.aaii(date(2026, 8, 10), cur)


# TestPositioningRejectsNonFiniteShortInterestAvg removed 2026-08-23 (pillar redesign):
# positioning()/_insider_buying_breadth()/_short_interest_trend() were deleted from
# MarketFactorCalculator - not covered by the redesign's evidence framework, and
# short_interest_finra had only 3 FINRA settlement cycles of local history, too thin to
# trust regardless. See algo/risk/market_exposure.py's module docstring, "Dropped
# entirely" section.
