"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep): an ETF
(SPY/QQQ/IWM - files N-1A/N-CSR under the Investment Company Act, never a 10-K) has ZERO
annual_balance_sheet and ZERO annual_income_statement rows. `_compute_quality_metrics`'s
`if not quality_row:` early return and `_compute_growth_metrics`'s `if not income_rows:`
early return both used to fall back to the generic "missing_sec_data" default for every
column, mislabeling a permanent business-model fact as an actionable SEC/XBRL data gap -
live-confirmed SPY's entire quality_metrics row (45 *_unavailable_reason columns) and
growth_metrics row carried this label despite `_get_etf_symbols()` (added 2026-09-05)
already existing for exactly this shape, just never wired into these two early returns.

Both now check `_get_etf_symbols()` and report 'etf_no_sec_filings' instead - the same
reason sec_valuations_income_context.py's own ETF carve-out uses for the identical "no SEC
financial statements at all" fact, already mapped to "Legitimate / not applicable".
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestEtfZeroBalanceSheetHistoryReason:
    def test_etf_with_no_balance_sheet_row_reports_etf_no_sec_filings(self):
        loader = _make_loader()
        with patch.object(type(loader), "_get_etf_symbols", return_value=frozenset({"SPY"})):
            result = loader._compute_quality_metrics("SPY", None)

        assert result["reason"] == "etf_no_sec_filings"
        assert result["current_ratio_unavailable_reason"] == "etf_no_sec_filings"
        assert result["roe_unavailable_reason"] == "etf_no_sec_filings"

    def test_non_etf_with_no_balance_sheet_row_keeps_generic_reason(self):
        loader = _make_loader()
        with patch.object(type(loader), "_get_etf_symbols", return_value=frozenset({"SPY"})):
            result = loader._compute_quality_metrics("ACTU", None)

        assert result["reason"] == "missing_sec_data"

    def test_etf_with_no_income_rows_reports_etf_no_sec_filings(self):
        loader = _make_loader()
        with patch.object(type(loader), "_get_etf_symbols", return_value=frozenset({"SPY"})):
            result = loader._compute_growth_metrics("SPY", [])

        assert result["reason"] == "etf_no_sec_filings"

    def test_non_etf_with_no_income_rows_keeps_generic_reason(self):
        loader = _make_loader()
        with patch.object(type(loader), "_get_etf_symbols", return_value=frozenset({"SPY"})):
            result = loader._compute_growth_metrics("ACTU", [])

        assert result["reason"] == "insufficient_history"
