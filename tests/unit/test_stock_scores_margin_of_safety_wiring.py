#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_value's treatment of
margin_of_safety_pct (loaders/load_stock_scores.py).

value_metrics.margin_of_safety_pct (DCF-based "discount to intrinsic value", computed by
load_sec_valuations.py and copied onto value_metrics by load_value_quality_growth_metrics.py,
migration 1208) has been through a long history: added at 0.20 (commit 28e7ebf7d), removed
2026-08-18 (commit e38a6667d), REINSTATED 2026-08-24 (user-directed, NVDA margin-of-safety DCF
audit), reweighted several times through 2026-08-28, REMOVED FROM SCORING 2026-08-28 (an
industry-practice call: systematic Value factor methodologies like MSCI/Russell/S&P/Fama-French
are built from accounting yield ratios, not DCF estimates), RESTORED 2026-08-30 (explicit user
directive, after a full history dig found the 2026-08-28 removal had little to no quoted user
sign-off), then REMOVED FROM SCORING AGAIN 2026-08-30 (same day, later user directive - "remove
margin of safety [from the value score], make sure it is just in the deep value page" - its 7%
went to Forward P/E, see test_stock_scores_pe_forward_pe_unprofitable_floor_20260828.py's
TestForwardPeScored). See _score_value's docstring for the full trail.

These tests guard the CURRENT (removed-from-scoring) wiring: margin_of_safety_pct no longer
moves value_score in either direction - it's fetched/persisted on value_metrics and displayed
on the Deep Value page (webapp/frontend/src/pages/DeepValueStocks.jsx) only.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestMarginOfSafetyNotScored:
    def _base_metrics(self) -> dict:
        return {
            "pe_ratio": 18.0,
            "pb_ratio": 2.0,
        }

    def test_margin_of_safety_value_does_not_move_value_score(self):
        """A positive vs. negative margin_of_safety_pct must produce the SAME value_score now -
        margin_of_safety_pct is no longer a scored value_score component."""
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
        sub-components - the field was never required."""
        loader = StockScoresLoader()

        score = loader._score_value(self._base_metrics(), "NO_DCF")

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_margin_of_safety_present_does_not_change_score_vs_absent(self):
        """Populated vs. missing must produce the SAME value_score now - margin_of_safety_pct
        no longer contributes weight, so adding it must not move the score."""
        loader = StockScoresLoader()

        with_value = dict(self._base_metrics(), margin_of_safety_pct=40.0)
        without_key = self._base_metrics()

        score_a = loader._score_value(with_value, "A")
        score_c = loader._score_value(without_key, "C")

        assert score_a == score_c
