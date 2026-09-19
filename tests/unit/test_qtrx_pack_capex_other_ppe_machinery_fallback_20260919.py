"""Regression test for the QTRX/PACK capex bug found live 2026-09-19 (/goal data-confidence
audit).

Both "PaymentsToAcquireOtherPropertyPlantAndEquipment" and
"PaymentsToAcquireMachineryAndEquipment" were plain always-overwrite mappings to "capex" -
added for filers (LLY/ADP, AAON respectively) that tag ONLY one of these narrower concepts,
never the standard "PaymentsToAcquirePropertyPlantAndEquipment". But QTRX and PACK each tag
BOTH the narrower concept AND the real, complete standard PP&E concept for the same fiscal
year - ordinary last-listed-wins let the narrower one unconditionally clobber the real total:

- QTRX FY2022-2025: stored value matched "PaymentsToAcquireOtherPropertyPlantAndEquipment"
  every year (e.g. FY2022 $152,000), real total under "PaymentsToAcquirePropertyPlantAnd
  Equipment" is $11,614,000 (exact yfinance match) - a ~76x understatement.
- PACK FY2023: stored value $23,900,000 matched the same "Other" concept; after making that
  one fallback-only, "PaymentsToAcquireMachineryAndEquipment" ($31,400,000) won instead -
  still wrong. Real total is $55,300,000 (exact yfinance match, "PaymentsToAcquireProperty
  PlantAndEquipment").
"""

from loaders.helpers.financial_statements_cashflow_config import (
    _CASHFLOW_FIELD_MAPPING,
    _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,
)
from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestCapexOtherPpeAndMachineryFallbackOnly:
    def test_concepts_map_to_capex_and_are_fallback_only(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["payments_to_acquire_other_property_plant_and_equipment"] == "capex"
        assert _CASHFLOW_FIELD_MAPPING["payments_to_acquire_machinery_and_equipment"] == "capex"
        assert "payments_to_acquire_other_property_plant_and_equipment" in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        assert "payments_to_acquire_machinery_and_equipment" in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "capex", "data_unavailable", "reason"})
        loader._field_mapping = {
            "payments_to_acquire_property_plant_and_equipment": "capex",
            "payments_to_acquire_other_property_plant_and_equipment": "capex",
            "payments_to_acquire_machinery_and_equipment": "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_real_ppe_total_not_overwritten_by_other_ppe(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "QTRX",
            "fiscal_year": 2022,
            "payments_to_acquire_property_plant_and_equipment": 11_614_000.0,
            "payments_to_acquire_other_property_plant_and_equipment": 152_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 11_614_000.0

    def test_real_ppe_total_not_overwritten_by_machinery_and_equipment(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "PACK",
            "fiscal_year": 2023,
            "payments_to_acquire_property_plant_and_equipment": 55_300_000.0,
            "payments_to_acquire_other_property_plant_and_equipment": 23_900_000.0,
            "payments_to_acquire_machinery_and_equipment": 31_400_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 55_300_000.0

    def test_machinery_and_equipment_still_fills_when_nothing_else_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAON",
            "fiscal_year": 2020,
            "payments_to_acquire_machinery_and_equipment": 5_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 5_000_000.0
