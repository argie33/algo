"""Regression test: pb_ratio_unavailable_reason must distinguish a symbol that has never once
tagged a real stockholders_equity value in its entire filing history from the genuinely
ambiguous "found an equity value somewhere but pb_ratio still came out null" remainder that
correctly stays "missing_sec_data".

Found live 2026-09-02 (goal: "keep the missing-data number going down" SEC/XBRL audit, same
pattern as test_pe_ratio_never_tagged_eps_reason_20260902.py): the existing equity lookup in
pb_ratio_reason (full-history query, no fiscal-year window) already distinguishes "found a row"
from "found nothing" via `equity_row`, but both cases fell into "missing_sec_data". Live-verified
23 of the universe's 65 pb_ratio "missing_sec_data" rows are the "found nothing" case - real
filers with real total_assets/total_liabilities but zero stockholders_equity concept ever
tagged. Spot-checked EPD, NRP, SPH directly against annual_balance_sheet: MLPs that tag
"Partners' Capital" instead of a "StockholdersEquity" concept.
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


class _EquityQueryCursor:
    def __init__(self, equity_row):
        self._equity_row = equity_row
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "SELECT stockholders_equity" in self.last_query:
            return self._equity_row
        return None

    def fetchall(self):
        return []


class TestPbRatioNeverTaggedEquityReason:
    def test_no_equity_row_anywhere_reports_never_tagged(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _EquityQueryCursor(equity_row=None)
            metrics = loader._build_value_metrics(
                "EPD",
                _FakeSecValRow(
                    {"pe_ratio": 12.0, "peg_ratio": 1.0, "pb_ratio": None, "current_price": 30.0, "market_cap": 6e10}
                ),
            )

        assert metrics["pb_ratio"] is None
        assert metrics["pb_ratio_unavailable_reason"] == "stockholders_equity_never_tagged_in_filings"

    def test_real_negative_equity_still_reports_negative_book_value(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _EquityQueryCursor(equity_row=(-500_000_000.0,))
            metrics = loader._build_value_metrics(
                "NEGEQCO",
                _FakeSecValRow(
                    {"pe_ratio": 8.0, "peg_ratio": 1.0, "pb_ratio": None, "current_price": 5.0, "market_cap": 5e8}
                ),
            )

        assert metrics["pb_ratio"] is None
        assert metrics["pb_ratio_unavailable_reason"] == "negative_book_value"

    def test_real_positive_equity_with_pb_still_null_keeps_generic_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _EquityQueryCursor(equity_row=(200_000_000.0,))
            metrics = loader._build_value_metrics(
                "AMBIGCO",
                _FakeSecValRow(
                    {"pe_ratio": 10.0, "peg_ratio": 1.0, "pb_ratio": None, "current_price": 10.0, "market_cap": 1e9}
                ),
            )

        assert metrics["pb_ratio"] is None
        assert metrics["pb_ratio_unavailable_reason"] == "missing_sec_data"
