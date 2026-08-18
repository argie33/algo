"""Regression test for the 2026-08-18 "roic_pct missing_sec_data" audit continuation.

"StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest" is the total-equity
(including noncontrolling/minority interest) us-gaap concept some filers tag instead of the
parent-only "StockholdersEquity" concept. Live-confirmed via real SEC companyfacts JSON that ADM
(Archer-Daniels-Midland, CIK 0000007084) has ZERO "StockholdersEquity" facts ever filed, only
this concept (e.g. FY2021 $22,508,000,000) - so stockholders_equity was NULL for every fiscal
year on file, which cascades into roic_pct (and any other metric needing invested capital)
failing with the generic "missing_sec_data" reason for an otherwise ordinary, profitable
operating company. A live DB scan found 115 symbols with 2+ real (non-data_unavailable)
annual_balance_sheet rows where stockholders_equity was NULL in every single one - after
excluding commodity/crypto trusts and ETFs with no real XBRL company facts (AAAU, BAR, BITB,
BITW, BNO, BDRY, ...), several (ADM, AAON among them) are ordinary operating companies that
should have this field.

Added as a fallback-only field (same "don't clobber a real total" mechanism already used for
the long-term-debt fallbacks - see test_sec_debt_fallback_concepts_not_overwriting.py) so a
filer that DOES report the standard "StockholdersEquity" concept always keeps that (more
precise, parent-only) value; this only fills genuinely empty years/filers.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS
from utils.external.sec_statements import _to_snake


class TestStockholdersEquityFallbackConceptMapping:
    def test_fallback_concept_maps_to_stockholders_equity(self) -> None:
        target_key = _to_snake("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
        assert _BALANCE_FIELD_MAPPING[target_key] == "stockholders_equity"
        assert target_key in _DEBT_FALLBACK_ONLY_FIELDS

    def test_standard_stockholders_equity_concept_still_maps_directly(self) -> None:
        assert _BALANCE_FIELD_MAPPING["stockholders_equity"] == "stockholders_equity"
        assert "stockholders_equity" not in _DEBT_FALLBACK_ONLY_FIELDS


class TestStockholdersEquityFallbackNotOverwritingRealValue:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "stockholders_equity", "data_unavailable", "reason"})
        loader._field_mapping = {
            "stockholders_equity": "stockholders_equity",
            "stockholders_equity_including_portion_attributable_to_noncontrolling_interest": "stockholders_equity",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _DEBT_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_real_stockholders_equity_not_overwritten_by_fallback_concept(self) -> None:
        # A filer reporting BOTH concepts for the same fiscal year (common for companies with
        # partially-owned subsidiaries) must keep the smaller, more precise parent-only figure,
        # not the larger total-including-noncontrolling-interest one.
        loader = self._make_loader()
        row = {
            "symbol": "TEST",
            "fiscal_year": 2024,
            "stockholders_equity": 4_500_000_000.0,
            "stockholders_equity_including_portion_attributable_to_noncontrolling_interest": 5_000_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stockholders_equity"] == 4_500_000_000.0

    def test_fallback_concept_populates_equity_when_standard_concept_absent(self) -> None:
        # ADM-style filer: never tags "StockholdersEquity" at all, only the
        # noncontrolling-interest-inclusive concept - previously silently NULL forever.
        loader = self._make_loader()
        row = {
            "symbol": "ADM",
            "fiscal_year": 2021,
            "stockholders_equity_including_portion_attributable_to_noncontrolling_interest": 22_508_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stockholders_equity"] == 22_508_000_000.0
