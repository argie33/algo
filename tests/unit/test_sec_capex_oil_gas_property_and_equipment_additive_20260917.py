"""Regression test (2026-09-17, xbrl_yfinance_line_item_report capex cluster follow-up).
Live-confirmed via SM (SM Energy, CIK 0000893538) FY2022: real SEC companyfacts JSON tags
"PaymentsToExploreAndDevelopOilAndGasProperties" ($879,934,000) AND
"PaymentsToAcquireOilAndGasPropertyAndEquipment" ($7,000) in the same fiscal year as
genuinely distinct, additive investing-activity cash outflows - not alternates. Both map to
db_field "capex" via field_mapping.

Before this fix, ADDITIVE_CONCEPT_PAIRS only listed the sibling concept
"payments_to_acquire_oil_and_gas_property" (no "_and_equipment" suffix, see
test_sec_capex_oil_gas_dual_concept_sum_20260907.py) - this "_and_equipment" variant fell
through to the ordinary last-listed-concept-wins rule and unconditionally overwrote the
already-resolved $879,934,000 with its own real-but-immaterial $7,000, understating capex by
~99.999% (stored value exactly matched our_value in xbrl_yfinance_line_item_report: 7000 vs.
yfinance's flagged 879941000 = 879934000 + 7000, an exact match once summed).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestCapexOilGasPropertyAndEquipmentAdditive:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cash_flow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "capex", "data_unavailable", "reason"})
        loader._field_mapping = {
            "payments_to_explore_and_develop_oil_and_gas_properties": "capex",
            "payments_to_acquire_oil_and_gas_property_and_equipment": "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_explore_develop_and_property_equipment_sum_instead_of_overwrite(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SM",
            "fiscal_year": 2022,
            "payments_to_explore_and_develop_oil_and_gas_properties": 879_934_000.0,
            "_rank_payments_to_explore_and_develop_oil_and_gas_properties": 2,
            "payments_to_acquire_oil_and_gas_property_and_equipment": 7_000.0,
            "_rank_payments_to_acquire_oil_and_gas_property_and_equipment": 2,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 879_934_000.0 + 7_000.0

    def test_order_independence_sum_regardless_of_dict_insertion_order(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SM",
            "fiscal_year": 2022,
            "payments_to_acquire_oil_and_gas_property_and_equipment": 7_000.0,
            "_rank_payments_to_acquire_oil_and_gas_property_and_equipment": 2,
            "payments_to_explore_and_develop_oil_and_gas_properties": 879_934_000.0,
            "_rank_payments_to_explore_and_develop_oil_and_gas_properties": 2,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 879_934_000.0 + 7_000.0

    def test_single_concept_only_unaffected(self) -> None:
        """A filer tagging only the "_and_equipment" concept must get that value as-is, not
        summed against anything."""
        loader = self._make_loader()
        row = {
            "symbol": "SOLO2",
            "fiscal_year": 2025,
            "payments_to_acquire_oil_and_gas_property_and_equipment": 500_000_000.0,
            "_rank_payments_to_acquire_oil_and_gas_property_and_equipment": 2,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 500_000_000.0
