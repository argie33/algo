#!/usr/bin/env python3
"""Regression test: StockScoresLoader._score_growth must return a real float even when a
growth candidate saturates the scoring curve's boundary.

Bug found 2026-08-27 (goal-mode data-coverage audit): `_score_single_growth`'s clamping used
int literals - `max(0, ...)` / `min(100, ...)` - which return the literal Python int when the
float argument saturates past the boundary (e.g. `min(100, 105.3)` -> int `100`, not `100.0`).
`_compute_stock_score`'s `is_real_score()` checks `isinstance(result, float)`, so any saturated
growth score silently failed that check and got discarded into `unavailable_metrics["growth"] =
"unknown_reason"` - not a data gap, a type bug. Affected 761/5194 live symbols when the sole
scored input was book_value_growth (every one <= -30% or >= +50%, both common values), confirmed
via direct DB query before the fix and 0 after re-running the scores loader.

UPDATED 2026-08-28: _score_growth is now a multi-input equal-weighted blend (RESTORED TO
MULTI-INPUT, user directive - see that method's own docstring), NOT sign-flipped ("shouldn't be
inverted" - same directive). `_score_single_growth`'s saturation-clamping logic this test guards
is unchanged and field-agnostic; these cases still apply verbatim, just with the sign convention
flipped (no more negation before scoring) and only revenue_growth_1y populated in the metrics
dict, so it's the sole *available* candidate for these specific cases (the blend still averages
over whatever's present - one candidate here just means the average has one term).
"""

from loaders.load_stock_scores import StockScoresLoader


class TestGrowthScoreSaturationReturnsFloat:
    def _score(self, revenue_growth_1y: float) -> float | dict:
        loader = StockScoresLoader.__new__(StockScoresLoader)
        metrics = {"data_unavailable": False, "revenue_growth_1y": revenue_growth_1y}
        return loader._score_growth(metrics, "TEST")

    def test_large_positive_revenue_growth_saturates_at_100_as_float(self):
        # NOT inverted (user directive): rapid revenue growth scores highest. 1093.03%
        # saturates the [0,cap=30] positive branch.
        result = self._score(1093.03)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 100.0

    def test_large_negative_revenue_growth_saturates_at_0_as_float(self):
        # NOT inverted: sharply shrinking revenue scores lowest, saturating the
        # max(0.0, ...) branch of the negative-growth mapping ([-50, 0] -> [0, 40]).
        result = self._score(-93.03)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 0.0

    def test_non_saturating_value_still_returns_float(self):
        result = self._score(-5.0)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"

    def test_exactly_zero_growth_returns_float(self):
        result = self._score(0.0)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 40.0
