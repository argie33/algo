#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_value's exclusion of margin_of_safety_pct
(loaders/load_stock_scores.py).

value_metrics.margin_of_safety_pct (DCF-based "discount to intrinsic value", computed by
load_sec_valuations.py and copied onto value_metrics by load_value_quality_growth_metrics.py,
migration 1208) was briefly wired into _score_value as a 0.20 sub-weight (see git history
around commit 28e7ebf7d / the now-removed TestMarginOfSafetyWiring in this file). Removed
2026-08-18 per explicit user request - margin of safety doesn't belong in the Value factor
score. It's still computed and stored, and still displayed on the frontend as the single
cross-symbol-comparable "discount to intrinsic value" read (see StockScoreAccordion.jsx),
just no longer folded into any factor score.

These tests guard against the wiring silently coming back: a symbol differing only in
margin_of_safety_pct must score identically to one without it.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestMarginOfSafetyExcludedFromValueScore:
    def _base_metrics(self) -> dict:
        return {
            "pe_ratio": 18.0,
            "pb_ratio": 2.0,
        }

    def test_margin_of_safety_does_not_move_value_score(self):
        loader = StockScoresLoader()

        undervalued = dict(self._base_metrics(), margin_of_safety_pct=40.0)
        overvalued = dict(self._base_metrics(), margin_of_safety_pct=-40.0)
        without_key = self._base_metrics()

        undervalued_score = loader._score_value(undervalued, "UNDERVALUED")
        overvalued_score = loader._score_value(overvalued, "OVERVALUED")
        base_score = loader._score_value(without_key, "BASE")

        assert undervalued_score == overvalued_score == base_score

    def test_missing_margin_of_safety_does_not_block_scoring(self):
        """A symbol with no margin_of_safety_pct must still get a real value score from
        its other available sub-components."""
        loader = StockScoresLoader()

        score = loader._score_value(self._base_metrics(), "NO_DCF")

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0
