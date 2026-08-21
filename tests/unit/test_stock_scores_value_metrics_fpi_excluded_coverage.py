"""Regression test for the 2026-08-21 fix (goal session - "why is stock_scores
intermittently stale"): StockScoresLoader.audit_upstream_coverage() trusted
data_loader_status.completion_pct for value_metrics, but that stat counts a symbol as
"failed" whenever value_metrics.data_unavailable=TRUE - which load_value_quality_growth_
metrics.py sets for EVERY foreign private issuer, since load_sec_valuations.py deliberately
and permanently refuses to compute market_cap/pe/pb/etc. for FPIs (20-F/40-F filers report
share counts in non-ADS home-market units, not a fixable gap).

Live-confirmed: of 982 active symbols with value_metrics.data_unavailable=TRUE, 795 (81%)
are FPIs. Raw completion_pct read 80.8% and hard-failed the real stock_scores run this
session even though the loader had completed cleanly - recomputing coverage over the
non-FPI universe only (the population this gate can actually judge loader health from)
gave 95.37% for the exact same data, clearing the existing 95% bar.

Fix: audit_upstream_coverage() now recomputes value_metrics coverage via
_value_metrics_coverage_excluding_fpi() (a live query joining company_info_sec.
is_foreign_private_issuer) instead of trusting the FPI-polluted completion_pct.
"""

from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader


def _loader() -> StockScoresLoader:
    return StockScoresLoader.__new__(StockScoresLoader)


def _run_audit(raw_rows, fpi_excluded_fetchone):
    loader = _loader()
    cur = MagicMock()
    cur.fetchall.return_value = raw_rows
    cur.fetchone.return_value = fpi_excluded_fetchone

    def fake_db_context(mode, **kwargs):
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        return ctx

    with patch("loaders.load_stock_scores.DatabaseContext", side_effect=fake_db_context):
        loader.audit_upstream_coverage()
    return cur


class TestValueMetricsFpiExcludedCoverage:
    def test_low_raw_completion_but_healthy_non_fpi_coverage_does_not_raise(self):
        """The exact live scenario: raw completion_pct=80.8% (FPI-polluted), but the
        non-FPI population is 95.37% covered - must not hard-fail."""
        raw_rows = [
            ("value_metrics", 80.8, 4122, 5100),
            ("stability_metrics", 99.0, 5050, 5100),
        ]
        _run_audit(raw_rows, fpi_excluded_fetchone=(3851, 4038))  # 95.37%

    def test_genuinely_low_non_fpi_coverage_still_raises(self):
        """A real loader problem affecting the non-FPI (judgeable) population must still
        be caught, even if the raw FPI-polluted number happens to look similar."""
        raw_rows = [
            ("value_metrics", 80.8, 4122, 5100),
            ("stability_metrics", 99.0, 5050, 5100),
        ]
        try:
            _run_audit(raw_rows, fpi_excluded_fetchone=(3000, 4038))  # 74.3%
            raise AssertionError("expected RuntimeError for genuinely low non-FPI coverage")
        except RuntimeError as e:
            assert "value_metrics" in str(e)

    def test_fpi_query_failure_falls_back_to_raw_completion_pct(self):
        """If the FPI-excluded query itself fails (e.g. company_info_sec join breaks),
        fall back to the original raw completion_pct behavior rather than silently
        skipping the gate entirely."""
        raw_rows = [
            ("value_metrics", 80.0, 4000, 5000),
            ("stability_metrics", 99.0, 5050, 5100),
        ]
        loader = _loader()
        cur = MagicMock()
        cur.fetchall.return_value = raw_rows
        cur.fetchone.side_effect = RuntimeError("db error")

        def fake_db_context(mode, **kwargs):
            ctx = MagicMock()
            ctx.__enter__.return_value = cur
            ctx.__exit__.return_value = False
            return ctx

        with patch("loaders.load_stock_scores.DatabaseContext", side_effect=fake_db_context):
            try:
                loader.audit_upstream_coverage()
                raise AssertionError("expected RuntimeError falling back to raw completion_pct")
            except RuntimeError as e:
                assert "value_metrics" in str(e)
