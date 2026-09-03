"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, no_recent_debt_components_symbols investigation): VRSN (VeriSign) tags its real,
current debt exclusively under "SeniorNotes"/"SeniorNotesCurrent" - neither ever appeared
in our concept list, so VeriSign fell into the "structurally debt-free" bucket despite
carrying ~$1.79B in real senior notes.

Live-confirmed via real SEC companyfacts JSON: SeniorNotes (noncurrent) $1,788,200,000
FY2025, growing basis from FY2024's $1,792,300,000; VeriSign's older "LongTermDebt"
concept has been a real $0 since FY2013 and "ConvertibleDebt" since FY2018 (paid off, not
still in use) - no overlap with SeniorNotes's real values in any year, so a plain
(non-fallback) mapping is safe, same convention as CommercialPaper/ShortTermBorrowings.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING


class TestVrsnSeniorNotesDebtConceptFixed:
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
            "senior_notes": "long_term_debt",
            "commercial_paper": "short_term_debt",
            "senior_notes_current": "short_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_both_concepts(self) -> None:
        assert _BALANCE_FIELD_MAPPING["senior_notes"] == "long_term_debt"
        assert _BALANCE_FIELD_MAPPING["senior_notes_current"] == "short_term_debt"

    def test_vrsn_style_debt_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "VRSN",
            "fiscal_year": 2025,
            "senior_notes": 1_788_200_000.0,
            "senior_notes_current": 0.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 1_788_200_000.0
        assert transformed[0]["short_term_debt"] == 0.0
