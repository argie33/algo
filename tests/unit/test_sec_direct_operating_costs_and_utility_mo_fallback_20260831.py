"""Regression test for the 2026-08-31 fix (goal session: "get all the data we need"
full-coverage audit, same sweep as test_sec_cost_of_goods_excluding_dda_fallback_20260831.py):
two more business-model-specific cost concepts that filers use INSTEAD of any previously
mapped COGS concept.

Live-confirmed via real SEC companyfacts JSON:
- Live Nation Entertainment (LYV, $23B market cap): zero data under any COGS concept
  above for any recent fiscal year, but real, current, plausible DirectOperatingCosts
  every year through FY2025 (FY2023 $17.29B/$22.75B revenue ~76%, FY2024 $17.33B/$23.16B
  ~75%).
- Regulated water utilities (AWK, WTRG, MSEX, YORW) tag
  UtilitiesOperatingExpenseMaintenanceAndOperations instead (AWK FY2023 $1.72B/$4.22B
  ~41%). CWT/SJW/ARTNA checked and confirmed to not use this concept - not fixed by this.

Both were previously mislabeled "reit_special_entity" (this codebase's generic "no cost
concept found" label - see load_value_quality_growth_metrics.py's no_gross_profit_concept)
despite real, current SEC data being on file. Fixed the same way as the DD&A-excluded
COGS concepts: fallback-only, since both are narrower, business-model-specific cost
measures rather than universal COGS tags.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING, _REVENUE_FALLBACK_ONLY_FIELDS


class TestDirectOperatingCostsAndUtilityMoConceptMapping:
    def test_both_variants_map_to_cost_of_revenue_and_are_fallback_only(self) -> None:
        for key in (
            "direct_operating_costs",
            "utilities_operating_expense_maintenance_and_operations",
        ):
            assert _INCOME_FIELD_MAPPING[key] == "cost_of_revenue"
            assert key in _REVENUE_FALLBACK_ONLY_FIELDS


class TestDirectOperatingCostsFallbackBehavior:
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
            "direct_operating_costs": "cost_of_revenue",
            "utilities_operating_expense_maintenance_and_operations": "cost_of_revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _REVENUE_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_lyv_style_filer_recovers_real_cost_of_revenue(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "LYV",
            "fiscal_year": 2023,
            "revenue": 22_749_073_000.0,
            "direct_operating_costs": 17_292_016_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 17_292_016_000.0

    def test_awk_style_filer_recovers_real_cost_of_revenue(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AWK",
            "fiscal_year": 2023,
            "revenue": 4_217_000_000.0,
            "utilities_operating_expense_maintenance_and_operations": 1_720_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 1_720_000_000.0

    def test_does_not_overwrite_a_real_full_cost_of_revenue(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMEFILER",
            "fiscal_year": 2025,
            "revenue": 100_000_000_000.0,
            "cost_of_revenue": 65_000_000_000.0,
            "direct_operating_costs": 50_000_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 65_000_000_000.0
