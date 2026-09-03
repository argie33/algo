"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data" sweep,
capex_never_tagged_in_recent_filings investigation): water utilities (SIC 4941) never tag
any of the PP&E/REIT/insurance-family capex concepts already in get_cash_flow()'s concept
list - their capex is tagged under a sector-specific concept instead.

Live-confirmed via real companyfacts JSON: CWT (California Water Service Group, CIK 1035201)
tags "PaymentsToAcquireWaterAndWasteWaterSystems" with real, growing annual values - FY2025
$516,991,000 / FY2024 $470,800,000 / FY2023 $383,747,000 - and tags zero PP&E-family
concepts anywhere in its companyfacts JSON. A genuine unextracted-data gap, not a structural
absence, same bug class as the REIT/insurance/oil-gas sector capex fixes
(test_reit_capex_concepts_fixed_20260824.py etc.). 13 SIC-4941 symbols in the universe -
only CWT verified live this session, but the concept is a standard us-gaap tag (not a
filer-specific extension), so this should recover the whole sector wherever it applies.
"""

import inspect

from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING
from utils.external import sec_statements
from utils.external.sec_statements import _to_snake


class TestWaterUtilityCapexConceptFixed:
    def test_payments_to_acquire_water_and_waste_water_systems_maps_to_capex(self):
        target_key = _to_snake("PaymentsToAcquireWaterAndWasteWaterSystems")
        assert target_key == "payments_to_acquire_water_and_waste_water_systems"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_water_utility_capex_concept_is_fetched(self):
        # A field_mapping entry alone is not enough - get_cash_flow()'s concept list must
        # actually request the concept from SEC or the mapping never fires (the "mapped but
        # unfetched" bug class test_financial_statements_field_mapping_completeness.py
        # guards more generally).
        source = inspect.getsource(sec_statements.get_cash_flow)
        assert "PaymentsToAcquireWaterAndWasteWaterSystems" in source
