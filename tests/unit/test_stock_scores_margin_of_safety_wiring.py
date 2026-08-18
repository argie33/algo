#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_value's margin_of_safety_pct
sub-component (loaders/load_stock_scores.py).

value_metrics.margin_of_safety_pct (DCF-based "discount to intrinsic value",
computed by load_sec_valuations.py and copied onto value_metrics by
load_value_quality_growth_metrics.py, migration 1208) was originally added in
commit 28e7ebf7d, whose message claimed it was "scored at 20% weight in
load_stock_scores.py" - but 28e7ebf7d is not an ancestor of HEAD (the scoring
hunk was dropped in a concurrent-session git collision, only the DCF
computation/storage half of the commit actually landed). Live-confirmed: the
value_metrics SELECT in load_stock_scores.py never fetched margin_of_safety_pct
at all, so the DCF signal had zero influence on value_score despite being fully
computed and stored - same "displayed/computed but never weighted" bug class as
ad_rating (test_stock_scores_ad_rating_weighting.py) and short_interest_trend.
Restored as a 0.20 sub-weight, same as the original design intent.

These tests guard: (1) a stock trading well below its DCF intrinsic value
(positive margin of safety) scores higher than one trading well above it
(negative margin of safety), (2) the component is optional - a symbol with no
margin_of_safety_pct (DCF not computable, e.g. negative FCF) still scores from
its other value inputs, unaffected.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestMarginOfSafetyWiring:
    def _base_metrics(self) -> dict:
        return {
            "pe_ratio": 18.0,
            "pb_ratio": 2.0,
        }

    def test_undervalued_scores_higher_than_overvalued(self):
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
        sub-components - margin of safety is additive, not required."""
        loader = StockScoresLoader()

        score = loader._score_value(self._base_metrics(), "NO_DCF")

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_missing_margin_of_safety_leaves_other_weights_unchanged(self):
        """Absence of margin_of_safety_pct should be indistinguishable in the
        renormalized result from that key simply not being in the dict - guards
        against the sub-score silently contributing 0 instead of being skipped."""
        loader = StockScoresLoader()

        with_key_none = dict(self._base_metrics(), margin_of_safety_pct=None)
        without_key = self._base_metrics()

        score_a = loader._score_value(with_key_none, "A")
        score_b = loader._score_value(without_key, "B")

        assert score_a == score_b
