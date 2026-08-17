"""Regression test for the 2026-08-17 long-term-debt fallback concepts (loader-review
goal continuation).

A live DB scan found 2,306 symbols with real (non-data_unavailable) annual_balance_sheet
rows that had NEVER had a single long_term_debt value across every fiscal year. Live
SEC companyfacts checks on a sample (MRKR, MODD, ATNM) confirmed real, instant-fact debt
reported under alternate concepts ("NotesPayableRelatedPartiesNoncurrent",
"LongTermNotesPayable", "ConvertibleNotesPayable") that were never fetched - these filers
simply never tag the standard "LongTermDebt" concept at all.

Added as fallback-only fields (same "don't clobber a real total" mechanism already used
for sales_revenue_net/interest_income_operating - see
test_sec_sales_revenue_net_not_overwritten.py) so a filer that DOES report the standard
LongTermDebt concept always keeps that value; these only fill genuinely empty years.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS
from utils.external.sec_statements import _to_snake


class TestDebtFallbackConceptMappings:
    def test_fallback_concepts_map_to_long_term_debt(self) -> None:
        for concept in ("NotesPayableRelatedPartiesNoncurrent", "LongTermNotesPayable", "ConvertibleNotesPayable"):
            target_key = _to_snake(concept)
            assert _BALANCE_FIELD_MAPPING[target_key] == "long_term_debt"
            assert target_key in _DEBT_FALLBACK_ONLY_FIELDS

    def test_standard_long_term_debt_concept_still_maps_directly(self) -> None:
        assert _BALANCE_FIELD_MAPPING["long_term_debt"] == "long_term_debt"
        assert "long_term_debt" not in _DEBT_FALLBACK_ONLY_FIELDS


class TestDebtFallbackNotOverwritingRealLongTermDebt:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "long_term_debt", "data_unavailable", "reason"})
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "long_term_notes_payable": "long_term_debt",
            "convertible_notes_payable": "long_term_debt",
            "notes_payable_related_parties_noncurrent": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _DEBT_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_real_long_term_debt_not_overwritten_by_fallback_concept(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "long_term_debt": 90_700_000_000.0,
            "convertible_notes_payable": 123.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 90_700_000_000.0

    def test_fallback_concept_populates_debt_when_standard_concept_absent(self) -> None:
        # MRKR-style micro-cap filer: never tags "LongTermDebt" at all, only
        # ConvertibleNotesPayable - previously silently treated as debt-free.
        loader = self._make_loader()
        row = {
            "symbol": "MRKR",
            "fiscal_year": 2015,
            "convertible_notes_payable": 52_942.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 52_942.0
