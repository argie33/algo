"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, total_debt_not_itemized investigation): AFL (Aflac) and MAA (Mid-America Apartment
Communities) both tag their entire real debt load under plain "NotesPayable" instead of any
LongTermDebt*/SeniorNotes*/DebtInstrument* concept already mapped - neither ever appeared in
our concept list, so both fell into the "structurally debt-free" bucket despite carrying
billions in real debt.

Live-confirmed via real SEC companyfacts JSON: AFL NotesPayable FY2025 $8,330,000,000, a
real, continuously growing figure back to FY2008 ($1.721B); MAA NotesPayable FY2025
$5,405,372,000, continuous back to FY2009 ($1.4B). Neither filer has a "NotesPayableCurrent"
sibling (no current/noncurrent split), so this is fallback-only (unlike VRSN's plain
SeniorNotes mapping) since "NotesPayable" is a generic enough concept name that a filer
reporting a real, more complete LongTermDebt/SeniorNotes figure must always keep that value.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestAflMaaNotesPayableDebtConceptFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "long_term_debt", "short_term_debt", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "notes_payable": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"notes_payable"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_notes_payable_to_long_term_debt(self) -> None:
        assert _BALANCE_FIELD_MAPPING["notes_payable"] == "long_term_debt"
        assert "notes_payable" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_afl_style_debt_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AFL",
            "fiscal_year": 2025,
            "notes_payable": 8_330_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 8_330_000_000.0

    def test_notes_payable_never_overwrites_a_real_long_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "long_term_debt": 95_281_000_000.0,
            "notes_payable": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 95_281_000_000.0
