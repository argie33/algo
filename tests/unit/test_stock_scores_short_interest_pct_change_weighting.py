#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_positioning's short-interest-%-change
sub-component (loaders/load_stock_scores.py).

2026-08-17 (migration 1203): replaced the former 3-bucket short_interest_trend enum
('increasing'/'decreasing'/'stable', each mapped to one of 3 fixed scores) with the
continuous short_interest_pct_change value itself, so two symbols on opposite sides of
the old +/-5% bucket edge (e.g. +4.9% vs +49%) no longer score identically. These tests
guard: (1) shorts covering (negative change) scores strictly higher than shorts building
(positive change), (2) the score is continuous - a bigger covering move scores higher
than a smaller one, not clamped to a shared bucket value, (3) the component is optional -
a symbol with no short_interest_pct_change still scores from its other positioning
inputs, unaffected, (4) the score is clamped to [0, 100] for extreme changes.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestShortInterestPctChangeWeighting:
    def _base_metrics(self) -> dict:
        return {
            "institutional_ownership": 50.0,
            "insider_ownership": 10.0,
            "short_interest": 3.0,
        }

    def test_covering_scores_higher_than_building(self):
        loader = StockScoresLoader()

        covering = dict(self._base_metrics(), short_interest_pct_change=-20.0)
        building = dict(self._base_metrics(), short_interest_pct_change=20.0)

        covering_score = loader._score_positioning(covering, "COVERING")
        building_score = loader._score_positioning(building, "BUILDING")

        assert isinstance(covering_score, float)
        assert isinstance(building_score, float)
        assert covering_score > building_score

    def test_score_is_continuous_not_bucketed(self):
        """A bigger covering move must score higher than a smaller one - the old enum
        collapsed every change beyond +/-5% into the same 3 fixed scores."""
        loader = StockScoresLoader()

        small_cover = dict(self._base_metrics(), short_interest_pct_change=-6.0)
        big_cover = dict(self._base_metrics(), short_interest_pct_change=-40.0)

        small_score = loader._score_positioning(small_cover, "SMALL")
        big_score = loader._score_positioning(big_cover, "BIG")

        assert isinstance(small_score, float)
        assert isinstance(big_score, float)
        assert big_score > small_score

    def test_missing_pct_change_does_not_block_scoring(self):
        loader = StockScoresLoader()

        score = loader._score_positioning(self._base_metrics(), "NO_PCT_CHANGE")

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_missing_pct_change_leaves_other_weights_unchanged(self):
        loader = StockScoresLoader()

        with_key_none = dict(self._base_metrics(), short_interest_pct_change=None)
        without_key = self._base_metrics()

        score_a = loader._score_positioning(with_key_none, "A")
        score_b = loader._score_positioning(without_key, "B")

        assert score_a == score_b

    def test_extreme_changes_clamp_to_0_100(self):
        loader = StockScoresLoader()

        extreme_building = dict(self._base_metrics(), short_interest_pct_change=1000.0)
        extreme_covering = dict(self._base_metrics(), short_interest_pct_change=-1000.0)

        building_score = loader._score_positioning(extreme_building, "EXTREME_UP")
        covering_score = loader._score_positioning(extreme_covering, "EXTREME_DOWN")

        assert isinstance(building_score, float)
        assert isinstance(covering_score, float)
        assert 0.0 <= building_score <= 100.0
        assert 0.0 <= covering_score <= 100.0
