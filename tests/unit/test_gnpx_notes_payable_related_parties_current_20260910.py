"""Regression test for the 2026-09-10 fix (goal session: SEC/XBRL missing-data count under
500, total_debt_not_itemized investigation): GNPX (Genprex) tags its real current-year
related-party loan under "NotesPayableRelatedPartiesClassifiedCurrent" - a current-portion
sibling of the already-fetched "NotesPayableRelatedPartiesNoncurrent" - which was never in our
short_term_debt concept list, so GNPX fell into the "structurally debt-free" bucket despite
carrying a real, XBRL-tagged related-party note payable.

Live-confirmed via real SEC companyfacts JSON (CIK 0001595248): GNPX tags
NotesPayableRelatedPartiesClassifiedCurrent but never any of NotesPayableCurrent/
ShortTermBorrowings/CommercialPaper/DebtCurrent/etc. Fallback-only, same generic-name caution
as notes_payable_current - a filer reporting a more specific standard concept must always keep
that value.
"""

from loaders.helpers.financial_statements_balance_config import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS
from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestGnpxNotesPayableRelatedPartiesCurrent:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "long_term_debt", "short_term_debt", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "short_term_debt": "short_term_debt",
            "notes_payable_related_parties_classified_current": "short_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"notes_payable_related_parties_classified_current"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_concept_to_short_term_debt(self) -> None:
        assert _BALANCE_FIELD_MAPPING["notes_payable_related_parties_classified_current"] == "short_term_debt"
        assert "notes_payable_related_parties_classified_current" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_gnpx_style_debt_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "GNPX",
            "fiscal_year": 2025,
            "notes_payable_related_parties_classified_current": 250_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 250_000.0

    def test_never_overwrites_a_real_short_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "short_term_debt": 10_912_000_000.0,
            "notes_payable_related_parties_classified_current": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 10_912_000_000.0
