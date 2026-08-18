"""Regression test for the 2026-08-18 total_liabilities derivation fallback.

Live DB audit (goal: "no SEC data" audit) found 1,060/5,723 symbols with real
total_assets and stockholders_equity but NULL total_liabilities. Root cause,
live-confirmed via REX American Resources's real SEC companyfacts JSON (CIK
0000744187): REX has reported zero "Liabilities" XBRL facts since 2018 (only
tiny, clearly-unrelated values before that), while "Assets" and
"LiabilitiesAndStockholdersEquity" are both populated and identical every
period ($797,731,000 for FY2026) - the filer simply never tags total
liabilities directly. The balance-sheet identity Assets = Liabilities +
StockholdersEquity always holds, so total_liabilities is derivable, not
missing. This was surfacing downstream as "SEC data not available" for
Debt to Assets / Debt to Equity on the Scores page despite REX having real,
complete balance sheet data for both inputs.

ConsolidatedFinancialStatementsLoader.transform() now fills total_liabilities
= total_assets - stockholders_equity only when total_liabilities is NULL and
both inputs are present.
"""

from decimal import Decimal
from unittest.mock import patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


class TestTotalLiabilitiesDerivationFallback:
    def _make_loader(self) -> ConsolidatedFinancialStatementsLoader:
        return ConsolidatedFinancialStatementsLoader(statement_type="balance", period="annual")

    def test_derives_total_liabilities_when_missing(self):
        loader = self._make_loader()
        rows = [
            {
                "symbol": "REX",
                "fiscal_year": 2026,
                "total_assets": Decimal("797731000"),
                "stockholders_equity": Decimal("610712000"),
                "total_liabilities": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            result = loader.transform(rows)

        assert result[0]["total_liabilities"] == Decimal("187019000")

    def test_does_not_overwrite_real_total_liabilities(self):
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

        # A filer that DOES report Liabilities directly must keep that real value,
        # not have it silently recomputed.
        assert result[0]["total_liabilities"] == Decimal("400000000")

    def test_does_not_derive_for_income_statement_type(self):
        loader = ConsolidatedFinancialStatementsLoader(statement_type="income", period="annual")
        rows = [
            {
                "symbol": "REX",
                "fiscal_year": 2026,
                "revenue": Decimal("650487000"),
                "net_income": Decimal("82951000"),
                "total_assets": Decimal("797731000"),
                "stockholders_equity": Decimal("610712000"),
                "total_liabilities": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            result = loader.transform(rows)

        # total_liabilities isn't a real income-statement field; the balance-only
        # derivation must not fire outside statement_type == "balance".
        assert result[0]["total_liabilities"] is None

    def test_leaves_null_when_inputs_incomplete(self):
        loader = self._make_loader()
        rows = [
            {
                "symbol": "SPINOFFCO",
                "fiscal_year": 2026,
                "total_assets": Decimal("100000000"),
                "stockholders_equity": None,
                "total_liabilities": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            result = loader.transform(rows)

        assert result[0]["total_liabilities"] is None
