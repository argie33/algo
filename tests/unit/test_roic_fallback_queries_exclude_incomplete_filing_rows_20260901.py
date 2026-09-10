"""Regression test (2026-09-01, /goal data-gap audit): three more ROIC-feeding fallback
queries in `_compute_quality_metrics` had the same missing `data_unavailable IS NOT TRUE`
filter bug as gross_profit's fallback (see
test_gross_profit_fallback_excludes_incomplete_filing_row_20260901.py) - income_tax_expense/
pretax_income/operating_income/interest_expense (both tiers), stockholders_equity/
cash_and_equivalents (both tiers), and long_term_debt (both tiers).

Live-confirmed 2026-09-01: unfiltered picks come from a data_unavailable=True row for 374
symbols (roic tax triple), 2,989 symbols (equity/cash), 1,267 symbols (long_term_debt). The
data_unavailable=True reason is a mix of `incomplete_sec_filing_*` (a genuinely partial filing)
and `stale_fiscal_year_not_confirmed_by_full_sec_refetch` (a row a fresh full SEC refetch no
longer reproduces at all - documented in loaders/helpers/sec_base.py as "a stale orphan, not a
legitimate gap") - both mean the row's values should not be trusted, confirming the fix is
correct for both reasons, not overly aggressive.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _RecordingCursor:
    """Records every query's SQL text, keyed by a distinctive substring, so each fallback
    site's filter can be asserted on independently without depending on execution order."""

    def __init__(self):
        self.queries_by_marker = {}
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query
        for marker in (
            "SELECT income_tax_expense",
            "SELECT stockholders_equity, cash_and_equivalents",
            "SELECT long_term_debt",
        ):
            if marker in query:
                self.queries_by_marker.setdefault(marker, []).append(query)

    def fetchall(self):
        return []

    def fetchone(self):
        return None  # force every fallback tier to run (no early-exit on a canned row)


class _RecordingDatabaseContext:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *exc):
        return False


def _quality_row():
    # Same 34-column shape as the gross_profitability fixture - all optional fields None so
    # every fallback branch in _compute_quality_metrics is forced to run.
    return (
        None,
        200_000_000.0,
        700_000_000.0,
        50_000_000.0,
        None,
        None,
        150_000_000.0,
        100_000_000.0,
        2025,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


class TestRoicFallbackQueriesExcludeIncompleteFilingRows:
    def test_all_six_fallback_query_sites_filter_on_data_unavailable(self, monkeypatch):
        import loaders.load_value_quality_growth_metrics as mod

        cursor = _RecordingCursor()
        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _RecordingDatabaseContext(cursor))
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

        loader._compute_quality_metrics("NOFALLBACK", _quality_row(), ev_metrics=None)

        tax_queries = cursor.queries_by_marker.get("SELECT income_tax_expense", [])
        equity_queries = cursor.queries_by_marker.get("SELECT stockholders_equity, cash_and_equivalents", [])
        debt_queries = cursor.queries_by_marker.get("SELECT long_term_debt", [])

        assert len(tax_queries) == 2, "expected both the 3-year and full-history tax fallback tiers to run"
        assert len(equity_queries) == 2, "expected both the 3-year and full-history equity/cash fallback tiers to run"
        # 2026-09-10: a new last-resort DebtComponentsFallbackMixin._fetch_total_debt_components_
        # fallback tier (loaders/helpers/vqg_quality_debt_fallback.py) fires whenever the
        # original long_term_debt-only anchor fallback still comes back None (ATHR/BRNS-shaped:
        # real short_term_debt/lease-liability debt, no long_term_debt tag ever) - its own
        # "long_term_debt, short_term_debt, ..." column-list query also matches this test's
        # "SELECT long_term_debt" marker, doubling the expected count at each of the two
        # existing call sites (roic_pct-feeding position + roce_pct-feeding position).
        assert len(debt_queries) == 4, (
            "expected both original debt tiers plus the new components-fallback tier at each site"
        )

        for query in tax_queries + equity_queries + debt_queries:
            assert "data_unavailable IS NOT TRUE" in query
