"""Regression test for the 2026-09-07 fix (goal: stock_scores factor/composite sanity audit +
tie-out CI sweep, gross_profit_identity live re-check).

Live-confirmed via real SEC companyfacts JSON: Altria (MO) is the mirror image of
test_managed_care_partial_gross_profit_rejected_20260906.py's CNC/ELV bug. Here `GrossProfit`
is the real, complete, filer-tagged total, but `CostOfGoodsAndServicesSold` is the PARTIAL
concept - every fiscal year 2016-2025, Revenue - COGS != GrossProfit by a large, growing
margin (FY2025: $23.279B - $5.597B = $17.682B implied vs. the real, filer-tagged GrossProfit
of only $14.542B - a $3.14B gap, this pipeline's own gross_profit_identity tie-out check's
residual). Peer-checked Philip Morris International (PM) for the same FY2025 period and it
reconciles EXACTLY ($40.648B - $13.366B = $27.282B, to the dollar) - ruling out an industry-
wide excise-tax-exclusion accounting convention as the explanation; this is Altria-specific.

Extended 2026-09-07 (same goal session continuation, gross_profit_identity's batch 21-45
triage) with ZIM (ZIM Integrated Shipping, an IFRS 20-F container-shipping line): ifrs-full
"CostOfSales" ($4.4608B FY2025) is similarly partial - Revenue ($6.9042B) - CostOfSales implies
a 35.4% gross margin vs. the real, filer-tagged GrossProfit's 19.1% ($1.3209B) - no single
missing concept closes the $1.1225B gap exactly (ruled out the TTEK/TAP clean-sum pattern via
an exhaustive concept scan), and GrossProfit's plausibility is corroborated by
GrossProfit - ProfitLossFromOperatingActivities = a normal $304.9M SG&A-scale residual.
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


class TestAltriaPartialCostOfRevenueRejected:
    def test_mo_cost_of_revenue_rejected_gross_profit_kept(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "MO",
                "fiscal_year": 2025,
                "revenue": Decimal("23279000000"),
                "cost_of_revenue": Decimal("5597000000"),
                "gross_profit": Decimal("14542000000"),
                "net_income": Decimal("6947000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["cost_of_revenue"] is None
        # Unlike CNC/ELV, gross_profit is the RELIABLE figure here and must be kept.
        assert result[0]["gross_profit"] == Decimal("14542000000")
        assert ({"symbol": "MO", "fiscal_year": 2025}, "cost_of_revenue") in loader._explicit_null_rejections
        assert ({"symbol": "MO", "fiscal_year": 2025}, "gross_profit") not in loader._explicit_null_rejections

    def test_zim_cost_of_revenue_rejected_gross_profit_kept(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "ZIM",
                "fiscal_year": 2025,
                "revenue": Decimal("6904200000"),
                "cost_of_revenue": Decimal("4460800000"),
                "gross_profit": Decimal("1320900000"),
                "net_income": Decimal("481500000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["cost_of_revenue"] is None
        assert result[0]["gross_profit"] == Decimal("1320900000")
        assert ({"symbol": "ZIM", "fiscal_year": 2025}, "cost_of_revenue") in loader._explicit_null_rejections

    def test_unrelated_symbol_with_similar_shape_is_not_rejected(self) -> None:
        """Peer-verified: Philip Morris International's own concepts reconcile exactly for
        the same fiscal year - the curated allowlist must not touch it."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "PM",
                "fiscal_year": 2025,
                "revenue": Decimal("40648000000"),
                "cost_of_revenue": Decimal("13366000000"),
                "gross_profit": Decimal("27282000000"),
                "net_income": Decimal("10000000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["cost_of_revenue"] == Decimal("13366000000")
        assert ({"symbol": "PM", "fiscal_year": 2025}, "cost_of_revenue") not in loader._explicit_null_rejections

    def test_balance_sheet_statement_type_is_unaffected(self) -> None:
        loader = _make_loader(statement_type="balance")
        rows = [
            {
                "symbol": "MO",
                "fiscal_year": 2025,
                "total_assets": Decimal("30000000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        _transform(loader, rows)
        assert loader._explicit_null_rejections == []

    def test_mo_with_no_cost_of_revenue_is_a_no_op(self) -> None:
        """A row that already has no cost_of_revenue (already-rejected or genuinely missing)
        must not spuriously appear in the rejection log."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "MO",
                "fiscal_year": 2024,
                "revenue": Decimal("24018000000"),
                "cost_of_revenue": None,
                "gross_profit": Decimal("14367000000"),
                "net_income": Decimal("6000000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["cost_of_revenue"] is None
        assert ({"symbol": "MO", "fiscal_year": 2024}, "cost_of_revenue") not in loader._explicit_null_rejections
