"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep, second
follow-up pass): 7 more genuine debt/borrowed-funds concepts found by scanning EVERY
numeric fact in each filer's full companyfacts JSON for one that exactly matches
xbrl_yfinance_line_item_report's flagged long_term_debt value (not from a predefined
candidate list):

- CPIX/NSYS/QTTB: "LongTermLineOfCredit" ($5,240,733 / $8,959,000 / $9,556,000)
- FFIN: "OtherBorrowings" ($21,055,000)
- LNZA: "LongTermLoansPayable" ($10,900,000)
- UE (equity REIT): "NotesAndLoansPayable" ($1,606,774,000)
- UFCS (P&C insurer): "SurplusNotes" ($146,200,000)
- IBKR (broker-dealer): "SecuritiesLoaned" ($11,347,000,000)
- GPMT (mortgage REIT): "BeneficialInterest" ($991,698,000)

All fallback-only - must never win over a real value the standard debt concepts already
found.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS

NEW_CONCEPTS = [
    "long_term_line_of_credit",
    "other_borrowings",
    "long_term_loans_payable",
    "notes_and_loans_payable",
    "surplus_notes",
    "securities_loaned",
    "beneficial_interest",
]


class TestSevenDebtConceptsFullCompanyfactsScan:
    def _make_loader(self, sec_field: str) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "long_term_debt", "data_unavailable", "reason"})
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            sec_field: "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({sec_field})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mappings_and_fallback_only_wired(self) -> None:
        for sec_field in NEW_CONCEPTS:
            assert _BALANCE_FIELD_MAPPING[sec_field] == "long_term_debt"
            assert sec_field in _DEBT_FALLBACK_ONLY_FIELDS

    def test_each_concept_fills_empty_long_term_debt(self) -> None:
        for sec_field in NEW_CONCEPTS:
            loader = self._make_loader(sec_field)
            row = {"symbol": "TESTCO", "fiscal_year": 2025, sec_field: 12_345.0}

            transformed = loader.transform([row])

            assert transformed[0]["long_term_debt"] == 12_345.0, sec_field

    def test_each_concept_never_overwrites_a_real_long_term_debt_value(self) -> None:
        for sec_field in NEW_CONCEPTS:
            loader = self._make_loader(sec_field)
            row = {
                "symbol": "TESTCO",
                "fiscal_year": 2025,
                "long_term_debt": 500_000_000.0,
                sec_field: 1.0,
            }

            transformed = loader.transform([row])

            assert transformed[0]["long_term_debt"] == 500_000_000.0, sec_field
