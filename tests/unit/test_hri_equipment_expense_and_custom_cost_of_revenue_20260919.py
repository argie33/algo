"""Regression tests for the 2026-09-19 HRI (Herc Holdings) cost_of_revenue fix.

HRI splits its cost of revenue across four separate income-statement line items:
"Direct operating" (DirectOperatingCosts, already fetched pre-fix) + "Depreciation of
rental equipment" (EquipmentExpense, a standard us-gaap concept, merged additively via
_fill_cost_of_revenue_from_equipment_expense_component) + two more tagged under
filer-specific custom XBRL extension concepts, invisible to companyfacts (same
structural gap CUSTOM_CAPEX_CONCEPTS' module docstring documents for DHT/CMRE):
hri:CostOfRevenueEarningEquipmentSold ("Cost of sales of rental equipment") and
hri:CostOfSalesOfNewEquipmentPartsAndSupplies ("Cost of sales of new equipment, parts
and supplies").

Fixture values (FY2023/2024/2025) match the real filed XBRL instance document, verified
live 2026-09-19 (accession 0001364479-26-000050).
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_income_statement_config
from utils.external.sec_custom_xbrl_concepts import (
    CUSTOM_COST_OF_REVENUE_CONCEPTS,
    extract_custom_cost_of_revenue_from_xbrl_xml,
)
from utils.external.sec_income_statement_fallbacks import _fill_cost_of_revenue_from_equipment_expense_component

_HRI_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:hri="http://hercrentals.com/20251231">
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001364479</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c-18">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001364479</identifier></entity>
    <period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period>
  </context>
  <context id="c-19">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001364479</identifier></entity>
    <period><startDate>2023-01-01</startDate><endDate>2023-12-31</endDate></period>
  </context>
  <hri:CostOfRevenueEarningEquipmentSold contextRef="c-1" unitRef="usd" decimals="-6">418000000</hri:CostOfRevenueEarningEquipmentSold>
  <hri:CostOfRevenueEarningEquipmentSold contextRef="c-18" unitRef="usd" decimals="-6">224000000</hri:CostOfRevenueEarningEquipmentSold>
  <hri:CostOfRevenueEarningEquipmentSold contextRef="c-19" unitRef="usd" decimals="-6">252000000</hri:CostOfRevenueEarningEquipmentSold>
  <hri:CostOfSalesOfNewEquipmentPartsAndSupplies contextRef="c-1" unitRef="usd" decimals="-6">42000000</hri:CostOfSalesOfNewEquipmentPartsAndSupplies>
  <hri:CostOfSalesOfNewEquipmentPartsAndSupplies contextRef="c-18" unitRef="usd" decimals="-6">24000000</hri:CostOfSalesOfNewEquipmentPartsAndSupplies>
  <hri:CostOfSalesOfNewEquipmentPartsAndSupplies contextRef="c-19" unitRef="usd" decimals="-6">25000000</hri:CostOfSalesOfNewEquipmentPartsAndSupplies>
</xbrl>
"""


class TestExtractCustomCostOfRevenueFromXbrlXml:
    def test_extracts_all_three_fiscal_years(self):
        values = extract_custom_cost_of_revenue_from_xbrl_xml(_HRI_XML, "HRI")
        assert values == {2025: 460_000_000.0, 2024: 248_000_000.0, 2023: 277_000_000.0}

    def test_unregistered_symbol_returns_empty(self):
        assert extract_custom_cost_of_revenue_from_xbrl_xml(_HRI_XML, "AAPL") == {}


class TestHriRegisteredInCustomCostOfRevenueConcepts:
    def test_hri_registered(self):
        assert "HRI" in CUSTOM_COST_OF_REVENUE_CONCEPTS


