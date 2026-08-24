"""Regression test for the 2026-08-24 fix (goal: "Margin of Safety (DCF) / Cash flow data
unavailable" audit): REITs (SIC 6798) never tag any of the PP&E-family capex concepts
(PaymentsToAcquirePropertyPlantAndEquipment and its siblings) - their capex is real property
investment, tagged under a completely different concept family.

Live-confirmed via real companyfacts JSON: AAT (American Assets Trust) tags
"PaymentsForCapitalImprovements" ($70.2M FY2024); AHT (Ashford Hospitality Trust) tags the
same concept ($108.0M FY2024); AHR (American Healthcare REIT) and ABR (Arbor Realty Trust, a
commercial mortgage REIT that still holds some real estate) tag
"PaymentsToAcquireRealEstate"/"PaymentsToAcquireAndDevelopRealEstate" ($60.4M/$3.47M
FY2024). None of these filers report under any PP&E-family concept at all - a genuine
unextracted-data gap (134 SIC-6798 symbols found with
intrinsic_value_unavailable_reason='missing_cash_flow_data' in a live DB audit), not a
structural absence like the depository-institution case
(test_bank_capex_structural_gap_fixed_20260822.py).

Pure agency-mortgage REITs with no real estate at all (e.g. AGNC, which only tags
MBS-purchase concepts, never any real-estate or PP&E concept) correctly remain uncovered by
this fix - a genuine structural gap for that subclass, not addressed here.
"""

import inspect

from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING
from utils.external import sec_statements
from utils.external.sec_statements import _to_snake


class TestReitCapexConceptsFixed:
    def test_payments_for_capital_improvements_maps_to_capex(self):
        target_key = _to_snake("PaymentsForCapitalImprovements")
        assert target_key == "payments_for_capital_improvements"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_payments_to_acquire_real_estate_maps_to_capex(self):
        target_key = _to_snake("PaymentsToAcquireRealEstate")
        assert target_key == "payments_to_acquire_real_estate"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_payments_to_acquire_and_develop_real_estate_maps_to_capex(self):
        target_key = _to_snake("PaymentsToAcquireAndDevelopRealEstate")
        assert target_key == "payments_to_acquire_and_develop_real_estate"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_reit_capex_concepts_are_fetched(self):
        # A field_mapping entry alone is not enough - get_cash_flow()'s concept list must
        # actually request the concept from SEC or the mapping never fires (the "mapped but
        # unfetched" bug class test_financial_statements_field_mapping_completeness.py
        # guards more generally).
        source = inspect.getsource(sec_statements.get_cash_flow)
        assert "PaymentsForCapitalImprovements" in source
        assert "PaymentsToAcquireRealEstate" in source
        assert "PaymentsToAcquireAndDevelopRealEstate" in source


class TestInsurerInvestmentRealEstateCapexConceptsFixed:
    """Insurers hold investment real estate as part of their portfolio, tagged under two
    insurer-specific concepts distinct from both the PP&E family and the REIT family above.
    Live-confirmed: MET (MetLife) $633M FY2025, RGA (Reinsurance Group of America) $1.073B
    FY2025 under "PaymentsToAcquireRealEstateAndRealEstateJointVentures"; PFG (Principal
    Financial) $135.5M FY2025, TRV (Travelers) $48M FY2025 under
    "PaymentsToAcquireRealEstateHeldForInvestment"."""

    def test_payments_to_acquire_real_estate_and_joint_ventures_maps_to_capex(self):
        target_key = _to_snake("PaymentsToAcquireRealEstateAndRealEstateJointVentures")
        assert target_key == "payments_to_acquire_real_estate_and_real_estate_joint_ventures"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_payments_to_acquire_real_estate_held_for_investment_maps_to_capex(self):
        target_key = _to_snake("PaymentsToAcquireRealEstateHeldForInvestment")
        assert target_key == "payments_to_acquire_real_estate_held_for_investment"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_insurer_capex_concepts_are_fetched(self):
        source = inspect.getsource(sec_statements.get_cash_flow)
        assert "PaymentsToAcquireRealEstateAndRealEstateJointVentures" in source
        assert "PaymentsToAcquireRealEstateHeldForInvestment" in source
