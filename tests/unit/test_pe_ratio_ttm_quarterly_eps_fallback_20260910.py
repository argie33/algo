"""Regression test: pe_ratio_unavailable_reason must fall back to a TTM EPS derived from 4 real
quarterly_income_statement rows before concluding "eps_never_tagged_in_filings", when the
symbol has zero usable annual_income_statement EPS but a complete real quarterly history.

Found live 2026-09-10 (goal: "SEC/XBRL missing data under 300" push). Live-confirmed via SKT
(Tanger Inc - a real, decades-old public REIT whose 10-Ks apparently never tag a calendar-year-
duration EarningsPerShareBasic/Diluted fact at all, only Q1-Q3) and AADX/AIB-style recent IPOs
(a real 10-K on file, but its own annual_income_statement rows are correctly flagged
data_unavailable/'incomplete_sec_filing_income'): both shapes had real, complete quarterly EPS
sitting unused, mislabeled under the "Missing SEC/XBRL data" bucket instead of the correct
"Legitimate / not applicable" (unprofitable_stock) bucket most of them actually belong to.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _EpsQueryCursor:
    """Mimics both the annual (fetchone) and quarterly (fetchall) EPS lookups this cascade
    makes, routed by which query string is executed - same convention as the sibling
    test file's _EpsQueryCursor."""

    def __init__(self, quarterly_eps_rows):
        self._quarterly_eps_rows = quarterly_eps_rows
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        return None

    def fetchall(self):
        if self.last_query and "quarterly_income_statement" in self.last_query:
            return self._quarterly_eps_rows
        return []


class TestPeRatioTtmQuarterlyEpsFallback:
    def test_four_real_negative_quarters_reports_unprofitable_not_never_tagged(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _EpsQueryCursor(
                quarterly_eps_rows=[(-1.04,), (-0.0878,), (-0.05,), (-0.0424,)]
            )
            metrics = loader._build_value_metrics(
                "AADX",
                _FakeSecValRow({"pe_ratio": None, "pb_ratio": 1.2, "current_price": 5.0, "market_cap": 100_000_000.0}),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "unprofitable_stock"

    def test_fewer_than_four_real_quarters_keeps_never_tagged_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _EpsQueryCursor(quarterly_eps_rows=[(-1.5,), (-0.5,)])
            metrics = loader._build_value_metrics(
                "TOONEW",
                _FakeSecValRow({"pe_ratio": None, "pb_ratio": 1.0, "current_price": 5.0, "market_cap": 50_000_000.0}),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "eps_never_tagged_in_filings"
