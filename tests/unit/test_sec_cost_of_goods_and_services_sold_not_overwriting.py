"""Regression test for the 2026-08-17 fix ("no SEC data" audit continuation): the
"cost_of_goods_and_services_sold" concept (added e1a3ae3b9 as a plain, always-overwrite
mapping so retail/product filers that never tag CostOfRevenue/CostOfSales - AMZN et al -
get a real cost_of_revenue) was NOT fallback-only, so on a filer that tags BOTH concepts
for unrelated line items it silently clobbered a correct value with a wrong one.

Live-confirmed via real SEC EDGAR companyfacts for CAT (Caterpillar): CostOfRevenue
FY2025=$44.75B (real, consolidated, ~65% of $67.6B revenue) vs.
CostOfGoodsAndServicesSold FY2025=$49M (some unrelated minor line item) -
annual_income_statement.cost_of_revenue was $49M, wrong by ~900x, with no
data_unavailable/reason flag anywhere. A DB-wide ratio scan found 32 symbols with this
same implausible-magnitude signature.

Fixed by moving "cost_of_goods_and_services_sold" into the existing
_REVENUE_FALLBACK_ONLY_FIELDS set (same "don't clobber a real value" mechanism already
used for sales_revenue_net/interest_income_operating - see
test_sec_sales_revenue_net_not_overwritten.py and
test_sec_debt_fallback_concepts_not_overwriting.py) so a filer that DOES report
CostOfRevenue/CostOfSales always keeps that value; this concept now only fills genuinely
empty years - preserving the original AMZN-style fix.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING, _REVENUE_FALLBACK_ONLY_FIELDS


class TestCostOfGoodsFallbackConceptMapping:
    def test_cost_of_goods_and_services_sold_maps_to_cost_of_revenue(self) -> None:
        assert _INCOME_FIELD_MAPPING["cost_of_goods_and_services_sold"] == "cost_of_revenue"
        assert "cost_of_goods_and_services_sold" in _REVENUE_FALLBACK_ONLY_FIELDS

    def test_standard_cost_of_revenue_concept_still_maps_directly(self) -> None:
        assert _INCOME_FIELD_MAPPING["cost_of_revenue"] == "cost_of_revenue"
        assert "cost_of_revenue" not in _REVENUE_FALLBACK_ONLY_FIELDS


class TestCostOfGoodsFallbackNotOverwritingRealCostOfRevenue:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "revenue", "cost_of_revenue", "net_income", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "revenue": "revenue",
            "cost_of_revenue": "cost_of_revenue",
            "cost_of_goods_and_services_sold": "cost_of_revenue",
            "net_income": "net_income",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _REVENUE_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_real_cost_of_revenue_not_overwritten_by_unrelated_cogs_concept(self) -> None:
        # CAT-style filer: reports both concepts, but CostOfGoodsAndServicesSold is a
        # small unrelated line item, not consolidated COGS.
        loader = self._make_loader()
        row = {
            "symbol": "CAT",
            "fiscal_year": 2025,
            "revenue": 67_600_000_000.0,
            "cost_of_revenue": 44_750_000_000.0,
            "cost_of_goods_and_services_sold": 49_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 44_750_000_000.0

    def test_fallback_concept_populates_cost_of_revenue_when_standard_concept_absent(self) -> None:
        # AMZN-style filer: never tags CostOfRevenue/CostOfSales at all, only
        # CostOfGoodsAndServicesSold - must still recover a real cost_of_revenue.
        loader = self._make_loader()
        row = {
            "symbol": "AMZN",
            "fiscal_year": 2025,
            "revenue": 716_924_000_000.0,
            "cost_of_goods_and_services_sold": 356_414_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 356_414_000_000.0
