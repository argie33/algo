"""Regression test for the 2026-09-09 fix (goal: SEC/XBRL missing-data count under 700):
recent IPOs (real 10-Qs filed, no 10-K yet) have zero annual_balance_sheet rows, so
quality_row_db stays None and _compute_quality_metrics short-circuits the WHOLE row to a
single generic unavailable marker - even though real quarterly_balance_sheet data exists that
could still compute debt_to_assets/current_ratio/quick_ratio directly, and roa/roe/net_margin/
sustainable_growth_rate via the net_income TTM-from-quarterly fallback added earlier this
session.

_fetch_balance_sheet_row_from_quarterly builds a substitute quality_row from the latest real
quarterly_balance_sheet snapshot (a point-in-time figure, unlike net_income/revenue - no TTM
summing), leaving every income-statement/cash-flow column None for the existing per-field
fallbacks to handle.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self, quarterly_balance_row):
        self._quarterly_balance_row = quarterly_balance_row
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        if "FROM quarterly_balance_sheet" in self._last_query:
            return self._quarterly_balance_row
        return None


class TestBalanceSheetRowFromQuarterlyFallback:
    def test_real_quarterly_row_builds_substitute_anchor(self):
        row = (
            100_000_000.0,  # stockholders_equity
            200_000_000.0,  # total_liabilities
            700_000_000.0,  # total_assets
            150_000_000.0,  # current_assets
            100_000_000.0,  # current_liabilities
            5_000_000.0,  # inventory
            50_000_000.0,  # long_term_debt
            30_000_000.0,  # cash_and_equivalents
            2026,  # fiscal_year
        )
        result = ValueQualityGrowthMetricsLoader._fetch_balance_sheet_row_from_quarterly(_FakeCursor(row), "RECENTIPO")

        assert result is not None
        assert len(result) == 35
        assert result[0] == 100_000_000.0  # stockholders_equity
        assert result[2] == 700_000_000.0  # total_assets
        assert result[3] is None  # net_income - left for the existing TTM fallback to fill
        assert result[8] == 2026  # fiscal_year
        assert result[20] == 50_000_000.0  # long_term_debt
        assert result[21] == 30_000_000.0  # cash_and_equivalents

    def test_no_quarterly_row_returns_none(self):
        result = ValueQualityGrowthMetricsLoader._fetch_balance_sheet_row_from_quarterly(_FakeCursor(None), "TOOFRESH")

        assert result is None
