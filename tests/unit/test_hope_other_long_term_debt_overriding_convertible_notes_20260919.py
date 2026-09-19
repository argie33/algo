"""Regression test for the 2026-09-19 fix (/goal data-confidence audit): HOPE (Hope Bancorp,
CIK 0001128361) live-confirmed via the real filed FY2025 10-K balance-sheet parenthetical
(accession 0001128361-26-000011, R4.htm) - the filer's single combined line "Convertible notes
and subordinated debentures, net" ($110,962,000 FY2025) is tagged under us-gaap:OtherLongTermDebt,
while us-gaap:ConvertibleNotesPayable separately tags only a tiny $444,000 residual component of
that same combined total (most of HOPE's convertible notes matured/converted around FY2023 - its
own ConvertibleNotesPayable was $217,148,000, the real complete total, as recently as FY2022).
sec_balance_sheet.py's concept-fetch list processes ConvertibleNotesPayable before
OtherLongTermDebt, so the ordinary fallback-only "db_field in row" skip permanently protected the
stale $444,000 component from ever being overwritten by the real $110,962,000 combined total.

See loaders/helpers/sec_zero_component_guards.py's
is_other_long_term_debt_overriding_narrow_convertible_notes_component docstring for the guard
this tests.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestHopeOtherLongTermDebtOverridingConvertibleNotes:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "long_term_debt", "short_term_debt", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "convertible_notes_payable": "long_term_debt",
            "other_long_term_debt": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"convertible_notes_payable", "other_long_term_debt"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_hope_style_tiny_convertible_notes_overridden_by_much_larger_other_long_term_debt(self) -> None:
        loader = self._make_loader()
        # Dict-insertion order matches HOPE's real concept-list order: "convertible_notes_payable"
        # processed before "other_long_term_debt" (both fallback-only).
        row = {
            "symbol": "HOPE",
            "fiscal_year": 2025,
            "convertible_notes_payable": 444_000.0,
            "other_long_term_debt": 110_962_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 110_962_000.0

    def test_other_long_term_debt_does_not_override_a_close_or_comparable_convertible_notes_value(self) -> None:
        """A modest gap (well under the 5x floor) must not trigger the override - a filer whose
        ConvertibleNotesPayable genuinely IS close to its real total must not be touched."""
        loader = self._make_loader()
        row = {
            "symbol": "SOMEBANK",
            "fiscal_year": 2025,
            "convertible_notes_payable": 200_000_000.0,
            "other_long_term_debt": 220_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 200_000_000.0

    def test_convertible_notes_still_the_complete_total_when_other_long_term_debt_absent(self) -> None:
        """HOPE's own FY2018-2022 shape: ConvertibleNotesPayable alone was the real, complete
        total before OtherLongTermDebt was ever tagged - must remain untouched."""
        loader = self._make_loader()
        row = {
            "symbol": "HOPE",
            "fiscal_year": 2022,
            "convertible_notes_payable": 217_148_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 217_148_000.0
