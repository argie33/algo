"""Regression test (2026-09-11, /goal session): a negative-equity sign-flip can make
return_on_equity look like a real positive percentage (e.g. net_income=-50M/equity=-10.6M ->
"ROE"=+471%, live-confirmed on OSTX/ARMP/AEON/CDT/CMPS). The scoring layer already floors this
exact shape to 0 (update_quality_sector_neutral_scores() in loaders/helpers/vqg_quality_batch.py,
condition `roe<0 OR roa<0`) but the raw value stored in quality_metrics.roe is deliberately NOT
nulled (see test_quality_roe_negative_equity_score_floor_20260905.py, which pins keeping it) - so
before this fix, nothing told an API/dashboard consumer the displayed percentage wasn't real
profitability. Both financials.py's key-metrics endpoint and stock_details.py now surface a
distress-artifact flag computed from the identical roe/roa condition the score already applied,
requiring no new column and no risk of a fiscal-year mismatch (same row, same stored values).
"""

import importlib
import inspect

financials = importlib.import_module("lambda.api.routes.financials")
stock_details = importlib.import_module("lambda.api.routes.scores_handlers.stock_details")


def test_key_metrics_select_includes_distress_artifact_flag():
    source = inspect.getsource(financials.handle)
    start = source.index('if endpoint == "key-metrics"')
    end = source.index("if endpoint ==", start + 1)
    block = source[start:end]
    assert "return_on_equity_distress_artifact" in block
    assert "qm.roe < 0 OR qm.roa < 0" in block


def test_stock_details_quality_inputs_includes_distress_artifact_flag():
    source = inspect.getsource(stock_details._get_stock_details)
    assert "return_on_equity_pct_distress_artifact" in source


class TestDistressArtifactComputation:
    """Mirrors the exact (roe<0 OR roa<0) condition from the scoring layer's floor."""

    @staticmethod
    def _compute(roe, roa):
        return roe is not None and roa is not None and (float(roe) < 0 or float(roa) < 0)

    def test_sign_flip_case_flagged(self):
        # OSTX-shaped: roe positive (sign-flip artifact), roa negative (the real loss)
        assert self._compute(471.71, -420.41) is True

    def test_genuine_negative_roe_flagged(self):
        assert self._compute(-15.0, -10.0) is True

    def test_normal_profitable_company_not_flagged(self):
        assert self._compute(18.5, 6.2) is False

    def test_extreme_but_positive_equity_case_not_flagged(self):
        # HRB/CVLT-shaped: extreme ROE from buyback-thinned equity, but roa is genuinely positive
        assert self._compute(624.40, 18.59) is False

    def test_missing_roa_not_flagged(self):
        # Can't verify the sign-flip without roa - matches the scoring layer's own
        # "omit rather than penalize for an unrelated data gap" precedent.
        assert self._compute(30.0, None) is False

    def test_missing_roe_not_flagged(self):
        assert self._compute(None, -5.0) is False
