"""Regression test for the 2026-09-07 fix: stock_based_compensation/common_stock_repurchased
have the exact same debit-balance XBRL sign-flip bug already fixed for dividends_paid
(2026-08-18, see load_financial_statements.py's DividendsCommonStockCash comment), just never
extended to them.

Live-confirmed via real SEC companyfacts JSON:
- AAMI (CIK 0001748824, accn 0001628280-26-012856): AllocatedShareBasedCompensationExpense
  tagged -$23,200,000 (FY2024) / -$47,700,000 (FY2025) - a real non-cash compensation addback
  reported negative by the filer.
- JCTC (CIK 0000885307, accn 0001217160-12-000393 / 0001217160-13-000312):
  PaymentsForRepurchaseOfCommonStock tagged -$3,075,559 (FY2012) / -$7,188 (FY2013).

Both fields are always cash-flow-statement magnitudes (a non-cash addback and a cash outflow,
respectively) - a live DB scan found 264+1,370 (annual+quarterly) negative
stock_based_compensation rows and 99+477 negative common_stock_repurchased rows before this
fix, all real filer-tagged negatives of this same shape.
"""

from decimal import Decimal
from typing import Any
from unittest.mock import patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type="cashflow", period=period)


def _transform(loader: ConsolidatedFinancialStatementsLoader, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
        return loader.transform(rows)


class TestStockBasedCompensationSignFlip:
    def test_negative_stock_based_compensation_normalized_to_positive(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "AAMI",
                "fiscal_year": 2025,
                "operating_cash_flow": Decimal("100000000"),
                "stock_based_compensation": Decimal("-47700000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        assert transformed[0]["stock_based_compensation"] == Decimal("47700000")

    def test_already_positive_stock_based_compensation_unchanged(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2025,
                "operating_cash_flow": Decimal("100000000000"),
                "stock_based_compensation": Decimal("11000000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        assert transformed[0]["stock_based_compensation"] == Decimal("11000000000")

    def test_none_stock_based_compensation_left_none(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "PJT",
                "fiscal_year": 2025,
                "operating_cash_flow": Decimal("50000000"),
                "stock_based_compensation": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        assert transformed[0]["stock_based_compensation"] is None


class TestCommonStockRepurchasedSignFlip:
    def test_negative_common_stock_repurchased_normalized_to_positive(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "JCTC",
                "fiscal_year": 2013,
                "operating_cash_flow": Decimal("5000000"),
                "common_stock_repurchased": Decimal("-7188"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        assert transformed[0]["common_stock_repurchased"] == Decimal("7188")

    def test_quarterly_negative_common_stock_repurchased_normalized(self) -> None:
        loader = _make_loader(period="quarterly")
        rows = [
            {
                "symbol": "JCTC",
                "fiscal_year": 2013,
                "fiscal_quarter": 4,
                "operating_cash_flow": Decimal("1000000"),
                "common_stock_repurchased": Decimal("-7188"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        assert transformed[0]["common_stock_repurchased"] == Decimal("7188")

    def test_income_statement_type_not_affected(self) -> None:
        """Sanity: the sign-flip normalization is scoped to statement_type == 'cashflow' only
        (mirrors the existing dividends_paid normalization's own scoping) - an income-statement
        loader instance should never touch these fields even if present in a stray row."""
        loader = ConsolidatedFinancialStatementsLoader(statement_type="income", period="annual")
        rows = [
            {
                "symbol": "XYZ",
                "fiscal_year": 2025,
                "revenue": Decimal("1000000"),
                "net_income": Decimal("100000"),
                "stock_based_compensation": Decimal("-5000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        assert transformed[0]["stock_based_compensation"] == Decimal("-5000")
