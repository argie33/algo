#!/usr/bin/env python3
"""Regression test: StockScoresLoader._score_growth must return a real float even when
book_value_growth saturates the scoring curve's boundary.

Bug found 2026-08-27 (goal-mode data-coverage audit): `_score_single_growth`'s clamping used
int literals - `max(0, ...)` / `min(100, ...)` - which return the literal Python int when the
float argument saturates past the boundary (e.g. `min(100, 105.3)` -> int `100`, not `100.0`).
`_compute_stock_score`'s `is_real_score()` checks `isinstance(result, float)`, so any saturated
growth score silently failed that check and got discarded into `unavailable_metrics["growth"] =
"unknown_reason"` - not a data gap, a type bug. Affected 761/5194 live symbols (every one with
book_value_growth <= -30% or >= +50%, both common values), confirmed via direct DB query before
the fix and 0 after re-running the scores loader.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestGrowthScoreSaturationReturnsFloat:
    def _score(self, book_value_growth: float) -> float | dict:
        loader = StockScoresLoader.__new__(StockScoresLoader)
        metrics = {"data_unavailable": False, "book_value_growth": book_value_growth}
        return loader._score_growth(metrics, "TEST")

    def test_large_negative_book_value_growth_saturates_at_100_as_float(self):
        # Inverted curve: very negative book_value_growth (shrinking book value) scores highest.
        # -39.71% (a real, common value - see MEDP in the live incident) saturates the [0,cap]
        # positive branch after sign-flip.
        result = self._score(-39.71)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 100.0

    def test_large_positive_book_value_growth_saturates_at_0_as_float(self):
        # Very positive book_value_growth (rapid book-value expansion) scores lowest after
        # sign-flip, saturating the max(0, ...) branch.
        result = self._score(1093.03)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 0.0

    def test_non_saturating_value_still_returns_float(self):
        result = self._score(-5.0)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"

    def test_exactly_zero_growth_returns_float(self):
        result = self._score(0.0)
        assert isinstance(result, float), f"expected float, got {type(result).__name__}: {result!r}"
        assert result == 40.0
