"""Regression test for the 2026-08-29 fix (goal: "full data" audit continuation): oil & gas
exploration & production filers (SIC 1311 "Crude Petroleum & Natural Gas" and related codes)
never tag any of the PP&E-family capex concepts - their capex is tagged under sector-specific
concept families the loader wasn't checking, leaving capex/free_cash_flow/fcf_yield NULL for
a live-confirmed 43 SIC-1311 symbols in the active scoring universe.

Live-confirmed via real companyfacts JSON: APA (Apache/APA Corp) $2.740B FY2025, AR (Antero
Resources) $685.5M FY2025, CHRD (Chord Energy) $1.348B FY2025, CRGY (Crescent Energy) $951.0M
FY2025, AMPY (Amplify Energy) $84.3M FY2025 all tag
"PaymentsToExploreAndDevelopOilAndGasProperties". EGY (small-cap) reports only
"PaymentsToAcquireOilAndGasProperty" $103.0M FY2024. DVN (Devon Energy) reports neither
"Payments"-prefixed concept for any recent fiscal year - its only current capex-equivalent
figure is "CostsIncurredOilAndGasPropertyAcquisitionExplorationAndDevelopmentActivities"
$4.000B FY2025 (the standard ASC 932 "costs incurred" supplemental disclosure, an
accrual-basis proxy used as a last resort, listed first/least-preferred so the more precise
"Payments"-based concepts win whenever a filer reports both).
"""

import inspect
from typing import Any

from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING
from utils.external import sec_statements
from utils.external.sec_statements import _to_snake, get_cash_flow


class TestOilGasCapexConceptsFixed:
    def test_payments_to_explore_and_develop_oil_and_gas_properties_maps_to_capex(self):
        target_key = _to_snake("PaymentsToExploreAndDevelopOilAndGasProperties")
        assert target_key == "payments_to_explore_and_develop_oil_and_gas_properties"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_payments_to_acquire_oil_and_gas_property_maps_to_capex(self):
        target_key = _to_snake("PaymentsToAcquireOilAndGasProperty")
        assert target_key == "payments_to_acquire_oil_and_gas_property"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_costs_incurred_oil_and_gas_property_activities_maps_to_capex(self):
        target_key = _to_snake("CostsIncurredOilAndGasPropertyAcquisitionExplorationAndDevelopmentActivities")
        assert target_key == "costs_incurred_oil_and_gas_property_acquisition_exploration_and_development_activities"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_oil_gas_capex_concepts_are_fetched(self):
        # A field_mapping entry alone is not enough - get_cash_flow()'s concept list must
        # actually request the concept from SEC or the mapping never fires (the "mapped but
        # unfetched" bug class test_financial_statements_field_mapping_completeness.py
        # guards more generally).
        source = inspect.getsource(sec_statements.get_cash_flow)
        assert "PaymentsToExploreAndDevelopOilAndGasProperties" in source
        assert "PaymentsToAcquireOilAndGasProperty" in source
        assert "CostsIncurredOilAndGasPropertyAcquisitionExplorationAndDevelopmentActivities" in source


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "20-F") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestOilGasMajorsIfrsCapexAliases:
    """Regression test for the same-day follow-up: TTE (TotalEnergies) and SHEL (Shell plc),
    both real oil & gas majors filing 20-F under IFRS, never matched either existing IFRS
    PP&E-purchase alias - their capex stayed NULL despite real, current, plausible-scale
    data being on file under filer-specific IFRS extension concepts."""

    def test_tte_additions_ppe_pre_2024_variant_maps_to_capex(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment": {
                    "units": {"USD": [_entry(2023, 16_478_000_000.0, "2024-03-01")]}
                },
            },
        }
        rows = get_cash_flow(_FakeClient(facts), "TTE", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2023]["payments_to_acquire_property_plant_and_equipment"] == 16_478_000_000.0

    def test_tte_additions_ppe_including_rou_2024_onward_variant_maps_to_capex(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipmentIncludingRightofuseAssets": {
                    "units": {"USD": [_entry(2025, 15_756_000_000.0, "2026-03-01")]}
                },
            },
        }
        rows = get_cash_flow(_FakeClient(facts), "TTE", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["payments_to_acquire_property_plant_and_equipment"] == 15_756_000_000.0

    def test_shel_ppe_construction_expenditures_maps_to_capex(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "PropertyPlantAndEquipmentExpendituresRecognisedForConstructions": {
                    "units": {"USD": [_entry(2025, 21_815_000_000.0, "2026-03-01")]}
                },
            },
        }
        rows = get_cash_flow(_FakeClient(facts), "SHEL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["payments_to_acquire_property_plant_and_equipment"] == 21_815_000_000.0


class TestToyotaIfrsCapexAlias:
    """Regression test for the 2026-09-03 follow-up: TM (Toyota Motor Corp), filing 20-F
    under IFRS, stopped tagging either us-gaap "PaymentsToAcquirePropertyPlantAndEquipment"
    or "PaymentsToAcquireProductiveAssets" after its FY2020 20-F - real capex continued
    under the ifrs-full "AdditionsToNoncurrentAssets" concept instead, previously unmapped."""

    def test_additions_to_noncurrent_assets_maps_to_capex(self, monkeypatch) -> None:
        monkeypatch.setattr(
            sec_statements._fx_rate_cache, "get_usd_rate", lambda code, date: 150.0 if code == "JPY" else None
        )
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "AdditionsToNoncurrentAssets": {"units": {"JPY": [_entry(2025, 5_991_268_000_000.0, "2026-06-24")]}},
            },
        }
        rows = get_cash_flow(_FakeClient(facts), "TM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["payments_to_acquire_property_plant_and_equipment"] == 5_991_268_000_000.0 / 150.0
