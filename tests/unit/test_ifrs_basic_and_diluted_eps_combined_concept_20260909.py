"""Regression test for the 2026-09-09 fix (goal session: SEC/XBRL missing-data reduction,
eps_never_tagged_in_filings investigation): the IFRS taxonomy's combined
"BasicAndDilutedEarningsLossPerShare" concept - the direct analog of us-gaap's already-fetched
"EarningsPerShareBasicAndDiluted" - was never fetched at all, and was additionally miscategorized
as noise ("per-share, not $") in xbrl_concept_coverage.py's NOISE_SUBSTRINGS list, hiding the gap
from future scans.

Live-confirmed via real companyfacts JSON: NAK (Northern Dynasty Minerals, CIK 0001164771) tags
ONLY this concept for its real EPS (FY2016-2020, e.g. FY2020=0.13 CAD/shares) - no
BasicEarningsLossPerShare/DilutedEarningsLossPerShare at all; GLBS (Globus Maritime, CIK
0001499780) tags all three side by side with consistent values (FY2024 Basic=Diluted=this
concept=0.02), confirming it is a genuine duplicate tag for the same figure, not a different
measure.

Reuses the us-gaap concept's own raw key ("earnings_per_share_basic_and_diluted") so it inherits
that key's existing fallback-only registration in _REVENUE_FALLBACK_ONLY_FIELDS (see
test_eps_basic_and_diluted_combined_concept_fallback_20260909.py) - a filer reporting the real
Basic/Diluted split always keeps that value; this only fills the gap for a filer (like NAK) that
never tags either.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING, _REVENUE_FALLBACK_ONLY_FIELDS
from utils.external.sec_statements import _INCOME_IFRS_ALIASES
from utils.external.xbrl_concept_coverage import NOISE_SUBSTRINGS


class TestIfrsBasicAndDilutedEpsCombinedConceptAlias:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "earnings_per_share", "data_unavailable", "reason"})
        loader._field_mapping = {
            "earnings_per_share_basic": "earnings_per_share",
            "earnings_per_share_basic_and_diluted": "earnings_per_share",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"earnings_per_share_basic_and_diluted"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_alias_is_registered_for_ifrs_full_namespace(self) -> None:
        aliases = dict(_INCOME_IFRS_ALIASES)
        assert aliases["BasicAndDilutedEarningsLossPerShare"] == "earnings_per_share_basic_and_diluted"

    def test_alias_reuses_the_existing_fallback_only_gaap_target_key(self) -> None:
        target_key = "earnings_per_share_basic_and_diluted"
        assert _INCOME_FIELD_MAPPING[target_key] == "earnings_per_share"
        assert target_key in _REVENUE_FALLBACK_ONLY_FIELDS

    def test_nak_style_filer_recovered_when_split_concepts_are_absent(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "NAK", "fiscal_year": 2020, "earnings_per_share_basic_and_diluted": 0.13}

        transformed = loader.transform([row])

        assert transformed[0]["earnings_per_share"] == 0.13

    def test_real_basic_split_value_still_wins_when_both_are_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "GLBS",
            "fiscal_year": 2024,
            "earnings_per_share_basic": 0.02,
            "earnings_per_share_basic_and_diluted": 0.02,
        }

        transformed = loader.transform([row])

        assert transformed[0]["earnings_per_share"] == 0.02

    def test_concept_no_longer_wrongly_dismissed_as_noise(self) -> None:
        # This concept IS the headline EPS figure the schema wants - it must not be matched by
        # any noise substring (that classification previously hid this real gap from
        # scripts/xbrl_concept_coverage_scan.py).
        assert not any(substr in "BasicAndDilutedEarningsLossPerShare" for substr in NOISE_SUBSTRINGS)
