#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_value's treatment of
margin_of_safety_pct (loaders/load_stock_scores.py).

value_metrics.margin_of_safety_pct (DCF-based "discount to intrinsic value", computed by
load_sec_valuations.py and copied onto value_metrics by load_value_quality_growth_metrics.py,
migration 1208) was added as a 0.20 sub-weight in commit 28e7ebf7d, removed 2026-08-18 (commit
e38a6667d), REINSTATED 2026-08-24 (user-directed, NVDA margin-of-safety DCF audit), reweighted
several times through 2026-08-28, and REMOVED FROM SCORING AGAIN 2026-08-28 (goal: "is margin of
safety typically a metric used in the value factor score... or is it typically used some other
way") - see _score_value's "MARGIN OF SAFETY - REMOVED FROM SCORING 2026-08-28" docstring note.

Unlike the 2026-08-18 removal (a display-only-for-comparability rationale, later overridden by
explicit user request), this one is an industry-practice call: systematic Value factor scores
(MSCI Enhanced Value, Russell Style, S&P Style Indices, Fama-French HML, AQR) are built from
accounting yield ratios (P/E, P/B, P/S, EV/EBITDA, dividend yield) computed directly from
financials - not DCF intrinsic-value estimates, which require per-company growth/discount-rate
assumptions and belong to a different tradition (Graham/Klarman "margin of safety" as a per-stock
deep-value screening/decision rule, not a cross-sectional ranking factor). This repo's own
sub-period t-stats for margin_of_safety were unstable (0.30 to 2.12 across halves) versus PE/PB/PS
being robust in every sub-period tested - consistent with that industry-practice read. The field
stays fully computed/stored/displayed and is the Deep Value Picks page's (DeepValueStocks.jsx)
primary metric instead.

These tests guard: (1) margin_of_safety_pct no longer moves value_score at all, in either
direction, (2) its presence/absence is fully inert - a symbol scores identically whether the
field is populated, None, or missing entirely, since it's not part of the weighted formula.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestMarginOfSafetyNotWired:
    def _base_metrics(self) -> dict:
        return {
            "pe_ratio": 18.0,
            "pb_ratio": 2.0,
        }

    def test_margin_of_safety_value_does_not_move_value_score(self):
        """Undervalued (positive MoS) vs. overvalued (negative MoS) must score identically -
        margin_of_safety_pct is no longer part of the weighted value_score formula."""
        loader = StockScoresLoader()

        undervalued = dict(self._base_metrics(), margin_of_safety_pct=40.0)
        overvalued = dict(self._base_metrics(), margin_of_safety_pct=-40.0)

        undervalued_score = loader._score_value(undervalued, "UNDERVALUED")
        overvalued_score = loader._score_value(overvalued, "OVERVALUED")

        assert isinstance(undervalued_score, float)
        assert isinstance(overvalued_score, float)
        assert undervalued_score == overvalued_score

    def test_missing_margin_of_safety_does_not_block_scoring(self):
        """A symbol with no margin_of_safety_pct (DCF not computable, e.g. negative
        FCF) must still get a real value score from its other available
        sub-components - the field was never required, and still isn't."""
        loader = StockScoresLoader()

        score = loader._score_value(self._base_metrics(), "NO_DCF")

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_margin_of_safety_present_none_or_absent_scores_identically(self):
        """Populated, None, or missing entirely - all three must produce the exact same
        value_score, since margin_of_safety_pct no longer contributes to weighted_sum/
        total_weight at all."""
        loader = StockScoresLoader()

        with_value = dict(self._base_metrics(), margin_of_safety_pct=25.0)
        with_key_none = dict(self._base_metrics(), margin_of_safety_pct=None)
        without_key = self._base_metrics()

        score_a = loader._score_value(with_value, "A")
        score_b = loader._score_value(with_key_none, "B")
        score_c = loader._score_value(without_key, "C")

        assert score_a == score_b == score_c
