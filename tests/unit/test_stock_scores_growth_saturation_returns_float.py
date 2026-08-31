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

UPDATED 2026-08-31 (/goal session, GROWTH_INPUT_IMPLAUSIBLE_PCT): a raw rate beyond 150% is now
EXCLUDED from the blend rather than scored (see that constant's docstring in
load_stock_scores.py for the KARO/DX evidence). 1093.03% moved from "saturates at 100" to
"excluded entirely" - the saturation test below now uses 90% (comfortably above cap=30, still
under the 150% implausibility threshold) to keep covering the same int-vs-float clamping bug
this file was originally written for.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestGrowthScoreSaturationReturnsFloat:
    def _score(self, revenue_growth_1y: float) -> float | dict:
        loader = StockScoresLoader.__new__(StockScoresLoader)
        metrics = {"data_unavailable": False, "revenue_growth_1y": revenue_growth_1y}
        return loader._score_growth(metrics, "TEST")

    def test_large_positive_revenue_growth_saturates_at_100_as_float(self):
        # NOT inverted (user directive): rapid revenue growth scores highest. 90% is well past
        # the [0,cap=30] positive branch's ceiling but still under the 150% implausibility
        # exclusion threshold, so it saturates rather than getting dropped from the blend.
        result = self._score(90.0)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 100.0

    def test_implausibly_extreme_growth_excluded_not_saturated(self):
        # 1093.03% is the kind of one-off/base-effect-driven value verified live on KARO
        # (eps_growth_1y=1889.36%, traced to a ~20x net-income jump on a flat share count -
        # almost certainly a non-recurring item, not organic growth). With revenue_growth_1y as
        # the sole candidate, excluding it leaves zero component scores -> the "no growth inputs
        # available" marker, not a false-confidence 100.
        result = self._score(1093.03)
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_growth_inputs_available"

    def test_implausible_field_excluded_but_other_fields_still_score(self):
        # A KARO/DX-shaped symbol: one wildly extreme field alongside genuinely reasonable
        # ones. The extreme field must not drag the blend up to near-100 by saturating - it
        # should simply not count, leaving the blend to reflect only the plausible inputs.
        loader = StockScoresLoader.__new__(StockScoresLoader)
        metrics = {
            "data_unavailable": False,
            "eps_growth_1y": 1889.36,  # excluded
            "revenue_growth_1y": 10.0,  # plausible, modest grower
        }
        result = loader._score_growth(metrics, "TEST")
        assert isinstance(result, float)
        # revenue_growth_1y=10% -> 40 + (10/30)*60 = 60.0, the sole surviving component.
        assert result == 60.0

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
