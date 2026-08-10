#!/usr/bin/env python3
"""Regression tests: MarketFactorCalculator silently laundered NaN/Infinity market data
into confident, wrong scores instead of failing fast (algo/risk/market_factor_calculator.py).

Same bug class already found and fixed this session in position_sizer.py, financial.py,
phase8_entry_execution.py, exit_engine.py, order_manager.py, and phase7_signal_generation.py:
`max(0.0, min(100.0, ...))`-style clamps silently launder NaN into a fixed boundary value via
Python's min()/max() short-circuit comparison behavior (`nan < x` is always False), rather than
raising. This is the highest-leverage instance found so far: market_factor_calculator.py feeds
every one of the ~12 factors behind MarketExposure.compute(), which gates real-money exposure
tier / position sizing for the whole portfolio - not just a single symbol.

Each factor method already fails fast on NULL/missing data; these tests prove it does the same
for NaN/Infinity, which passes every "is not None" guard silently.
"""

import math
from datetime import date

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


class TestCreditSpreadRejectsNonFiniteOAS:
    def test_nan_oas_raises_instead_of_scoring_as_low_stress(self):
        # Without the fix: max(0, min(100, 100 - (nan - 300) / 2)) silently -> 100.0
        # (best possible / lowest-stress score) for corrupted credit data.
        calc = MarketFactorCalculator()
        cur = _FakeCursor((float("nan"),))
        with pytest.raises(RuntimeError, match="Non-finite HY OAS"):
            calc.credit_spread(date(2026, 8, 10), cur)


class TestAaiiRejectsNonFiniteSentiment:
    def test_nan_bullish_raises_instead_of_defaulting_to_neutral(self):
        # Without the fix: NaN fails both `spread < -15` and `spread > 15` comparisons,
        # silently falling through to the "neutral" branch (score=50) - directly
        # contradicting the function's own docstring ("sentiment extremes are key
        # contrarian signals... missing data is a data error, not a skip condition").
        calc = MarketFactorCalculator()
        cur = _FakeCursor((float("nan"), 30.0))
        with pytest.raises(RuntimeError, match="Non-finite AAII sentiment"):
            calc.aaii(date(2026, 8, 10), cur)


class TestNaaimRejectsNonFiniteExposure:
    def test_nan_exposure_raises_instead_of_scoring_as_extreme_overweight(self):
        # Without the fix: min(100, max(0, 100 - nan / 2)) silently -> 0.0
        # (extreme-overweight / most-bearish-contrarian score) for corrupted data.
        calc = MarketFactorCalculator()
        cur = _FakeCursor((float("nan"),))
        with pytest.raises(RuntimeError, match="Non-finite NAAIM exposure"):
            calc.naaim(date(2026, 8, 10), cur)

    def test_finite_exposure_still_works(self):
        calc = MarketFactorCalculator()
        cur = _FakeCursor((50.0,))
        result = calc.naaim(date(2026, 8, 10), cur)
        assert result["score"] == 75.0
