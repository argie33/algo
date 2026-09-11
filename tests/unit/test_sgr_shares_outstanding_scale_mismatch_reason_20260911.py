"""Regression: sustainable_growth_rate's "shares_outstanding is unavailable" fallback reason
must distinguish a known scale-mismatched share count from a genuinely never-tagged one,
instead of collapsing both into the generic "missing_sec_data" label.

Bug (confirmed live 2026-09-11): CVKD (Cadrenal Therapeutics)/HCWB (HCW Biologics) have real
dividend history, real net_income/stockholders_equity, but shares_outstanding reads None inside
_compute_quality_metrics - NOT because SEC never tagged it, but because
load_value_quality_growth_metrics.py's own quality_row query already excludes sec_valuations
rows flagged `reason = 'shares_outstanding_scale_mismatch'` (a fix added for the PMI/SELX/AGH/
AKTX/UHAL sustainable_growth_rate corruption bug - CVKD has two disagreeing share counts across
tables: company_info_sec=3,567,592 vs sec_valuations=1,993,757). That upstream exclusion is
correct and load-bearing - the bug is only that the missing_sec_data fallback here couldn't
tell "never tagged" apart from "excluded as untrustworthy", so both got the same generic label.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(stockholders_equity=1000.0, net_income=100.0, dividends_paid=None, shares_outstanding=None):
    row = [None] * 34
    row[0] = stockholders_equity
    row[3] = net_income
    row[6] = 500.0  # current_assets
    row[7] = 100.0  # current_liabilities
    row[11] = shares_outstanding
    row[15] = dividends_paid
    return row


class _RoutingCursor:
    """Mock cursor: dividend_data has real recent history (shares_outstanding is None so the
    TTM attempt never fires), company_info_sec has no fpi-exclusion reason, sec_valuations.reason
    is configurable."""

    def __init__(self, sec_valuations_reason):
        self._sec_valuations_reason = sec_valuations_reason
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        if "sec_valuations" in self._last_query:
            return (self._sec_valuations_reason,) if self._sec_valuations_reason is not None else None
        if "company_info_sec" in self._last_query:
            return (None,)
        if "dividend_data" in self._last_query:
            return (1,)
        return None

    def fetchall(self):
        return []


class TestSustainableGrowthRateSharesOutstandingScaleMismatch:
    def test_scale_mismatched_shares_outstanding_gets_precise_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(
                sec_valuations_reason="shares_outstanding_scale_mismatch"
            )
            metrics = loader._compute_quality_metrics(
                "CVKD",
                _quality_row(
                    stockholders_equity=1000.0, net_income=-100.0, dividends_paid=None, shares_outstanding=None
                ),
            )
        assert metrics["sustainable_growth_rate"] is None
        assert metrics["sustainable_growth_rate_unavailable_reason"] == "shares_outstanding_scale_mismatch"

    def test_genuinely_never_tagged_shares_outstanding_keeps_missing_sec_data(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(
                sec_valuations_reason="no_income_statement"
            )
            metrics = loader._compute_quality_metrics(
                "REALPAY_NOSHARES",
                _quality_row(
                    stockholders_equity=1000.0, net_income=100.0, dividends_paid=None, shares_outstanding=None
                ),
            )
        assert metrics["sustainable_growth_rate"] is None
        assert metrics["sustainable_growth_rate_unavailable_reason"] == "missing_sec_data"

    def test_no_sec_valuations_row_keeps_missing_sec_data(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(sec_valuations_reason=None)
            metrics = loader._compute_quality_metrics(
                "NOROW",
                _quality_row(
                    stockholders_equity=1000.0, net_income=100.0, dividends_paid=None, shares_outstanding=None
                ),
            )
        assert metrics["sustainable_growth_rate"] is None
        assert metrics["sustainable_growth_rate_unavailable_reason"] == "missing_sec_data"