class TestFillCostOfRevenueFromEquipmentExpenseComponent:
    """Pre-transform raw-key merge: direct_operating_costs += equipment_expense, gated on
    both being present so a filer without EquipmentExpense (the vast majority) is unaffected.
    """

    def test_merges_equipment_expense_into_direct_operating_costs(self):
        rows = [
            {
                "symbol": "HRI",
                "fiscal_year": 2025,
                "direct_operating_costs": 1_602_000_000,
                "equipment_expense": 856_000_000,
            }
        ]
        _fill_cost_of_revenue_from_equipment_expense_component(rows)
        assert rows[0]["direct_operating_costs"] == 1_602_000_000 + 856_000_000
        assert "equipment_expense" not in rows[0]

    def test_no_direct_operating_costs_leaves_equipment_expense_unused(self):
        rows = [{"symbol": "AAPL", "fiscal_year": 2025, "equipment_expense": 5_000_000}]
        _fill_cost_of_revenue_from_equipment_expense_component(rows)
        assert "direct_operating_costs" not in rows[0]

    def test_no_equipment_expense_leaves_direct_operating_costs_unchanged(self):
        rows = [{"symbol": "LYV", "fiscal_year": 2025, "direct_operating_costs": 17_290_000_000}]
        _fill_cost_of_revenue_from_equipment_expense_component(rows)
        assert rows[0]["direct_operating_costs"] == 17_290_000_000


def _make_income_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_income_statement_config("annual")
    loader.table_name = config["table_name"]
    loader.period = "annual"
    loader.statement_type = "income"
    loader.is_symbol_based = True
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    loader._fallback_only_fields = config["fallback_only_fields"]
    loader._sec_client = MagicMock()
    loader._sec_client.symbol_to_cik.return_value = "0001364479"
    return loader


class TestApplyCustomIncomeExtensionsStagesCostOfRevenueKey:
    def test_custom_cost_of_revenue_staged_for_matching_fiscal_years(self):
        loader = _make_income_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[
                    {
                        "symbol": "HRI",
                        "fiscal_year": 2025,
                        "fiscal_period": "FY",
                        "direct_operating_costs": 2_458_000_000,
                    },
                ],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_cost_of_revenue",
                return_value={2025: 460_000_000.0},
            ) as mock_fetch,
        ):
            rows = loader.fetch_incremental("HRI", since=None)

        mock_fetch.assert_called_once_with("HRI", loader._sec_client)
        assert rows[0]["custom_extension_cost_of_revenue_additive"] == 460_000_000.0

    def test_unregistered_symbol_never_calls_fetch_custom_cost_of_revenue(self):
        loader = _make_income_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "AAPL", "fiscal_year": 2025, "fiscal_period": "FY", "revenue": 1}],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_cost_of_revenue"
            ) as mock_fetch,
        ):
            loader.fetch_incremental("AAPL", since=None)

        mock_fetch.assert_not_called()


class TestTransformSumsCustomCostOfRevenueIntoCostOfRevenue:
    """End-to-end through the real SecEdgarStatementLoader.transform() (sec_base.py) -
    exercises the actual ADDITIVE_CONCEPT_PAIRS/is_fallback_only_write_permitted_by_
    documented_override wiring, not just apply_custom_income_extensions() in isolation.
    """

    def test_real_transform_sums_direct_operating_and_custom_cost_of_revenue(self):
        loader = _make_income_loader()
        raw_rows = [
            {
                "symbol": "HRI",
                "fiscal_year": 2025,
                "fiscal_period": "FY",
                "direct_operating_costs": 2_458_000_000,
                "custom_extension_cost_of_revenue_additive": 460_000_000.0,
            }
        ]
        transformed = loader.transform(raw_rows)
        assert transformed[0]["cost_of_revenue"] == 2_458_000_000 + 460_000_000.0

    def test_real_transform_never_overwrites_when_custom_value_absent(self):
        loader = _make_income_loader()
        raw_rows = [
            {"symbol": "LYV", "fiscal_year": 2025, "fiscal_period": "FY", "direct_operating_costs": 17_330_000_000}
        ]
        transformed = loader.transform(raw_rows)
        assert transformed[0]["cost_of_revenue"] == 17_330_000_000
