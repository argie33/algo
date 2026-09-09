"""Regression test for the 2026-09-09 fix (goal: SEC/XBRL missing-data count under 700,
eps_never_tagged_in_filings investigation): EH (EHang, 20-F foreign private issuer) and 10
other cached filers report one combined "EarningsPerShareBasicAndDiluted" XBRL concept
instead of the split Basic/Diluted pair - never fetched anywhere in this codebase, so their
earnings_per_share went NULL forever, cascading into pe_ratio/ps_ratio/dividend_yield/
sec_valuations.

Fallback-only (via _REVENUE_FALLBACK_ONLY_FIELDS, the shared fallback-only bucket for this
file despite its name) - a filer reporting the real Basic/Diluted split always keeps that
value.
"""

from loaders.load_financial_statements import _INCOME_FIELD_MAPPING, _REVENUE_FALLBACK_ONLY_FIELDS
from utils.external.sec_statements import _to_snake


class TestEarningsPerShareBasicAndDilutedFallback:
    def test_concept_maps_to_earnings_per_share(self) -> None:
        target_key = _to_snake("EarningsPerShareBasicAndDiluted")
        assert target_key == "earnings_per_share_basic_and_diluted"
        assert _INCOME_FIELD_MAPPING[target_key] == "earnings_per_share"

    def test_concept_is_fallback_only(self) -> None:
        target_key = _to_snake("EarningsPerShareBasicAndDiluted")
        assert target_key in _REVENUE_FALLBACK_ONLY_FIELDS

    def test_standard_split_concepts_still_map_directly_and_are_not_fallback_only(self) -> None:
        basic_key = _to_snake("EarningsPerShareBasic")
        assert _INCOME_FIELD_MAPPING[basic_key] == "earnings_per_share"
        assert basic_key not in _REVENUE_FALLBACK_ONLY_FIELDS
