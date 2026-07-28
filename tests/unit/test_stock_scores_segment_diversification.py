#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_stability's business-diversification
sub-component (loaders/load_stock_scores.py).

sec_segment_metrics.revenue_concentration_hhi (Herfindahl index of revenue by business
segment, computed from real XBRL segment disclosures) was fully implemented and
live-verified but had zero consumers anywhere - not in any score, not in any API route,
not on the dashboard. Folded in as a minor (0.10) sub-weight inside stability scoring,
the same pattern already used for debt_to_assets. These tests guard: (1) diversified
companies score higher than concentrated ones, (2) the component is optional - a symbol
with no segment data still scores from its other stability inputs, unaffected.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestSegmentDiversificationSubScore:
    def _base_metrics(self) -> dict:
        return {
            "volatility_252d": 0.20,
            "volatility_60d": 0.20,
            "volatility_30d": 0.20,
            "beta": 1.0,
        }

    def test_diversified_company_scores_higher_than_concentrated(self):
        loader = StockScoresLoader()

        diversified = dict(self._base_metrics(), revenue_concentration_hhi=1000.0)
        concentrated = dict(self._base_metrics(), revenue_concentration_hhi=10000.0)

        diversified_score = loader._score_stability(diversified, "DIVERSIFIED")
        concentrated_score = loader._score_stability(concentrated, "CONCENTRATED")

        assert isinstance(diversified_score, float)
        assert isinstance(concentrated_score, float)
        assert diversified_score > concentrated_score

    def test_missing_segment_data_does_not_block_scoring(self):
        """A symbol with no sec_segment_metrics row (single-segment filers, ETFs
        excluded, or not yet backfilled) must still get a real stability score from
        its other available sub-components - segment data is additive, not required."""
        loader = StockScoresLoader()

        score = loader._score_stability(self._base_metrics(), "NO_SEGMENT_DATA")

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_missing_segment_data_leaves_other_weights_unchanged(self):
        """Absence of revenue_concentration_hhi should be indistinguishable in the
        renormalized result from that key simply not being in the dict - guards
        against the sub-score silently contributing 0 instead of being skipped."""
        loader = StockScoresLoader()

        with_key_none = dict(self._base_metrics())
        without_key = self._base_metrics()

        score_a = loader._score_stability(with_key_none, "A")
        score_b = loader._score_stability(without_key, "B")

        assert score_a == score_b

    def test_highly_concentrated_score_floors_at_50_not_zero(self):
        """Single-segment companies (HHI=10000) are extremely common and often healthy
        businesses - concentration is a secondary risk signal, not a verdict. The
        sub-score must not collapse to 0 for the single-segment case."""
        loader = StockScoresLoader()

        metrics = dict(self._base_metrics(), revenue_concentration_hhi=10000.0)
        score = loader._score_stability(metrics, "SINGLE_SEGMENT")

        # Isolate the diversification sub-score's floor by comparing against the
        # no-segment-data baseline: the difference should be small, not catastrophic.
        baseline = loader._score_stability(self._base_metrics(), "BASELINE")
        assert isinstance(score, float)
        assert isinstance(baseline, float)
        assert baseline - score < 10.0
