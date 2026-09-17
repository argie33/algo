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
saturated 100 off a single available field). Every test below supplies enough filler fields to
clear GROWTH_MIN_FIELDS_AVAILABLE and keep testing the specific saturation/exclusion behavior
each test is named for, not the floor itself (see TestGrowthMinFieldsAvailable below for that).

UPDATED 2026-09-16 (factor-purity /goal session: "we don't want to veer far from what they do").
GROWTH_SCORE_FIELDS cut 12->4 (see that constant's own GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE
docstring in growth_scoring.py - MSCI's/Barra's real published Growth methodology uses 5/2
descriptors, not 12, and none of them are simple two-point 1y/3y/5y CAGRs). revenue_growth_1y is
no longer scored - tests below use eps_growth_trend_5y (still in GROWTH_SCORE_FIELDS) instead,
and GROWTH_MIN_FIELDS_AVAILABLE dropped 5->2 (nearest achievable ratio to Quality's ~40% with
only 4 slots, rounded up to the stricter side), so only 1 filler field is needed now.

UPDATED 2026-09-17 (factor-purity follow-up, "get rid of it" not just verify it's inert):
`_score_single_growth`'s hand-set [-50%,0]->[0,40] / [0,cap%]->[40,100] piecewise curve - the
very saturation behavior this file was originally written to test - was itself proven to never
survive as growth_score's live value (see that function's own docstring for the live-audit
evidence: 109/3,063 real symbols "matched" within tolerance, and all 109 were confirmed
coincidental correlation, not Pass-1 survival, via `_withhold_growth_below_floor()` returning 0)
and REPLACED with a flat NEUTRAL_PLACEHOLDER_SCORE (50.0) for any non-None value. The specific
int-vs-float saturation values below no longer apply - every available field now contributes
exactly 50.0 regardless of magnitude or sign, so the tests below assert that instead. What they
still meaningfully cover: the GROWTH_INPUT_IMPLAUSIBLE_PCT exclusion (an extreme raw value is
dropped from the blend, not merely saturated) and GROWTH_MIN_FIELDS_AVAILABLE's floor/
renormalization logic, both unaffected by this change since they operate on the RAW value before
`_score_single_growth` is ever called.
"""

from loaders.load_stock_scores import GROWTH_MIN_FIELDS_AVAILABLE, StockScoresLoader

# 1 filler field, held at exactly 0.0 -> _score_single_growth(0.0, 30) == 50.0 (the flat
# NEUTRAL_PLACEHOLDER_SCORE as of 2026-09-17 - see test_exactly_zero_growth_returns_float,
# which double-checks this fact holds). Combined with one field under test, every case below
# has exactly 2 available fields - GROWTH_MIN_FIELDS_AVAILABLE itself - so these tests also
# incidentally pin the floor's boundary at 2, not some other number.
_ZERO_FILLERS = {
    "sps_growth_trend_5y": 0.0,
}


class TestGrowthScoreSaturationReturnsFloat:
    def _score(self, eps_growth_trend_5y: float, extra: dict | None = None) -> float | dict:
        loader = StockScoresLoader.__new__(StockScoresLoader)
        metrics = {"data_unavailable": False, "eps_growth_trend_5y": eps_growth_trend_5y, **(extra or {})}
        return loader._score_growth(metrics, "TEST")

    def test_large_positive_revenue_growth_saturates_at_100_as_float(self):
        # 90% is well past the old [0,cap=30] positive branch's ceiling but still under the
        # 150% implausibility exclusion threshold, so it's scored (via the flat
        # NEUTRAL_PLACEHOLDER_SCORE, 2026-09-17), not excluded. Both eps_growth_trend_5y=90.0
        # and the 1 zero-filler now score 50.0 each: avg (50+50)/2 = 50.0.
        result = self._score(90.0, _ZERO_FILLERS)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 50.0

    def test_implausibly_extreme_growth_excluded_not_saturated(self):
        # 1093.03% is the kind of one-off/base-effect-driven value verified live on KARO
        # (eps_growth_1y=1889.36%, traced to a ~20x net-income jump on a flat share count -
        # almost certainly a non-recurring item, not organic growth). With eps_growth_trend_5y as
        # the SOLE candidate (no fillers - excluding it must leave zero components, not a
        # thin-sample marker), excluding it leaves zero component scores -> the "no growth
        # inputs available" marker, not a false-confidence 100.
        result = self._score(1093.03)
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_growth_inputs_available"

    def test_implausible_field_excluded_but_other_fields_still_score(self):
        # A KARO/DX-shaped symbol: one wildly extreme field alongside genuinely reasonable
        # ones. The extreme field must not count at all - GROWTH_INPUT_IMPLAUSIBLE_PCT excludes
        # it before `_score_single_growth` (now a flat NEUTRAL_PLACEHOLDER_SCORE, see that
        # function's own docstring) ever sees it.
        # sps_growth_trend_5y=1889.36 excluded; eps_growth_trend_5y=10.0 -> 50.0;
        # forward_eps_growth_current_fy=0.0 -> 50.0: 2 valid components survive exclusion
        # (clears the floor), avg (50+50)/2 = 50.0.
        loader = StockScoresLoader.__new__(StockScoresLoader)
        metrics = {
            "data_unavailable": False,
            "sps_growth_trend_5y": 1889.36,  # excluded
            "eps_growth_trend_5y": 10.0,  # plausible, modest grower
            "forward_eps_growth_current_fy": 0.0,
        }
        result = loader._score_growth(metrics, "TEST")
        assert isinstance(result, float)
        assert result == 50.0

    def test_large_negative_revenue_growth_saturates_at_0_as_float(self):
        # Sharply shrinking growth (eps_growth_trend_5y=-93.03) now scores the same flat
        # NEUTRAL_PLACEHOLDER_SCORE (50.0) as any other non-None value, same as the 1
        # zero-filler: avg (50+50)/2 = 50.0.
        result = self._score(-93.03, _ZERO_FILLERS)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 50.0

    def test_non_saturating_value_still_returns_float(self):
        result = self._score(-5.0, _ZERO_FILLERS)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"

    def test_exactly_zero_growth_returns_float(self):
        # Both fields at exactly 0.0 -> every component scores the flat
        # NEUTRAL_PLACEHOLDER_SCORE (50.0, 2026-09-17) -> avg is exactly 50.0. This also
        # establishes the "any non-None value -> 50.0" fact _ZERO_FILLERS above relies on.
        result = self._score(0.0, _ZERO_FILLERS)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 50.0


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

    def test_min_fields_available_constant_is_two(self):
        # Pinned explicitly - if this constant is ever retuned, this test should be updated
        # deliberately, not silently pass with a different threshold.
        assert GROWTH_MIN_FIELDS_AVAILABLE == 2

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
