#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_value's treatment of negative-book-value
companies (loaders/load_stock_scores.py), added 2026-09-05 (real-money-readiness audit).

Same bug class and fix as test_stock_scores_pe_forward_pe_unprofitable_floor_20260828.py's
P/E and Forward P/E floors: pb_ratio is only computed by load_sec_valuations.py when
stockholders_equity is positive; before this fix, `_score_value` treated a None pb_ratio as
"no data" and simply excluded P/B from the weighted average, renormalizing the symbol's
value_score onto its remaining components (P/E, P/S, Forward P/E, Dividend Yield) as if P/B
had never existed - even though `pb_ratio_unavailable_reason == "negative_book_value"`
(loaders/helpers/vqg_value.py) already distinguishes this from genuinely missing data. A
negative book value (distressed leverage, LBO-style buybacks) is definitionally worse than
any positive one on a book-to-market basis, so it must be floored at 0 (this pillar's
existing worst P/B sub-score), not excluded.

These tests guard: (1) a negative-book-value company scores LOWER on value_score than an
otherwise-identical positive-book-value company, (2) it still produces a real (non-null)
score from its other components, (3) a genuinely missing-data case (pb_ratio None, no reason
or a different reason) is NOT floored - still renormalized/excluded exactly as before.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestPbNegativeBookValueFloor:
    def _base_metrics(self) -> dict:
        return {
            "pe_ratio": 15.0,
            "ps_ratio": 3.0,
        }

    def test_negative_book_value_scores_lower_than_positive(self):
        loader = StockScoresLoader()

        positive_book_value = dict(self._base_metrics(), pb_ratio=2.0)
        negative_book_value = dict(
            self._base_metrics(), pb_ratio=None, pb_ratio_unavailable_reason="negative_book_value"
        )

        positive_score = loader._score_value(positive_book_value, "POSITIVE_BOOK_VALUE")
        negative_score = loader._score_value(negative_book_value, "NEGATIVE_BOOK_VALUE")

        assert isinstance(positive_score, float)
        assert isinstance(negative_score, float)
        assert negative_score < positive_score

    def test_negative_book_value_still_produces_a_real_score(self):
        """A negative-book-value company must not be blocked from scoring entirely - it still
        gets a real value_score from P/E, P/S, and any other available inputs."""
        loader = StockScoresLoader()

        score = loader._score_value(
            dict(self._base_metrics(), pb_ratio=None, pb_ratio_unavailable_reason="negative_book_value"),
            "NEGATIVE_BOOK_VALUE",
        )

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_genuinely_missing_pb_data_is_not_floored(self):
        """A pb_ratio of None with no reason (or a non-"negative_book_value" reason, e.g. real
        missing SEC data) means the true P/B is UNKNOWN, not known-bad - must still be excluded/
        renormalized exactly as before, not floored to 0."""
        loader = StockScoresLoader()

        missing_no_reason = dict(self._base_metrics(), pb_ratio=None)
        missing_other_reason = dict(self._base_metrics(), pb_ratio=None, pb_ratio_unavailable_reason="missing_sec_data")
        without_key = self._base_metrics()

        score_a = loader._score_value(missing_no_reason, "A")
        score_b = loader._score_value(missing_other_reason, "B")
        score_c = loader._score_value(without_key, "C")

        # All three should be identical to each other (P/B simply excluded/renormalized) and
        # strictly HIGHER than the floored negative-book-value case, since exclusion != floor.
        assert score_a == score_b == score_c
        negative_book_value_score = loader._score_value(
            dict(self._base_metrics(), pb_ratio=None, pb_ratio_unavailable_reason="negative_book_value"),
            "NEGATIVE_BOOK_VALUE",
        )
        assert negative_book_value_score < score_a
