"""Regression test for the 2026-09-17 divergence-repair trend-break sweep: mining and oil &
gas filers tag their real primary net property asset under sector-specific concepts, genuinely
ADDITIVE to (not an alternate for) a small remaining corporate "PropertyPlantAndEquipmentNet"
balance. Found via a broadened trend-break classifier: 1,401 unreviewed ppe_net divergent
rows, median ratio ~0.28-0.30 vs. yfinance across the whole set.

Live-confirmed via real SEC companyfacts JSON:
- THM (International Tower Hill Mines, CIK 0001134115) FY2025: "MineralPropertiesNet"
  $55,375,124 + "PropertyPlantAndEquipmentNet" $7,465 = $55,382,589 - an EXACT match to the
  yfinance-flagged value ($55,382,589), proving these are genuinely additive (mineral rights
  vs. corporate office equipment), not alternates for the same fact.
- PZG (Paramount Gold Nevada, CIK 0001629210): same pattern.
- RRC (Range Resources, CIK 0000315852) FY2025: "OilAndGasPropertySuccessfulEffortMethodNet"
  $6,708,366,000 + "PropertyPlantAndEquipmentNet" $4,935,000 = $6,713,301,000, same ballpark
  as yfinance's $6,886,743,000 (small residual gap plausibly right-of-use/other assets).
- HPK (HighPeak Energy, CIK 0001792849): same pattern.

Initially wired as fallback-only, which was WRONG - see sec_zero_component_guards.py's
ADDITIVE_CONCEPT_PAIRS comment for why (the plain concept legitimately has real, if small,
data for these filers, so fallback-only's "only fill if the standard concept found nothing"
semantics let the standard concept silently overwrite the larger sector value on later
processing - live-confirmed via a reload producing zero DB change for THM/PZG/RRC/HPK).
Corrected to the additive-sum mechanism (same as the existing O&G capex / TITN
interest_expense precedent) same session before landing.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING


class TestPpeNetMiningOilGasSiblingConcepts:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "ppe_net", "data_unavailable", "reason"})
        loader._field_mapping = {
            "property_plant_and_equipment_net": "ppe_net",
            "mineral_properties_net": "ppe_net",
            "oil_and_gas_property_successful_effort_method_net": "ppe_net",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wired(self) -> None:
        assert _BALANCE_FIELD_MAPPING["mineral_properties_net"] == "ppe_net"
        assert _BALANCE_FIELD_MAPPING["oil_and_gas_property_successful_effort_method_net"] == "ppe_net"

    def test_thm_style_mineral_properties_summed_not_overwritten(self) -> None:
        loader = self._make_loader()
        # Dict-insertion order matches the concept-list order (mineral_properties_net listed
        # before the plain concept): mineral_properties_net processed first, then
        # property_plant_and_equipment_net triggers the sum rather than overwriting it.
        row = {
            "symbol": "THM",
            "fiscal_year": 2025,
            "mineral_properties_net": 55_375_124.0,
            "property_plant_and_equipment_net": 7_465.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["ppe_net"] == 55_382_589.0

    def test_rrc_style_oil_and_gas_property_summed_not_overwritten(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "RRC",
            "fiscal_year": 2025,
            "oil_and_gas_property_successful_effort_method_net": 6_708_366_000.0,
            "property_plant_and_equipment_net": 4_935_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["ppe_net"] == 6_713_301_000.0

    def test_solo_mineral_properties_still_fills_empty_field(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "SOMECORP", "fiscal_year": 2025, "mineral_properties_net": 5_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["ppe_net"] == 5_000.0
