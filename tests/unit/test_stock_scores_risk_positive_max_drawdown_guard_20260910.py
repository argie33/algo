"""Regression test for the 2026-09-10 financial-calc integrity audit finding: _score_risk's
max_drawdown_1y handling used `abs(min(0.0, raw_value))`, which silently treated a positive
value (this column's documented convention is a negative peak-to-trough percentage) as a real
0.0 drawdown - the best possible score - with no warning or exclusion. The only current
producer (load_risk_metrics_daily.py's _calculate_max_drawdown()) can never actually emit a
positive value, so this hasn't fired in practice, but the pillar must not silently reward what
would be a real data-integrity violation if that ever changed.

Fixed: a positive max_drawdown_1y is now excluded from the Risk pillar's weighted blend
entirely (logged as a critical data-integrity violation) rather than scored as zero drawdown.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestRiskPositiveMaxDrawdownGuard:
    def _score(self, metrics: dict) -> float | dict:
        loader = StockScoresLoader.__new__(StockScoresLoader)
        return loader._score_risk({"data_unavailable": False, **metrics}, "TEST")

    def test_positive_max_drawdown_alone_excluded_not_scored_as_zero_drawdown(self):
        """A corrupted positive max_drawdown_1y must not silently score as the best possible
        (zero) drawdown - with nothing else available, it must fall through to the
        no-scores-computed marker instead of a real float score."""
        result = self._score({"max_drawdown_1y": 5.0})
        assert isinstance(result, dict), (
            f"a positive max_drawdown_1y with no other inputs must not produce a real score, got {result!r}"
        )
        assert result["reason"] == "no_risk_scores_computed"

    def test_positive_max_drawdown_excluded_when_other_metrics_present(self):
        """With beta also available, a positive (corrupted) max_drawdown_1y must not
        contribute to the weighted blend at all - only beta's 20% weight should count, which
        is below the 0.40 min-weight-available floor."""
        result = self._score({"beta": 1.0, "max_drawdown_1y": 5.0})
        assert isinstance(result, dict)
        assert result["reason"] == "insufficient_risk_inputs_thin_sample"

    def test_zero_max_drawdown_still_scores_as_best_case(self):
        """Exactly 0.0 (no decline at all) is a legitimate, if rare, real value - must still
        score normally, distinguishing it from a positive (corrupted) value."""
        result = self._score({"volatility_60d": 0.20, "volatility_252d": 0.20, "beta": 1.0, "max_drawdown_1y": 0.0})
        assert isinstance(result, float)

    def test_negative_max_drawdown_unaffected_by_guard(self):
        """Sanity check: real negative values still score exactly as before."""
        result = self._score({"volatility_60d": 0.20, "volatility_252d": 0.20, "beta": 1.0, "max_drawdown_1y": -10.0})
        assert isinstance(result, float)
