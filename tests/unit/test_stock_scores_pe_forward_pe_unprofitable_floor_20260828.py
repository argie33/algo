#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_value's treatment of unprofitable/
negative-forecast companies (loaders/load_stock_scores.py).

Added 2026-08-28 (goal: "is this value score right per industry best practice" - the P/E vs.
E/P gap). pe_ratio is only computed by load_sec_valuations.py when trailing EPS is positive
(same for forward_pe on forward EPS); before this fix, `_score_value` treated a None pe_ratio
as "no data" and simply excluded P/E from the weighted average, renormalizing the symbol's
value_score onto its remaining components as if P/E had never existed. Live-confirmed via
load_value_quality_growth_metrics.py's own audit: 2283 of 2519 universe pe_ratio NULLs (91%)
are unprofitable companies with a real, present EPS <= 0, not missing data (reason =
"unprofitable_stock"); 848 of 1560 forward_pe "no_analyst_estimates" rows (54%) are actually
negative-forecast-EPS companies (reason = "negative_forward_eps"). This is the exact same
selection-bias bug class this file's own PE-vs-PB/PS ranking dispute was already caught on
(strict-dropna Fama-MacBeth testing systematically excluding unprofitable/small firms) - just
live in production scoring rather than a backtest script.

Fix: an unprofitable/negative-forecast company is now floored at the worst possible P/E or
Forward P/E sub-score (0) and DOES count toward total_weight, rather than being excluded. This
is the theoretically correct treatment without needing a new stored earnings-yield field: any
negative earnings yield is, by definition, worse than any non-negative one, so flooring at the
curve's existing worst value is exactly what a true E/P ranking would produce (up to ordering
among unprofitable names specifically, which would need the real EPS magnitude to differentiate
- not attempted here).

These tests guard: (1) an unprofitable company (pe_ratio None, reason=unprofitable_stock) scores
LOWER on value_score than an otherwise-identical profitable company, (2) an unprofitable
company's value_score is not NULL/blocked - it still gets a real score from its other
components, (3) a genuinely missing-data case (pe_ratio None, no reason or a different reason)
is NOT floored - still renormalized/excluded exactly as before, since that case's true P/E is
unknown, not known-bad, (4) the same three properties hold for forward_pe/negative_forward_eps.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestPeUnprofitableFloor:
    def _base_metrics(self) -> dict:
        return {
            "pb_ratio": 2.0,
            "ps_ratio": 3.0,
        }

    def test_unprofitable_scores_lower_than_profitable(self):
        loader = StockScoresLoader()

        profitable = dict(self._base_metrics(), pe_ratio=15.0)
        unprofitable = dict(self._base_metrics(), pe_ratio=None, pe_ratio_unavailable_reason="unprofitable_stock")

        profitable_score = loader._score_value(profitable, "PROFITABLE")
        unprofitable_score = loader._score_value(unprofitable, "UNPROFITABLE")

        assert isinstance(profitable_score, float)
        assert isinstance(unprofitable_score, float)
        assert unprofitable_score < profitable_score

    def test_unprofitable_still_produces_a_real_score(self):
        """An unprofitable company must not be blocked from scoring entirely - it still gets a
        real value_score from P/B, P/S, and any other available inputs."""
        loader = StockScoresLoader()

        score = loader._score_value(
            dict(self._base_metrics(), pe_ratio=None, pe_ratio_unavailable_reason="unprofitable_stock"),
            "UNPROFITABLE",
        )

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_genuinely_missing_pe_data_is_not_floored(self):
        """A pe_ratio of None with no reason (or a non-"unprofitable_stock" reason, e.g. real
        missing SEC data) means the true P/E is UNKNOWN, not known-bad - must still be excluded/
        renormalized exactly as before, not floored to 0. Distinguishes "genuinely missing" from
        "unprofitable" using the same pe_ratio_unavailable_reason field production code reads."""
        loader = StockScoresLoader()

        missing_no_reason = dict(self._base_metrics(), pe_ratio=None)
        missing_other_reason = dict(self._base_metrics(), pe_ratio=None, pe_ratio_unavailable_reason="missing_sec_data")
        without_key = self._base_metrics()

        score_a = loader._score_value(missing_no_reason, "A")
        score_b = loader._score_value(missing_other_reason, "B")
        score_c = loader._score_value(without_key, "C")

        # All three should be identical to each other (P/E simply excluded/renormalized) and
        # strictly HIGHER than the floored unprofitable case, since exclusion != floor-to-worst.
        assert score_a == score_b == score_c
        unprofitable_score = loader._score_value(
            dict(self._base_metrics(), pe_ratio=None, pe_ratio_unavailable_reason="unprofitable_stock"),
            "UNPROFITABLE",
        )
        assert unprofitable_score < score_a


class TestForwardPeNegativeForecastFloor:
    def _base_metrics(self) -> dict:
        return {
            "pe_ratio": 15.0,
            "pb_ratio": 2.0,
            "ps_ratio": 3.0,
        }

    def test_negative_forecast_scores_lower_than_positive_forecast(self):
        loader = StockScoresLoader()

        positive_forecast = dict(self._base_metrics(), forward_pe=18.0)
        negative_forecast = dict(
            self._base_metrics(), forward_pe=None, forward_pe_unavailable_reason="negative_forward_eps"
        )

        positive_score = loader._score_value(positive_forecast, "POSITIVE_FORECAST")
        negative_score = loader._score_value(negative_forecast, "NEGATIVE_FORECAST")

        assert isinstance(positive_score, float)
        assert isinstance(negative_score, float)
        assert negative_score < positive_score

    def test_negative_forecast_still_produces_a_real_score(self):
        loader = StockScoresLoader()

        score = loader._score_value(
            dict(
                self._base_metrics(),
                forward_pe=None,
                forward_pe_unavailable_reason="negative_forward_eps",
            ),
            "NEGATIVE_FORECAST",
        )

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_genuine_no_analyst_coverage_is_not_floored(self):
        """forward_pe None with the genuine "no_analyst_estimates" reason (real absence of
        coverage, not a negative forecast) must stay excluded/renormalized, not floored."""
        loader = StockScoresLoader()

        no_coverage = dict(self._base_metrics(), forward_pe=None, forward_pe_unavailable_reason="no_analyst_estimates")
        without_key = self._base_metrics()

        score_a = loader._score_value(no_coverage, "A")
        score_b = loader._score_value(without_key, "B")
        assert score_a == score_b

        negative_forecast_score = loader._score_value(
            dict(
                self._base_metrics(),
                forward_pe=None,
                forward_pe_unavailable_reason="negative_forward_eps",
            ),
            "NEGATIVE_FORECAST",
        )
        assert negative_forecast_score < score_a
