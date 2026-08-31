#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_value's treatment of unprofitable/
negative-forecast companies (loaders/load_stock_scores.py).

Added 2026-08-28 (goal: "is this value score right per industry best practice" - the P/E vs.
E/P gap). Originally guarded that BOTH trailing pe_ratio and forward_pe floored unprofitable/
negative-forecast companies at the worst sub-score (0) and counted them toward total_weight,
rather than excluding/renormalizing them as if the field simply didn't exist.

Trailing P/E was REMOVED FROM SCORING ENTIRELY 2026-08-30 (weight-derivation pass - see
loaders/load_stock_scores.py's _score_value docstring "CURRENT LIVE FORMULA" note for the full
trail): a corrected joint regression (fixing a real measurement bug - unprofitable companies
were being scored as NEUTRAL instead of WORST in the test script, understating trailing P/E's
true weakness) found trailing P/E's coefficient statistically indistinguishable from zero in
every window tested once correctly measured (never significant, stays weakly positive
throughout - re-verified directly against the live DB 2026-08-31, correcting an earlier claim
of a sign flip that did not reproduce), and no mainstream Value methodology (MSCI included)
scores trailing E/P at all. TestPeUnprofitableFloor below is INVERTED from its original form to
guard the current
(not-scored) wiring: pe_ratio, in any state, must not move value_score at all any more.

Forward P/E's own unprofitable-forecast floor is UNCHANGED by this - TestForwardPeScored below
still guards the original (scored, floored) behavior.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestPeNotScored:
    """Trailing P/E (pe_ratio) is not part of the current Value formula - see module docstring.
    pe_ratio, whether present, unprofitable, or genuinely missing, must not move value_score in
    any direction any more."""

    def _base_metrics(self) -> dict:
        return {
            "pb_ratio": 2.0,
            "ps_ratio": 3.0,
        }

    def test_pe_value_does_not_move_value_score(self):
        loader = StockScoresLoader()

        profitable = dict(self._base_metrics(), pe_ratio=15.0)
        without_pe = self._base_metrics()

        profitable_score = loader._score_value(profitable, "PROFITABLE")
        without_pe_score = loader._score_value(without_pe, "WITHOUT_PE")

        assert isinstance(profitable_score, float)
        assert isinstance(without_pe_score, float)
        assert profitable_score == without_pe_score

    def test_unprofitable_reason_does_not_move_value_score(self):
        """Trailing P/E's own unprofitable-company floor is gone along with the rest of its
        scoring - an unprofitable company must score IDENTICALLY to a symbol with no pe_ratio
        data at all, since neither contributes to value_score any more."""
        loader = StockScoresLoader()

        unprofitable = dict(self._base_metrics(), pe_ratio=None, pe_ratio_unavailable_reason="unprofitable_stock")
        without_key = self._base_metrics()

        unprofitable_score = loader._score_value(unprofitable, "UNPROFITABLE")
        without_key_score = loader._score_value(without_key, "WITHOUT_KEY")

        assert isinstance(unprofitable_score, float)
        assert isinstance(without_key_score, float)
        assert unprofitable_score == without_key_score

    def test_score_still_computed_from_remaining_inputs(self):
        """A symbol with only pb_ratio/ps_ratio (no pe_ratio at all) must still get a real
        value_score - pe_ratio was never required."""
        loader = StockScoresLoader()

        score = loader._score_value(self._base_metrics(), "NO_PE")

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0


class TestForwardPeScored:
    """Forward P/E was scored 2026-08-28 through 2026-08-29 (with a negative-forecast floor,
    same treatment as trailing P/E used to have), REMOVED 2026-08-30 (user directive - reverting
    Value to its 08-26/08-28 7-input formula, which never included Forward P/E), then RESTORED
    AGAIN 2026-08-30 (same day, later user directive - "add forward PE back to the value
    score"), taking the 7% freed by Margin of Safety's removal from scoring the same request
    (see test_stock_scores_margin_of_safety_wiring.py). Guards the CURRENT (scored) wiring:
    forward_pe is a real weighted value_score component, with the same unprofitable/negative-
    forecast floor treatment trailing P/E used to have before it was removed from scoring
    entirely (see TestPeNotScored above) - forward_pe's own floor is UNCHANGED by that removal."""

    def _base_metrics(self) -> dict:
        return {
            "pe_ratio": 15.0,
            "pb_ratio": 2.0,
            "ps_ratio": 3.0,
        }

    def test_forward_pe_value_moves_value_score(self):
        loader = StockScoresLoader()

        with_forward_pe = dict(self._base_metrics(), forward_pe=18.0)
        without_forward_pe = self._base_metrics()

        score_with = loader._score_value(with_forward_pe, "WITH_FWD_PE")
        score_without = loader._score_value(without_forward_pe, "WITHOUT_FWD_PE")

        assert score_with != score_without

    def test_negative_forecast_scores_lower_than_positive(self):
        """A negative-forecast-EPS company (reason=negative_forward_eps) is floored at 0 for
        forward_pe's sub-score - it must score LOWER than an otherwise-identical company with a
        real forward_pe."""
        loader = StockScoresLoader()

        positive_forecast = dict(self._base_metrics(), forward_pe=18.0)
        negative_forecast = dict(
            self._base_metrics(), forward_pe=None, forward_pe_unavailable_reason="negative_forward_eps"
        )

        positive_score = loader._score_value(positive_forecast, "POSITIVE")
        negative_score = loader._score_value(negative_forecast, "NEGATIVE")

        assert isinstance(positive_score, float)
        assert isinstance(negative_score, float)
        assert negative_score < positive_score

    def test_negative_forecast_still_produces_a_real_score(self):
        loader = StockScoresLoader()

        score = loader._score_value(
            dict(self._base_metrics(), forward_pe=None, forward_pe_unavailable_reason="negative_forward_eps"),
            "NEGATIVE_FORECAST",
        )

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_genuinely_missing_forward_pe_is_not_floored(self):
        """A forward_pe of None with no reason (or a non-"negative_forward_eps" reason, e.g.
        no_analyst_estimates) means the true forward P/E is UNKNOWN, not known-bad - must still
        be excluded/renormalized, not floored to 0."""
        loader = StockScoresLoader()

        missing_no_reason = dict(self._base_metrics(), forward_pe=None)
        missing_other_reason = dict(
            self._base_metrics(), forward_pe=None, forward_pe_unavailable_reason="no_analyst_estimates"
        )
        without_key = self._base_metrics()

        score_a = loader._score_value(missing_no_reason, "A")
        score_b = loader._score_value(missing_other_reason, "B")
        score_c = loader._score_value(without_key, "C")

        assert score_a == score_b == score_c
        negative_forecast_score = loader._score_value(
            dict(self._base_metrics(), forward_pe=None, forward_pe_unavailable_reason="negative_forward_eps"),
            "NEGATIVE_FORECAST",
        )
        assert negative_forecast_score < score_a
