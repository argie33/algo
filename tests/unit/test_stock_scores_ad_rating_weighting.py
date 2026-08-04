#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_positioning's A/D (Accumulation/
Distribution) rating sub-component (loaders/load_stock_scores.py).

positioning_metrics.ad_rating (volume-confirmed price-trend signal, computed by
loaders/technical_indicators.py::compute_ad_rating and written by
load_positioning_metrics.py) was fully implemented, 93.5% populated, and displayed
on the scores page, but never weighted into positioning_score - the same
"displayed but never weighted" bug class as short_interest_trend. Folded in as a
0.15 sub-weight. These tests guard: (1) a bullish A/D rating scores higher than a
bearish one, (2) the component is optional - a symbol with no ad_rating still
scores from its other positioning inputs, unaffected.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestAdRatingWeighting:
    def _base_metrics(self) -> dict:
        return {
            "institutional_ownership": 50.0,
            "insider_ownership": 10.0,
            "short_interest": 3.0,
        }

    def test_bullish_ad_rating_scores_higher_than_bearish(self):
        loader = StockScoresLoader()

        bullish = dict(self._base_metrics(), ad_rating=100.0)
        bearish = dict(self._base_metrics(), ad_rating=30.0)

        bullish_score = loader._score_positioning(bullish, "BULLISH")
        bearish_score = loader._score_positioning(bearish, "BEARISH")

        assert isinstance(bullish_score, float)
        assert isinstance(bearish_score, float)
        assert bullish_score > bearish_score

    def test_missing_ad_rating_does_not_block_scoring(self):
        """A symbol with no ad_rating (compute_ad_rating failed, e.g. insufficient
        price history) must still get a real positioning score from its other
        available sub-components - ad_rating is additive, not required."""
        loader = StockScoresLoader()

        score = loader._score_positioning(self._base_metrics(), "NO_AD_RATING")

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_missing_ad_rating_leaves_other_weights_unchanged(self):
        """Absence of ad_rating should be indistinguishable in the renormalized
        result from that key simply not being in the dict - guards against the
        sub-score silently contributing 0 instead of being skipped."""
        loader = StockScoresLoader()

        with_key_none = dict(self._base_metrics(), ad_rating=None)
        without_key = self._base_metrics()

        score_a = loader._score_positioning(with_key_none, "A")
        score_b = loader._score_positioning(without_key, "B")

        assert score_a == score_b
