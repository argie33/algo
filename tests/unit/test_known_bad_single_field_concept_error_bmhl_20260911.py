"""Regression test for the 2026-09-11 BMHL cost_of_revenue fix (goal session: adversarial
scoring-validation - a "why is BMHL's revenue $6,910 but cost_of_revenue $4.1M" lead).

Live-confirmed via BMHL's (Bluemount Holdings Ltd) real SEC companyfacts JSON: its FY2023-2025
20-F/A (accession 0001171843-25-005486) tags cost_of_revenue from BOTH us-gaap:CostOfRevenue
(HKD 7,259,000/12,493,000/31,887,000) AND ifrs-full:CostOfSales (HKD 9,735/15,078/33,834, same
accn/filed/period) - a ~750-943x discrepancy. ifrs-full:CostOfSales is the real figure (ties out
exactly against revenue-minus-gross_profit); us-gaap:CostOfRevenue wins the shared
_aggregate_concepts engine's "first-populated-wins for cross-concept collisions" tiebreak purely
because us-gaap concepts are listed before ifrs aliases in _aggregate_concepts_build_specs,
regardless of which value is correct.

_reject_known_bad_single_field_concept_errors() nulls only the specific fields on a row matching
KNOWN_BAD_SINGLE_FIELD_CONCEPT_ERRORS - unlike KNOWN_BAD_FILING_SCALE_ERRORS's whole-row
rejection, revenue/gross_profit/net_income (independently confirmed correct) must survive
untouched.
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


class TestKnownBadSingleFieldConceptErrorRejected:
    def test_bmhl_cost_of_revenue_nulled_other_fields_untouched(self) -> None:
        loader = _make_loader(statement_type="income")
        rows = [
            {
                "symbol": "BMHL",
                "fiscal_year": 2025,
                "revenue": Decimal("6910.53"),
                "cost_of_revenue": Decimal("4099113.00"),
                "gross_profit": Decimal("2561.13"),
                "net_income": Decimal("1296.57"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        row = transformed[0]
        assert row["cost_of_revenue"] is None
        assert row["revenue"] == Decimal("6910.53")
        assert row["gross_profit"] == Decimal("2561.13")
        assert row["net_income"] == Decimal("1296.57")
        rejected_fields = {field for _, field in loader._explicit_null_rejections}
        assert rejected_fields == {"cost_of_revenue"}

    def test_bmhl_all_three_affected_fiscal_years_rejected(self) -> None:
        loader = _make_loader(statement_type="income")
        rows = [
            {"symbol": "BMHL", "fiscal_year": 2023, "cost_of_revenue": Decimal("924736.94")},
            {"symbol": "BMHL", "fiscal_year": 2024, "cost_of_revenue": Decimal("1596590.33")},
            {"symbol": "BMHL", "fiscal_year": 2025, "cost_of_revenue": Decimal("4099113.00")},
        ]
        transformed = _transform(loader, rows)
        assert all(row["cost_of_revenue"] is None for row in transformed)

    def test_bmhl_unaffected_fiscal_year_untouched(self) -> None:
        loader = _make_loader(statement_type="income")
        rows = [{"symbol": "BMHL", "fiscal_year": 2022, "cost_of_revenue": Decimal("500000.00")}]
        transformed = _transform(loader, rows)
        assert transformed[0]["cost_of_revenue"] == Decimal("500000.00")
        assert loader._explicit_null_rejections == []

    def test_unrelated_symbol_untouched(self) -> None:
        loader = _make_loader(statement_type="income")
        rows = [{"symbol": "AAPL", "fiscal_year": 2025, "cost_of_revenue": Decimal("200000000000")}]
        transformed = _transform(loader, rows)
        assert transformed[0]["cost_of_revenue"] == Decimal("200000000000")
        assert loader._explicit_null_rejections == []
