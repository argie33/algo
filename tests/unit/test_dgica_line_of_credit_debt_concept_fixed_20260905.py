"""Regression test for the 2026-09-05 fix (goal session: "missing SEC/XBRL data" sweep,
total_debt_not_itemized investigation): Donegal Group (DGICA/DGICB, CIK 0000800457) - a small
insurance holding company - tags its only real debt instrument, a $35,000,000 revolving credit
facility, exclusively under the plain "LineOfCredit" us-gaap concept.

Live-confirmed via real SEC companyfacts JSON (FY2025 balance) that Donegal never tags
LongTermDebt/NotesPayable/SubordinatedDebt/SeniorNotes or any other debt concept the loader
already fetches - "LineOfCredit" is its only real debt fact. No Current/Noncurrent split
reported, so single-figure fallback targeting long_term_debt, same convention as
notes_payable/subordinated_debt. Fallback-only since a filer reporting a more specific standard
debt concept must always keep that value.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestDgicaLineOfCreditDebtConceptFixed:
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
            "line_of_credit": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"line_of_credit"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_line_of_credit_concept_to_long_term_debt(self) -> None:
        assert _BALANCE_FIELD_MAPPING["line_of_credit"] == "long_term_debt"
        assert "line_of_credit" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_dgica_style_debt_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "DGICA",
            "fiscal_year": 2025,
            "line_of_credit": 35_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 35_000_000.0

    def test_never_overwrites_a_real_long_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMECORP",
            "fiscal_year": 2025,
            "notes_payable": 8_330_000_000.0,
            "line_of_credit": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 8_330_000_000.0
