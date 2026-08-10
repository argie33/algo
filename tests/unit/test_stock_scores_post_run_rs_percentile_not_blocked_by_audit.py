"""Regression test for the 2026-08-10 fix: StockScoresLoader.post_run() ran
audit_upstream_coverage() before update_rs_percentiles(), so a transient audit failure
(a momentary dip in value_metrics/stability_metrics coverage, unrelated to momentum_score)
crashed the whole loader subprocess and prevented rs_percentile from ever being computed -
even though all per-symbol scoring (including momentum_score) had already completed.

Live-reproduced: stock_scores showed 100% per-symbol completion (4917/4917) but
rs_percentile was NULL for all 4617 usable rows, because post_run()'s audit step raised
before reaching the RS-ranking step. Phase 7 then silently filtered out every single
candidate (100+ otherwise-qualified) since it hard-requires rs_percentile, with a generic
"no signals found" message that never named the real cause.

Fixed by running update_rs_percentiles() first (it only reads momentum_score, which the
audit doesn't check), then the audit - so a coverage problem still fails the run for
visibility, but no longer collaterally blocks the unrelated, Phase-7-critical RS ranking.
"""

from unittest.mock import MagicMock, call, patch

from loaders.load_stock_scores import StockScoresLoader


def _loader() -> StockScoresLoader:
    return StockScoresLoader.__new__(StockScoresLoader)


class TestPostRunOrdering:
    def test_rs_percentiles_computed_even_when_audit_raises(self):
        loader = _loader()
        loader.update_rs_percentiles = MagicMock()
        loader.audit_upstream_coverage = MagicMock(side_effect=RuntimeError("value_metrics coverage low"))

        try:
            loader.post_run()
            assert False, "expected the audit's RuntimeError to still propagate"
        except RuntimeError:
            pass

        loader.update_rs_percentiles.assert_called_once()

    def test_rs_percentiles_runs_before_audit(self):
        loader = _loader()
        calls = []
        loader.update_rs_percentiles = MagicMock(side_effect=lambda: calls.append("rs"))
        loader.audit_upstream_coverage = MagicMock(side_effect=lambda: calls.append("audit"))

        loader.post_run()

        assert calls == ["rs", "audit"], f"expected rs_percentile ranking before the audit, got: {calls}"

    def test_healthy_audit_still_runs_after_rs_percentiles(self):
        loader = _loader()
        loader.update_rs_percentiles = MagicMock()
        loader.audit_upstream_coverage = MagicMock()

        loader.post_run()

        loader.update_rs_percentiles.assert_called_once()
        loader.audit_upstream_coverage.assert_called_once()
