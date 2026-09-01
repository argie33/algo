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
flipped (no more negation before scoring).

UPDATED 2026-08-31 (/goal session, GROWTH_INPUT_IMPLAUSIBLE_PCT): a raw rate beyond 150% is now
EXCLUDED from the blend rather than scored (see that constant's docstring in
load_stock_scores.py for the KARO/DX evidence). 1093.03% moved from "saturates at 100" to
"excluded entirely" - the saturation test below now uses 90% (comfortably above cap=30, still
under the 150% implausibility threshold) to keep covering the same int-vs-float clamping bug
this file was originally written for.

UPDATED 2026-08-31 (later same day, /goal session, GROWTH_MIN_FIELDS_AVAILABLE): _score_growth
now withholds a score entirely below a minimum-coverage floor (see that constant's docstring -
found by looking at live post-reload results: several thin-coverage symbols were landing a
saturated 100 off a single available field). Every test below now supplies enough filler fields
(revenue_growth_3y/eps_growth_1y/eps_growth_3y/revenue_growth_5y, all held at 0.0 -> a known,
exact 40.0 each, per test_exactly_zero_growth_returns_float) to clear
GROWTH_MIN_FIELDS_AVAILABLE=5 and keep testing the specific saturation/exclusion behavior each
test is named for, not the floor itself (see TestGrowthMinFieldsAvailable below for that).
"""

from loaders.load_stock_scores import GROWTH_MIN_FIELDS_AVAILABLE, StockScoresLoader

# 4 filler fields, each held at exactly 0.0 -> _score_single_growth(0.0, 30) == 40.0 (see
# test_exactly_zero_growth_returns_float, which double-checks this fact holds). Combined with
# one field under test, every case below has exactly 5 available fields - GROWTH_MIN_FIELDS_AVAILABLE
# itself - so these tests also incidentally pin the floor's boundary at 5, not some other number.
_ZERO_FILLERS = {
    "eps_growth_1y": 0.0,
    "revenue_growth_3y": 0.0,
    "eps_growth_3y": 0.0,
    "revenue_growth_5y": 0.0,
}


class TestGrowthScoreSaturationReturnsFloat:
    def _score(self, revenue_growth_1y: float, extra: dict | None = None) -> float | dict:
        loader = StockScoresLoader.__new__(StockScoresLoader)
        metrics = {"data_unavailable": False, "revenue_growth_1y": revenue_growth_1y, **(extra or {})}
        return loader._score_growth(metrics, "TEST")

    def test_large_positive_revenue_growth_saturates_at_100_as_float(self):
        # NOT inverted (user directive): rapid revenue growth scores highest. 90% is well past
        # the [0,cap=30] positive branch's ceiling but still under the 150% implausibility
        # exclusion threshold, so it saturates rather than getting dropped from the blend.
        # revenue_growth_1y=90.0 -> 100.0, 4 zero-fillers -> 40.0 each: avg (100+40*4)/5 = 52.0.
        result = self._score(90.0, _ZERO_FILLERS)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 52.0

    def test_implausibly_extreme_growth_excluded_not_saturated(self):
        # 1093.03% is the kind of one-off/base-effect-driven value verified live on KARO
        # (eps_growth_1y=1889.36%, traced to a ~20x net-income jump on a flat share count -
        # almost certainly a non-recurring item, not organic growth). With revenue_growth_1y as
        # the SOLE candidate (no fillers - excluding it must leave zero components, not a
        # thin-sample marker), excluding it leaves zero component scores -> the "no growth
        # inputs available" marker, not a false-confidence 100.
        result = self._score(1093.03)
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_growth_inputs_available"

    def test_implausible_field_excluded_but_other_fields_still_score(self):
        # A KARO/DX-shaped symbol: one wildly extreme field alongside genuinely reasonable
        # ones. The extreme field must not drag the blend up to near-100 by saturating - it
        # should simply not count, leaving the blend to reflect only the plausible inputs.
        # eps_growth_1y=1889.36 excluded; revenue_growth_1y=10.0 -> 60.0; 4 zero-fillers -> 40.0
        # each: 5 valid components survive exclusion (clears the floor), avg (60+40*4)/5 = 44.0.
        loader = StockScoresLoader.__new__(StockScoresLoader)
        metrics = {
            "data_unavailable": False,
            "eps_growth_1y": 1889.36,  # excluded
            "revenue_growth_1y": 10.0,  # plausible, modest grower
            **_ZERO_FILLERS,
        }
        result = loader._score_growth(metrics, "TEST")
        assert isinstance(result, float)
        assert result == 44.0

    def test_large_negative_revenue_growth_saturates_at_0_as_float(self):
        # NOT inverted: sharply shrinking revenue scores lowest, saturating the
        # max(0.0, ...) branch of the negative-growth mapping ([-50, 0] -> [0, 40]).
        # revenue_growth_1y=-93.03 -> 0.0, 4 zero-fillers -> 40.0 each: avg (0+40*4)/5 = 32.0.
        result = self._score(-93.03, _ZERO_FILLERS)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 32.0

    def test_non_saturating_value_still_returns_float(self):
        result = self._score(-5.0, _ZERO_FILLERS)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"

    def test_exactly_zero_growth_returns_float(self):
        # All 5 fields at exactly 0.0 -> every component scores 40.0 -> avg is exactly 40.0.
        # This also establishes the "0.0 -> 40.0" fact _ZERO_FILLERS above relies on.
        result = self._score(0.0, _ZERO_FILLERS)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 40.0


class TestGrowthMinFieldsAvailable:
    """GROWTH_MIN_FIELDS_AVAILABLE (added 2026-08-31, /goal session - found by looking at live
    post-reload results: ATTO/GFUZ/VRXA/KWM/BLSM each had exactly 1/12 fields available and that
    one field happened to be >=30%, landing a saturated 100 growth_score indistinguishable from
    NVDA's real 100 built from 11/12 genuinely strong fields). Mirrors Quality's existing
    ~40%-of-101 thin-sample floor (see _score_quality's own docstring) - below
    GROWTH_MIN_FIELDS_AVAILABLE, _score_growth withholds a score rather than renormalizing too
    few fields up to a full 0-100 range."""

    def _score_with_n_fields(self, n: int) -> float | dict:
        from loaders.load_stock_scores import GROWTH_SCORE_FIELDS

        loader = StockScoresLoader.__new__(StockScoresLoader)
        metrics = {"data_unavailable": False, **dict.fromkeys(GROWTH_SCORE_FIELDS[:n], 0.0)}
        return loader._score_growth(metrics, "TEST")

    def test_min_fields_available_constant_is_five(self):
        # Pinned explicitly - if this constant is ever retuned, this test should be updated
        # deliberately, not silently pass with a different threshold.
        assert GROWTH_MIN_FIELDS_AVAILABLE == 5

    def test_one_field_available_returns_thin_sample_marker(self):
        result = self._score_with_n_fields(1)
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "insufficient_growth_inputs_thin_sample"

    def test_below_floor_returns_thin_sample_marker(self):
        result = self._score_with_n_fields(GROWTH_MIN_FIELDS_AVAILABLE - 1)
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "insufficient_growth_inputs_thin_sample"

    def test_at_floor_returns_real_score(self):
        result = self._score_with_n_fields(GROWTH_MIN_FIELDS_AVAILABLE)
        assert isinstance(result, float), f"expected float at the floor boundary, got {result!r}"

    def test_above_floor_returns_real_score(self):
        result = self._score_with_n_fields(GROWTH_MIN_FIELDS_AVAILABLE + 1)
        assert isinstance(result, float)

    def test_zero_fields_available_returns_no_inputs_marker_not_thin_sample(self):
        loader = StockScoresLoader.__new__(StockScoresLoader)
        metrics = {"data_unavailable": False}
        result = loader._score_growth(metrics, "TEST")
        assert isinstance(result, dict)
        assert result["reason"] == "no_growth_inputs_available"
