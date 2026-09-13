"""Regression test for the 2026-09-13 widening of _reject_scale_mismatched_net_income()
(loaders/helpers/financial_statements_value_validation.py) - goal session: quarterly-
revenue-identity backlog implausibility scan.

The original guard only checked net_income*scale ~= pretax_income - income_tax_expense (the
"reported in thousands/millions, needs multiplying up" direction). Live-confirmed via INVE's
real SEC companyfacts JSON that the MIRROR-IMAGE error also occurs: FY2021 NetIncomeLoss is
tagged $1,620,000,000,000, while the SAME row's own sibling ProfitLoss concept (a real,
correctly-scaled fact for the identical period) is $1,620,000 - exactly 1,000,000x SMALLER,
not larger. pretax_income($1,648,000) - income_tax_expense($28,000) = $1,620,000 confirms
ProfitLoss is the real figure and NetIncomeLoss is over-scaled by exactly 1,000,000x - a
direction this guard never checked, so a fresh production reload today still stores the
$1.62 trillion figure untouched.

Fix: check net_income/scale in addition to net_income*scale - a symmetric extension of the
same "unmistakably the same multiplicative family" logic already used here.
"""

from decimal import Decimal
from typing import Any
from unittest.mock import patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _transform(loader: ConsolidatedFinancialStatementsLoader, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
        return loader.transform(rows)


class TestNetIncomeScaleMismatchReverseDirection:
    def test_inve_shaped_million_x_too_large_net_income_rejected(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "INVE",
                "fiscal_year": 2021,
                "net_income": Decimal("1620000000000"),
                "pretax_income": Decimal("1648000"),
                "income_tax_expense": Decimal("28000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["net_income"] is None
        assert ({"symbol": "INVE", "fiscal_year": 2021}, "net_income") in loader._explicit_null_rejections

    def test_original_too_small_direction_still_rejected(self) -> None:
        """Guard against regressing the original, already-shipped direction (MVBF-shaped:
        net_income reported 1,000x too small)."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "MVBF",
                "fiscal_year": 2020,
                "net_income": Decimal("26922"),
                "pretax_income": Decimal("36850000"),
                "income_tax_expense": Decimal("9928000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["net_income"] is None
        assert ({"symbol": "MVBF", "fiscal_year": 2020}, "net_income") in loader._explicit_null_rejections

    def test_genuine_net_income_not_falsely_flagged(self) -> None:
        """A real, correctly-scaled net_income that merely differs from pretax-tax by normal
        NCI/discontinued-ops noise (well outside any power-of-10 ratio) must survive."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "REAL",
                "fiscal_year": 2024,
                "net_income": Decimal("95000000"),
                "pretax_income": Decimal("120000000"),
                "income_tax_expense": Decimal("25000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["net_income"] == Decimal("95000000")
