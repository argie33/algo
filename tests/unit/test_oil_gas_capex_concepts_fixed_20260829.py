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

from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING
from utils.external import sec_statements
from utils.external.sec_statements import _to_snake


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
