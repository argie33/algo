"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep, second
follow-up pass): 6 more genuine capex-equivalent concepts found by scanning EVERY numeric
fact in each filer's full companyfacts JSON for one that exactly matches
xbrl_yfinance_line_item_report's flagged capex value (not from a predefined candidate
list):

- FBIO/KIDZ/SCYX: "PaymentsToAcquireIntangibleAssets" ($15,000,000 / $1,250,000 / $1,172,000)
- KKR: "PaymentsToAcquireFurnitureAndFixtures" ($85,056,000)
- KOS (E&P): "PaymentsToAcquireOilAndGasEquipment" ($933,659,000)
- NLY (mortgage REIT): "PaymentsToAcquireMortgageServicingRightsMSR" ($396,806,000)
- DOCS/ROOT/STEM: "PaymentsToDevelopSoftware" ($8,901,000 / $14,100,000 / $6,602,000)
- TIL: "PaymentsToAcquireInProcessResearchAndDevelopment" ($10,000,000)

All fallback-only - must never win over a real value the standard PP&E-family capex
concepts already found.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING, _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

NEW_CONCEPTS = [
    "payments_to_acquire_intangible_assets",
    "payments_to_acquire_furniture_and_fixtures",
    "payments_to_acquire_oil_and_gas_equipment",
    "payments_to_acquire_mortgage_servicing_rights_msr",
    "payments_to_develop_software",
    "payments_to_acquire_in_process_research_and_development",
]


class TestSixCapexConceptsFullCompanyfactsScan:
    def _make_loader(self, sec_field: str) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "capex", "data_unavailable", "reason"})
        loader._field_mapping = {
            "payments_to_acquire_property_plant_and_equipment": "capex",
            sec_field: "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({sec_field})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mappings_and_fallback_only_wired(self) -> None:
        for sec_field in NEW_CONCEPTS:
            assert _CASHFLOW_FIELD_MAPPING[sec_field] == "capex"
            assert sec_field in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def test_each_concept_fills_empty_capex(self) -> None:
        for sec_field in NEW_CONCEPTS:
            loader = self._make_loader(sec_field)
            row = {"symbol": "TESTCO", "fiscal_year": 2025, sec_field: 12_345.0}

            transformed = loader.transform([row])

            assert transformed[0]["capex"] == 12_345.0, sec_field

    def test_each_concept_never_overwrites_a_real_capex_value(self) -> None:
        for sec_field in NEW_CONCEPTS:
            loader = self._make_loader(sec_field)
            row = {
                "symbol": "TESTCO",
                "fiscal_year": 2025,
                "payments_to_acquire_property_plant_and_equipment": 500_000_000.0,
                sec_field: 1.0,
            }

            transformed = loader.transform([row])

            assert transformed[0]["capex"] == 500_000_000.0, sec_field
