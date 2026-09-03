"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, DE debt gap investigation): Deere & Company's standard "LongTermDebtNoncurrent"
concept (already mapped, CAT/SLB/XOM fix) stopped reporting after FY2021 with no us-gaap/
ifrs successor - DE's real "Long-term borrowings" continued under a filer-specific custom
extension concept instead (de:LongTermDebtAndFinanceLeasesNoncurrent, handled by
CUSTOM_DEBT_LONGTERM_CONCEPTS - see test_sec_custom_xbrl_concepts.py's TestExtractCustomDebt
Deere for that half). This file covers the OTHER half: DE's real short-term debt
("Short-term borrowings") tagged under the plain, standard "DebtCurrent" concept, never
mapped before - live-confirmed $13,796,000,000 FY2025/$13,533,000,000 FY2024, real and
continuous back to FY2020.

DE also tags a smaller sibling concept ("SecuredDebt", "Short-term securitization
borrowings", $6,596,000,000 FY2025) that is DELIBERATELY NOT mapped here - this loader's
transform() has no summing mechanism for two concepts targeting the same column (plain
`row[db_field] = value` overwrite, last-processed-wins), so mapping both would silently
drop one of the two real figures rather than capture both. DebtCurrent alone (fallback-
only, since it's a generic enough name that a more specific standard concept - Commercial
Paper/ShortTermBorrowings/SeniorNotesCurrent - must always keep priority) is strictly
better than the prior NULL.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestDeDebtCurrentFixed:
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
            "commercial_paper": "short_term_debt",
            "debt_current": "short_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"debt_current"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_debt_current_to_short_term_debt(self) -> None:
        assert _BALANCE_FIELD_MAPPING["debt_current"] == "short_term_debt"
        assert "debt_current" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_de_style_short_term_debt_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "DE",
            "fiscal_year": 2025,
            "debt_current": 13_796_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 13_796_000_000.0

    def test_debt_current_never_overwrites_a_real_short_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "commercial_paper": 7_980_000_000.0,
            "debt_current": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 7_980_000_000.0
