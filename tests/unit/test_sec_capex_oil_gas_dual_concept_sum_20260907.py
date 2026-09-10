"""Regression test (2026-09-07, real-money-readiness audit). Live-confirmed via Crescent
Energy (CRGY) FY2025: an E&P filer can tag BOTH "PaymentsToExploreAndDevelopOilAndGasProperties"
($951.0M, exploration & development spend) AND "PaymentsToAcquireOilAndGasProperty" ($818.9M,
acreage/property acquisition) in the SAME fiscal year as genuinely distinct, additive
investing-activity cash outflows - not alternates for the same fact. Both map to db_field
"capex" via field_mapping. sec_base.py's ordinary last-listed-concept-wins rule silently
discarded whichever one was processed first, understating total capex by the other line's
full amount (and correspondingly overstating free_cash_flow/fcf_margin, since FCF is derived
as operating_cash_flow - capex).

Fixed: transform() now sums these two specific concepts into capex instead of overwriting.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestCapexOilGasDualConceptSum:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cash_flow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "capex", "data_unavailable", "reason"})
        loader._field_mapping = {
            "payments_to_explore_and_develop_oil_and_gas_properties": "capex",
            "payments_to_acquire_oil_and_gas_property": "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_both_oil_gas_capex_concepts_sum_instead_of_overwrite(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "CRGY",
            "fiscal_year": 2025,
            "payments_to_explore_and_develop_oil_and_gas_properties": 951_000_000.0,
            "_rank_payments_to_explore_and_develop_oil_and_gas_properties": 2,
            "payments_to_acquire_oil_and_gas_property": 818_900_000.0,
            "_rank_payments_to_acquire_oil_and_gas_property": 2,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 951_000_000.0 + 818_900_000.0

    def test_order_independence_sum_regardless_of_dict_insertion_order(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "CRGY",
            "fiscal_year": 2025,
            "payments_to_acquire_oil_and_gas_property": 818_900_000.0,
            "_rank_payments_to_acquire_oil_and_gas_property": 2,
            "payments_to_explore_and_develop_oil_and_gas_properties": 951_000_000.0,
            "_rank_payments_to_explore_and_develop_oil_and_gas_properties": 2,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 951_000_000.0 + 818_900_000.0

    def test_single_concept_only_unaffected(self) -> None:
        """A filer tagging only ONE of the two concepts must get that value as-is, not
        summed against anything."""
        loader = self._make_loader()
        row = {
            "symbol": "SOLO",
            "fiscal_year": 2025,
            "payments_to_acquire_oil_and_gas_property": 500_000_000.0,
            "_rank_payments_to_acquire_oil_and_gas_property": 2,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 500_000_000.0
