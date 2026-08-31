"""Regression test for the 2026-08-31 fix (goal session: "get all the data we need"
full-coverage audit): industrial/materials filers that break out D&A as its own
income-statement line (rather than folding it into cost of sales) tag
CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization or
CostOfGoodsSoldExcludingDepreciationDepletionAndAmortization instead of any previously
mapped concept.

Live-confirmed via real SEC companyfacts JSON: Linde plc (LIN, $230B market cap) had
zero data under CostOfRevenue/CostOfSales/CostOfGoodsAndServicesSold for every fiscal
year, but a real, plausible cost figure (FY2025 $17.39B against $33.99B revenue, ~51%)
under CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization -
quality_metrics.gross_profitability/gross_margin had been silently NULL despite 40,000+
real income-statement data on file. Howmet Aerospace (HWM) and Cognizant (CTSH)
independently confirmed the same gap via the same concept.

Fixed the same way as cost_of_goods_and_services_sold above: fallback-only, since
excluding D&A makes this a narrower figure than a full COGS-including-D&A tag when a
filer reports both.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING, _REVENUE_FALLBACK_ONLY_FIELDS


class TestCostOfGoodsExcludingDdaConceptMapping:
    def test_both_variants_map_to_cost_of_revenue_and_are_fallback_only(self) -> None:
        for key in (
            "cost_of_goods_and_service_excluding_depreciation_depletion_and_amortization",
            "cost_of_goods_sold_excluding_depreciation_depletion_and_amortization",
        ):
            assert _INCOME_FIELD_MAPPING[key] == "cost_of_revenue"
            assert key in _REVENUE_FALLBACK_ONLY_FIELDS


class TestCostOfGoodsExcludingDdaFallbackBehavior:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "revenue", "cost_of_revenue", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "revenue": "revenue",
            "cost_of_revenue": "cost_of_revenue",
            "cost_of_goods_and_service_excluding_depreciation_depletion_and_amortization": "cost_of_revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _REVENUE_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_lin_style_filer_recovers_real_cost_of_revenue(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "LIN",
            "fiscal_year": 2025,
            "revenue": 33_986_000_000.0,
            "cost_of_goods_and_service_excluding_depreciation_depletion_and_amortization": 17_389_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 17_389_000_000.0

    def test_does_not_overwrite_a_real_full_cost_of_revenue(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMEFILER",
            "fiscal_year": 2025,
            "revenue": 100_000_000_000.0,
            "cost_of_revenue": 65_000_000_000.0,
            "cost_of_goods_and_service_excluding_depreciation_depletion_and_amortization": 50_000_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 65_000_000_000.0
