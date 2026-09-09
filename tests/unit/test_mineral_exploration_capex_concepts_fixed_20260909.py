"""Regression test for the 2026-09-09 fix (goal: "capex_never_tagged_in_recent_filings"
86-symbol sweep): mineral exploration/development-stage and mining filers report capex
under 2 concepts never fetched at all before this fix.

1. "PurchaseOfExplorationAndEvaluationAssets" (ifrs-full) - live-confirmed via real
   companyfacts JSON on Lifezone Metals (LZM, CIK 1958217, developing the Kabanga Nickel
   project in Tanzania): FY2025 $21,826,327 / FY2024 $49,951,501 / FY2023 $51,355,297,
   each closely tracking (~95-105% of) the same fiscal year's real
   "CashFlowsFromUsedInInvestingActivities" total - the dominant driver of LZM's investing
   outflow, not a minor sub-line. Also live-confirmed on Foremost Clean Energy (FMST, CIK
   1935418): CAD 249,957 FY2024/25 - same concept, confirming it is a standard (not
   filer-specific) IFRS taxonomy element for the sector.

2. "PaymentsToAcquireMineralRights" (us-gaap) - live-confirmed via real companyfacts JSON
   on large, well-known filers: Freeport-McMoRan $2,200,000,000, Royal Gold
   $1,164,753,000, Diamondback Energy $444,083,000, Coeur Mining $116,898,000 - all real,
   current, substantial 10-K figures. Also live-confirmed on Trilogy Metals (TMQ, one of
   this session's 86 target symbols): real annual values through FY2021 ($119,000).

Deliberately NOT added in the same investigation (see sec_cash_flow.py's get_cash_flow()
comment for the full evidence): TFPM's (Triple Flag Precious Metals)
"PaymentsForExplorationAndEvaluationExpenses" (only 4% of its real investing outflow, a
minor incidental sub-line for a royalty/streaming company whose real investing activity
is buying royalty interests, not PP&E capex) and TMQ's own
"SignificantCostsIncurredToAcquireMineralInterestOfProvedReserves" (only 6 filers use it,
and TMQ's own values are "since inception" cumulative totals, not per-fiscal-year
durations - unsafe to aggregate by fiscal_year).
"""

import inspect

from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING
from utils.external import sec_statements
from utils.external.sec_statements import _to_snake


class TestMineralExplorationCapexConceptsFixed:
    def test_purchase_of_exploration_and_evaluation_assets_maps_to_capex(self):
        target_key = _to_snake("PurchaseOfExplorationAndEvaluationAssets")
        assert target_key == "purchase_of_exploration_and_evaluation_assets"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_payments_to_acquire_mineral_rights_maps_to_capex(self):
        target_key = _to_snake("PaymentsToAcquireMineralRights")
        assert target_key == "payments_to_acquire_mineral_rights"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_both_concepts_are_actually_fetched(self):
        # A field_mapping entry alone is not enough - get_cash_flow()'s concept list must
        # actually request the concept from SEC or the mapping never fires (the "mapped but
        # unfetched" bug class test_financial_statements_field_mapping_completeness.py
        # guards more generally).
        source = inspect.getsource(sec_statements.get_cash_flow)
        assert "PurchaseOfExplorationAndEvaluationAssets" in source
        assert "PaymentsToAcquireMineralRights" in source
