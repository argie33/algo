"""Regression test for the 2026-09-10 total_assets derivation fallback (under-500
XBRL coverage push).

Live-confirmed via real SEC companyfacts JSON: BTTC (Black Titan Corp, CIK
0002034400) and XLAB (Exascale Labs Holdings, CIK 0002109869) both tag
"Liabilities" and "StockholdersEquity" directly every period (real, non-null,
exactly-offsetting values - both are pre-revenue shells with zero net assets)
but never tag a combined "Assets" concept at all. Since "stockholders_equity"
alone satisfies transform()'s _has_required() any()-check for the balance
statement type, these rows were already reaching the "valid" branch with
total_assets left permanently NULL - not a genuine gap, just the balance-sheet
identity Assets = Liabilities + StockholdersEquity never being applied in this
direction (only the reverse, total_liabilities = total_assets -
stockholders_equity, existed - see
test_financial_statements_derives_total_liabilities_fallback.py). This
surfaced downstream as quality_metrics "no_recent_total_assets_reported" /
growth_metrics "stockholders_equity_not_reported"-adjacent gaps on the Scores
coverage report despite both real balance-sheet inputs being on file.

ConsolidatedFinancialStatementsLoader.transform() now fills total_assets =
total_liabilities + stockholders_equity only when total_assets is NULL and
both inputs are present.
"""

from decimal import Decimal
from unittest.mock import patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


class TestTotalAssetsDerivationFallback:
    def _make_loader(self) -> ConsolidatedFinancialStatementsLoader:
        return ConsolidatedFinancialStatementsLoader(statement_type="balance", period="annual")

    def test_derives_total_assets_when_missing(self):
        loader = self._make_loader()
        rows = [
            {
                "symbol": "BTTC",
                "fiscal_year": 2025,
                "total_assets": None,
                "stockholders_equity": Decimal("-167120"),
                "total_liabilities": Decimal("167120"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            result = loader.transform(rows)

        assert result[0]["total_assets"] == Decimal("0")

    def test_does_not_overwrite_real_total_assets(self):
        loader = self._make_loader()
        rows = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2025,
                "total_assets": Decimal("500000000"),
                "stockholders_equity": Decimal("100000000"),
                "total_liabilities": Decimal("400000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            result = loader.transform(rows)

        # A filer that DOES report Assets directly must keep that real value,
        # not have it silently recomputed.
        assert result[0]["total_assets"] == Decimal("500000000")

    def test_does_not_derive_for_income_statement_type(self):
        loader = ConsolidatedFinancialStatementsLoader(statement_type="income", period="annual")
        rows = [
            {
                "symbol": "BTTC",
                "fiscal_year": 2025,
                "revenue": Decimal("0"),
                "net_income": Decimal("-167120"),
                "total_assets": None,
                "stockholders_equity": Decimal("-167120"),
                "total_liabilities": Decimal("167120"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            result = loader.transform(rows)

        # total_assets isn't a real income-statement field; the balance-only
        # derivation must not fire outside statement_type == "balance".
        assert result[0]["total_assets"] is None

    def test_leaves_null_when_inputs_incomplete(self):
        loader = self._make_loader()
        rows = [
            {
                "symbol": "SPINOFFCO",
                "fiscal_year": 2026,
                "total_assets": None,
                "stockholders_equity": Decimal("100000000"),
                "total_liabilities": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            result = loader.transform(rows)

        assert result[0]["total_assets"] is None
