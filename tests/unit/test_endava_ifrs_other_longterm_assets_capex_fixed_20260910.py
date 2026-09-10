"""Regression test for the 2026-09-10 fix (goal session: re-verify
"capex_never_tagged_in_recent_filings" against real cached companyfacts JSON, per the
user's "assume prior sweeps might have missed something" directive rather than trusting
memory that this bucket is closed).

DAVA (Endava plc, CIK 0001656081, IT-services 20-F/IFRS filer) tags NONE of the existing
ifrs-full PP&E-purchase concepts in sec_cash_flow.py's _CASHFLOW_IFRS_ALIASES for any
fiscal year, despite reporting a real, growing PropertyPlantAndEquipment balance
(GBP20.78M FY2024 / GBP14.18M FY2025). Live-confirmed via real companyfacts JSON: its
actual capex cash outflow is tagged under
"PurchaseOfOtherLongtermAssetsClassifiedAsInvestingActivities" instead - real, continuous,
plausible-scale annual values every fiscal year FY2016-2025 (GBP2.75M-13.97M, always well
below both PropertyPlantAndEquipment book value and total CashFlowsFromUsedInInvestingActivities
for the same year - a genuine partial sub-line, not a placeholder or implausible outlier).
Not filer-specific: 75 distinct filers in the on-disk companyfacts cache tag this concept,
including large well-known IFRS names (Unilever, Novartis, AstraZeneca, Shell, Canadian
Natural Resources, RELX) - a standard taxonomy element that was simply missing from this
alias list, same bug class as this list's other IFRS PP&E-purchase entries.
"""

import inspect

from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING
from utils.external import sec_cash_flow
from utils.external.sec_cash_flow import _CASHFLOW_IFRS_ALIASES


class TestEndavaIfrsOtherLongtermAssetsCapexFixed:
    def test_concept_registered_as_ifrs_alias_targeting_capex_key(self):
        alias_map = dict(_CASHFLOW_IFRS_ALIASES)
        assert (
            alias_map.get("PurchaseOfOtherLongtermAssetsClassifiedAsInvestingActivities")
            == "payments_to_acquire_property_plant_and_equipment"
        )

    def test_target_key_maps_to_capex_column(self):
        assert _CASHFLOW_FIELD_MAPPING["payments_to_acquire_property_plant_and_equipment"] == "capex"

    def test_new_alias_listed_after_existing_ppe_purchase_aliases(self):
        # ifrs_aliases use first-match-wins per (fiscal_year, target_key) - see
        # sec_cash_flow.py's own comment on this convention. The new fallback entry must
        # be listed AFTER every existing higher-priority PP&E-purchase alias so it only
        # fills the gap when all of them are absent for that fiscal year, never overwrites
        # a more specific real value.
        names = [concept for concept, _target in _CASHFLOW_IFRS_ALIASES]
        higher_priority = [
            "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
            "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
            "AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment",
            "AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipmentIncludingRightofuseAssets",
            "PropertyPlantAndEquipmentExpendituresRecognisedForConstructions",
            "AdditionsToNoncurrentAssets",
        ]
        new_index = names.index("PurchaseOfOtherLongtermAssetsClassifiedAsInvestingActivities")
        for concept in higher_priority:
            assert names.index(concept) < new_index, f"{concept} must be listed before the new fallback alias"

    def test_get_cash_flow_source_references_the_alias_list(self):
        source = inspect.getsource(sec_cash_flow.get_cash_flow)
        assert "_CASHFLOW_IFRS_ALIASES" in source
