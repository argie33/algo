"""Regression test for the 2026-09-07 fix (goal session: "make sure the list/checks are
right, then fix issues" audit): plain "CostOfGoodsSold" - the older, pre-2009-taxonomy
singular-concept COGS tag - was never fetched at all.

Live-confirmed via real SEC EDGAR companyfacts cache: 47 real filers (Halliburton, Thermo
Fisher Scientific, NCR Voyix among them) tag ONLY this concept, with NONE of the
CostOfRevenue/CostOfSales/CostOfGoodsAndServicesSold/*ExcludingDepreciation family present at
all - cost_of_revenue/gross_profit/gross_margin were silently NULL for these filers' entire
history.

Added as a fallback-only concept/field mapping (same "fills only an already-empty db_field"
mechanism as cost_of_goods_and_services_sold and the *ExcludingDepreciation variants) so a
filer that DOES report a standard cost-of-revenue concept keeps that value.
"""

from loaders.load_financial_statements import _INCOME_FIELD_MAPPING, _REVENUE_FALLBACK_ONLY_FIELDS


class TestCostOfGoodsSoldFallbackConceptMapping:
    def test_maps_to_cost_of_revenue(self) -> None:
        assert _INCOME_FIELD_MAPPING["cost_of_goods_sold"] == "cost_of_revenue"

    def test_is_fallback_only(self) -> None:
        assert "cost_of_goods_sold" in _REVENUE_FALLBACK_ONLY_FIELDS
