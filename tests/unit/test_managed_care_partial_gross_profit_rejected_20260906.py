"""Regression test for the 2026-09-06 fix (goal: "SEC/XBRL missing data to zero"/tie-out
sweep, gross_profit_identity follow-up to test_stale_gross_profit_force_nulled_20260906.py's
ABBV/GILD/AMGN/ABT fix).

Live-confirmed via real SEC companyfacts JSON: Centene (CNC) and Elevance Health (ELV) - both
managed-care health insurers, SIC "Hospital & Medical Service Plans" - tag their own
"GrossProfit"/"CostOfGoodsAndServicesSold" XBRL concepts to a narrow, real sub-calculation
(their non-premium service-fee segments only) that EXCLUDES their dominant cost line - medical
claims/benefits expense, tagged separately as PolicyholderBenefitsAndClaimsIncurredHealthCare/
BenefitsLossesAndExpenses, which this pipeline never maps to cost_of_revenue at all. CNC FY2025:
revenue=$174.581B, cost_of_revenue=$2.670B, gross_profit=$14.209B (both real, filer-reported
facts) vs the real dominant cost, PolicyholderBenefitsAndClaimsIncurredHealthCare, ~$118.9B
(FY2023) - not economically comparable to a retailer's gross margin.

Unlike the ABBV-shaped bug (no real value exists at all, a stale leftover), CNC's/ELV's figures
ARE real filer-reported facts - just not meaningful as "cost of revenue"/"gross profit" for a
managed-care insurer. Fixed via a curated, individually-verified symbol allowlist (not a SIC-
wide null, which would incorrectly also blank UNH/CI/CVS's real PBM/retail-pharmacy segment
cost data - live-confirmed those symbols' CostOfGoodsAndServicesSold figures ARE meaningful,
~50-55% of revenue, a real comparable ratio, and MOH/HUM correctly have no GrossProfit tag at
all already).
"""

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _transform(loader: ConsolidatedFinancialStatementsLoader, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
        return loader.transform(rows)


class TestManagedCarePartialGrossProfitRejected:
    def test_cnc_gross_profit_and_cost_of_revenue_rejected(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "CNC",
                "fiscal_year": 2025,
                "revenue": Decimal("174581000000"),
                "cost_of_revenue": Decimal("2670000000"),
                "gross_profit": Decimal("14209000000"),
                "net_income": Decimal("-1230000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["gross_profit"] is None
        assert result[0]["cost_of_revenue"] is None
        assert ({"symbol": "CNC", "fiscal_year": 2025}, "gross_profit") in loader._explicit_null_rejections
        assert ({"symbol": "CNC", "fiscal_year": 2025}, "cost_of_revenue") in loader._explicit_null_rejections

    def test_elv_gross_profit_and_cost_of_revenue_rejected(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "ELV",
                "fiscal_year": 2025,
                "revenue": Decimal("199125000000"),
                "cost_of_revenue": Decimal("21178000000"),
                "gross_profit": Decimal("30000000000"),
                "net_income": Decimal("6000000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["gross_profit"] is None
        assert result[0]["cost_of_revenue"] is None

    def test_unrelated_symbol_with_similar_shape_is_not_rejected(self) -> None:
        """Guards the curated-allowlist discipline: UNH's real, meaningful PBM-segment
        cost_of_revenue (a genuinely comparable ~50%+ of revenue ratio) must NOT be touched -
        only the two individually-verified symbols are affected."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "UNH",
                "fiscal_year": 2025,
                "revenue": Decimal("447567000000"),
                "cost_of_revenue": Decimal("50655000000"),
                "gross_profit": None,
                "net_income": Decimal("15000000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["cost_of_revenue"] == Decimal("50655000000")
        assert ({"symbol": "UNH", "fiscal_year": 2025}, "cost_of_revenue") not in loader._explicit_null_rejections

    def test_balance_sheet_statement_type_is_unaffected(self) -> None:
        """The curated symbols' balance-sheet rows (a different statement_type) have no
        gross_profit/cost_of_revenue columns at all - this check must be a no-op there."""
        loader = _make_loader(statement_type="balance")
        rows = [
            {
                "symbol": "CNC",
                "fiscal_year": 2025,
                "total_assets": Decimal("50000000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        _transform(loader, rows)
        assert loader._explicit_null_rejections == []
