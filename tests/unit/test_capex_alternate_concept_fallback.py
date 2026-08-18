"""Regression test: capex must be sourced from either real SEC concept filers use for it.

Live DB audit (2026-08-10) found free_cash_flow/fcf_to_net_income stuck at "SEC data not
available" for ~1,067 symbols despite operating_cash_flow being populated for most of
them. Root cause: annual_cash_flow.capex is only ever populated from a single us-gaap
concept ("PaymentsToAcquirePropertyPlantAndEquipment") and a single (and, live-confirmed,
never-matching) IFRS concept. Real filers use two other real tags instead:
  - AAON, KELYB, CPS, DTIL (US GAAP): "PaymentsToAcquireProductiveAssets" (live-confirmed
    via SEC companyfacts - AAON alone has 112 real entries back through FY2023, and
    reports NO "PaymentsToAcquirePropertyPlantAndEquipment" at all).
  - VALN (Valneva SE), IMTX (Immatics N.V.), ASM, VIVO, EFXT, ALAR (IFRS 20-F filers):
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities" - the previously
    mapped IFRS concept ("...IntangibleAssetsOtherThanGoodwillInvestmentPropertyAnd
    OtherNoncurrentAssets") never matched any real filer checked live.
This test locks in both new mappings so a future "cleanup" pass can't silently drop them
(see test_financial_statements_field_mapping_completeness.py for the sibling test that
catches a mapped-but-unfetched-elsewhere class of the same bug).
"""

from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING
from utils.external.sec_statements import _CASHFLOW_IFRS_ALIASES, _to_snake


class TestCapexAlternateConceptFallback:
    def test_payments_to_acquire_productive_assets_maps_to_capex(self):
        target_key = _to_snake("PaymentsToAcquireProductiveAssets")
        assert target_key == "payments_to_acquire_productive_assets"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_payments_to_acquire_machinery_and_equipment_maps_to_capex(self):
        # FIXED 2026-08-18: AAON tagged "PaymentsToAcquireProductiveAssets" (the fallback
        # above) only through FY2023 Q3, then switched to this concept for FY2023 Q4/10-K
        # onward with zero overlap - live-confirmed via SEC companyfacts real capex
        # ($104.3M FY2023, $195.7M FY2024, $190.6M FY2025). Neither capex concept was
        # fetched, so free_cash_flow/fcf_yield/fcf_to_net_income were NULL
        # ("missing_sec_data") for 3+ straight fiscal years despite a real, complete
        # operating_cash_flow every year.
        target_key = _to_snake("PaymentsToAcquireMachineryAndEquipment")
        assert target_key == "payments_to_acquire_machinery_and_equipment"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_payments_to_acquire_machinery_and_equipment_is_fetched(self):
        # A field_mapping entry alone is not enough - get_cash_flow()'s concept list must
        # actually request the concept from SEC or the mapping never fires (the exact
        # "mapped but unfetched" bug class test_financial_statements_field_mapping_
        # completeness.py guards more generally).
        import inspect

        from utils.external import sec_statements

        source = inspect.getsource(sec_statements.get_cash_flow)
        assert "PaymentsToAcquireMachineryAndEquipment" in source

    def test_standard_capex_concept_still_maps_to_capex(self):
        # Guards against the new fallback accidentally replacing, rather than
        # supplementing, the original (and still far more common) concept.
        target_key = _to_snake("PaymentsToAcquirePropertyPlantAndEquipment")
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_ifrs_capex_concept_alias_present_and_targets_capex_column(self):
        alias_map = dict(_CASHFLOW_IFRS_ALIASES)
        assert (
            alias_map.get("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities")
            == "payments_to_acquire_property_plant_and_equipment"
        )
        # The alias target_key must itself be mapped through to the real capex column.
        assert _CASHFLOW_FIELD_MAPPING["payments_to_acquire_property_plant_and_equipment"] == "capex"
