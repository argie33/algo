"""Regression test (2026-09-10, goal: "under 500" missing-XBRL push): the anchor-row query's
`acf.data_unavailable = FALSE` JOIN condition discards operating_cash_flow/free_cash_flow
whenever the row is flagged "incomplete_sec_filing_cashflow" - usually correct, since that flag
normally means operating_cash_flow itself is the missing field required_metrics enforces (see
sec_cash_flow.py). But a stale flag can outlive a later backfill: live-confirmed BEBE/PONO have
a real, current-year operating_cash_flow despite data_unavailable=TRUE, so free_cash_flow
(which shares this exact symbol population) was also mislabeled "missing_sec_data".

vqg_quality_inputs.py's existing same-year dividends_paid rescue (2026-08-18) already queries
annual_cash_flow directly for this fiscal year, bypassing the data_unavailable filter - this
extends that same query/rescue to operating_cash_flow and free_cash_flow.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(net_income=100.0, operating_cash_flow=None, free_cash_flow=None, dividends_paid=None):
    row = [None] * 34
    row[0] = 1000.0  # stockholders_equity
    row[3] = net_income
    row[6] = 500.0  # current_assets
    row[7] = 100.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[13] = operating_cash_flow
    row[14] = free_cash_flow
    row[15] = dividends_paid
    return row


class _RoutingCursor:
    def __init__(self, same_year_row=None):
        self._same_year_row = same_year_row
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        if "annual_cash_flow" in self._last_query and "operating_cash_flow" in self._last_query:
            return self._same_year_row
        return None

    def fetchall(self):
        return []


class TestOperatingCashFlowIncompleteRowFallback:
    def test_masked_but_present_ocf_and_fcf_are_recovered(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(same_year_row=(None, -220859.0, -300000.0))
            metrics = loader._compute_quality_metrics(
                "PONO", _quality_row(operating_cash_flow=None, free_cash_flow=None)
            )

        assert metrics["operating_cash_flow"] == -220859.0
        assert metrics.get("operating_cash_flow_unavailable_reason") is None
        assert metrics["free_cash_flow"] == -300000.0
        assert metrics.get("free_cash_flow_unavailable_reason") is None

    def test_genuinely_missing_ocf_stays_none(self):
        # The common case: the row is flagged BECAUSE operating_cash_flow is really absent -
        # the rescue query finds no row (or a row with None values) and must not fabricate one.
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(same_year_row=None)
            metrics = loader._compute_quality_metrics(
                "REALGAP", _quality_row(operating_cash_flow=None, free_cash_flow=None)
            )

        assert metrics["operating_cash_flow"] is None
        assert metrics["free_cash_flow"] is None

    def test_explicit_ocf_never_overwritten_by_fallback(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # A different value (999.0) in the fallback row - must not leak in since OCF is
            # already known from the anchor row itself.
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(same_year_row=(None, 999.0, None))
            metrics = loader._compute_quality_metrics(
                "KNOWNOCF", _quality_row(operating_cash_flow=50_000_000.0, free_cash_flow=None)
            )

        assert metrics["operating_cash_flow"] == 50_000_000.0
