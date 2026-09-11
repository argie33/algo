"""Regression: sustainable_growth_rate's dividend_data TTM recovery must not multiply a
per-share dividend sum by a shares_outstanding value sec_valuations has already flagged as
scale-mismatched.

Bug (confirmed live 2026-09-11): CVKD (Cadrenal Therapeutics) has two disagreeing
shares_outstanding values across tables - company_info_sec says 3,567,592, sec_valuations
says 1,993,757 (sec_valuations.reason = "shares_outstanding_scale_mismatch"). The TTM
dividend recovery added 2026-09-05 (test_sustainable_growth_rate_dividend_reason.py's
TestSustainableGrowthRateDividendDataRecovery) blindly multiplies dividend_data's per-share
sum by shares_outstanding with no check against this known inconsistency - CVKD's real TTM
$33/share x 3.57M shares = $117.7M dividends_paid against a $1.8M equity base, which only
avoided corrupting the SGR value by accident (via the unrelated MAX_PLAUSIBLE_GROWTH_PCT
implausible-ratio bound). A symbol with smaller magnitudes could silently produce a wrong-but-
plausible SGR from the same untrustworthy shares_outstanding.
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


class _ScaleMismatchCursor:
    """Mock cursor: dividend_data has real recent history, sec_valuations.reason is
    "shares_outstanding_scale_mismatch" for this symbol."""

    def __init__(self):
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        if "sec_valuations" in self._last_query:
            return ("shares_outstanding_scale_mismatch",)
        if "SUM(dividend_per_share)" in self._last_query:
            # Would recover a real-looking TTM figure if not gated - must never be reached.
            return (33.0,)
        if "dividend_data" in self._last_query:
            return (1,)
        return None

    def fetchall(self):
        return []


class TestSustainableGrowthRateSharesOutstandingScaleMismatch:
    def test_scale_mismatched_shares_outstanding_skips_ttm_recovery(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _ScaleMismatchCursor()
            metrics = loader._compute_quality_metrics(
                "CVKD",
                _quality_row(
                    stockholders_equity=1000.0, net_income=-100.0, dividends_paid=None, shares_outstanding=3567592.0
                ),
            )
        assert metrics["sustainable_growth_rate"] is None
        assert metrics["sustainable_growth_rate_unavailable_reason"] == "shares_outstanding_scale_mismatch"

    def test_non_mismatched_shares_outstanding_unaffected(self):
        # sec_valuations.reason is something else (or no row) - TTM recovery proceeds as before.
        loader = _make_loader()

        class _CleanCursor(_ScaleMismatchCursor):
            def fetchone(self):
                if "sec_valuations" in self._last_query:
                    return ("no_income_statement",)
                if "SUM(dividend_per_share)" in self._last_query:
                    return (2.0,)
                if "dividend_data" in self._last_query:
                    return (1,)
                return None

        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _CleanCursor()
            metrics = loader._compute_quality_metrics(
                "REALPAY",
                _quality_row(
                    stockholders_equity=1000.0, net_income=100.0, dividends_paid=None, shares_outstanding=10.0
                ),
            )
        # Recovered dividends_paid = 2.0/share * 10.0 shares = 20.0.
        # ROE = 100/1000 = 10%, retention_ratio = 1 - 20/100 = 0.8 -> SGR = 8.0
        assert metrics["sustainable_growth_rate"] == 8.0
        assert metrics.get("sustainable_growth_rate_unavailable_reason") is None
