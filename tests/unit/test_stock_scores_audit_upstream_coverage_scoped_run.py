"""Regression test for the 2026-08-10 fix: StockScoresLoader.audit_upstream_coverage()
trusted data_loader_status.completion_pct for value_metrics/stability_metrics, but that
row is SHARED across every invocation of load_value_quality_growth_metrics.py - including
small scoped `--symbols` diagnostic runs.

Live-reproduced: a 2-symbol diagnostic run that legitimately failed both symbols (unrelated
missing SEC valuation data) left value_metrics at symbol_count=2/symbols_loaded=0
(completion_pct=0.0), even though a real full-universe run moments earlier had loaded
5699/4917 symbols successfully. The pre-fix audit read that 0.0% and hard-failed EVERY
subsequent stock_scores run, universe-wide, until the next full run happened to overwrite
it - a tiny, non-representative symbol_count was treated as evidence of universe-wide
upstream failure.

Fixed by requiring symbol_count to be large enough to plausibly represent a full-universe
run before trusting completion_pct at all.
"""

from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader


def _loader() -> StockScoresLoader:
    return StockScoresLoader.__new__(StockScoresLoader)


def _run_audit(rows):
    loader = _loader()
    cur = MagicMock()
    cur.fetchall.return_value = rows

    def fake_db_context(mode, **kwargs):
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        return ctx

    with patch("loaders.load_stock_scores.DatabaseContext", side_effect=fake_db_context):
        loader.audit_upstream_coverage()


class TestAuditSkipsNonRepresentativeScopedRuns:
    def test_tiny_scoped_run_does_not_hard_fail_universe_wide_audit(self):
        # Exactly the reproduced scenario: a 2-symbol diagnostic run failed both.
        rows = [
            ("value_metrics", 0.0, 0, 2),
            ("stability_metrics", 98.0, 4900, 5000),
        ]
        _run_audit(rows)  # must not raise

    def test_real_full_universe_low_coverage_still_hard_fails(self):
        # A genuine full-universe run with real degraded coverage must still be caught.
        rows = [
            ("value_metrics", 80.0, 4000, 5000),
            ("stability_metrics", 98.0, 4900, 5000),
        ]
        try:
            _run_audit(rows)
            assert False, "expected RuntimeError for real universe-wide low coverage"
        except RuntimeError as e:
            assert "value_metrics" in str(e)

    def test_full_universe_healthy_coverage_passes(self):
        rows = [
            ("value_metrics", 99.0, 4950, 5000),
            ("stability_metrics", 98.0, 4900, 5000),
        ]
        _run_audit(rows)  # must not raise
