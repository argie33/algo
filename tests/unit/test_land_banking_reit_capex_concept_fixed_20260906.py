"""Regression test for the 2026-09-06 fix (goal: "capex_never_tagged_in_recent_filings"
sweep across the active universe): MRP (Millrose Properties, Inc., CIK 2017206), a
land-banking REIT spun off from Lennar in Feb 2025 whose entire business model is
acquiring and optioning land to homebuilders, reports NEITHER any PP&E-family concept nor
any of the existing REIT-family concepts (PaymentsToAcquireRealEstate,
PaymentsToAcquireAndDevelopRealEstate, PaymentsForCapitalImprovements,
PaymentsToAcquireCommercialRealEstate, PaymentsToDevelopRealEstateAssets).

Live-confirmed via real companyfacts JSON: a single (only FY2025 exists post-spinoff),
real value of $858,938,000 under "PaymentsToAcquireLand" - plausible against MRP's own
reported $9.258B total assets / $5.856B stockholders' equity for the same fiscal year
(accn 0002017206-26-000002). Standard (not filer-specific) us-gaap concept - the direct
cash equivalent of capex for a land-acquisition-as-core-business REIT.

A broad live sweep this same session (~60 symbols across SIC 1040/2834/2836/6199/6282/
6311/6331/6798 and BDC clusters carrying the same unavailable-reason) found no other
genuine unhandled capex concept - mortgage REITs, BDCs, asset managers, insurers, and
pharma/biotech filers checked only report investment-securities/loan purchase concepts
(a fundamentally different economic activity from capex), correctly NOT added here.
"""

import inspect

from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING
from utils.external import sec_statements
from utils.external.sec_statements import _to_snake


class TestLandBankingReitCapexConceptFixed:
    def test_payments_to_acquire_land_maps_to_capex(self):
        target_key = _to_snake("PaymentsToAcquireLand")
        assert target_key == "payments_to_acquire_land"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_payments_to_acquire_land_concept_is_fetched(self):
        # A field_mapping entry alone is not enough - get_cash_flow()'s concept list must
        # actually request the concept from SEC or the mapping never fires (the "mapped but
        # unfetched" bug class test_financial_statements_field_mapping_completeness.py
        # guards more generally).
        source = inspect.getsource(sec_statements.get_cash_flow)
        assert "PaymentsToAcquireLand" in source
