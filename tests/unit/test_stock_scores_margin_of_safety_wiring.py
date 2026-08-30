#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_value's treatment of
margin_of_safety_pct (loaders/load_stock_scores.py).

value_metrics.margin_of_safety_pct (DCF-based "discount to intrinsic value", computed by
load_sec_valuations.py and copied onto value_metrics by load_value_quality_growth_metrics.py,
migration 1208) has been through a long history: added at 0.20 (commit 28e7ebf7d), removed
2026-08-18 (commit e38a6667d), REINSTATED 2026-08-24 (user-directed, NVDA margin-of-safety DCF
audit), reweighted several times through 2026-08-28, REMOVED FROM SCORING 2026-08-28 (an
industry-practice call: systematic Value factor methodologies like MSCI/Russell/S&P/Fama-French
are built from accounting yield ratios, not DCF estimates), and RESTORED AGAIN 2026-08-30
(explicit user directive, after a full history dig found the 2026-08-28 redesign - including
this removal - had little to no quoted user sign-off, unlike the 2026-08-24 reinstatement which
was directly user-requested). See _score_value's docstring for the full trail.

These tests guard the CURRENT (restored) wiring: margin_of_safety_pct is a real 7%-weighted
value_score component again - a positive (undervalued) reading scores higher than a negative
(overvalued) one, and the field's presence/absence changes the score (since it now contributes
real weight), not the reverse.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestMarginOfSafetyWired:
    def _base_metrics(self) -> dict:
        return {
            "pe_ratio": 18.0,
            "pb_ratio": 2.0,
        }

    def test_undervalued_scores_higher_than_overvalued(self):
        """Undervalued (positive MoS) must score higher than overvalued (negative MoS) -
        margin_of_safety_pct is a real, scored value_score component."""
        loader = StockScoresLoader()

        undervalued = dict(self._base_metrics(), margin_of_safety_pct=40.0)
        overvalued = dict(self._base_metrics(), margin_of_safety_pct=-40.0)

        undervalued_score = loader._score_value(undervalued, "UNDERVALUED")
        overvalued_score = loader._score_value(overvalued, "OVERVALUED")

        assert isinstance(undervalued_score, float)
        assert isinstance(overvalued_score, float)
        assert undervalued_score > overvalued_score

    def test_missing_margin_of_safety_does_not_block_scoring(self):
        """A symbol with no margin_of_safety_pct (DCF not computable, e.g. negative
        FCF) must still get a real value score from its other available
        sub-components - the field is not required, just weighted when present."""
        loader = StockScoresLoader()

        score = loader._score_value(self._base_metrics(), "NO_DCF")

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_margin_of_safety_none_and_absent_score_identically(self):
        """An explicit `None` value and a missing key must be treated the same -
        both should renormalize over the remaining available components identically."""
        loader = StockScoresLoader()

        with_key_none = dict(self._base_metrics(), margin_of_safety_pct=None)
        without_key = self._base_metrics()

        score_b = loader._score_value(with_key_none, "B")
        score_c = loader._score_value(without_key, "C")

        assert score_b == score_c

    def test_margin_of_safety_present_changes_score_vs_absent(self):
        """Populated vs. missing must NOT produce the same value_score any more - MoS is a
        real weighted component now, so adding it should move the score (renormalizing over
        one more available component)."""
        loader = StockScoresLoader()

        with_value = dict(self._base_metrics(), margin_of_safety_pct=40.0)
        without_key = self._base_metrics()

        score_a = loader._score_value(with_value, "A")
        score_c = loader._score_value(without_key, "C")

        assert score_a != score_c
