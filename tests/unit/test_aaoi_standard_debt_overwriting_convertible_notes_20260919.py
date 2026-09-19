"""Regression test for the 2026-09-19 fix (/goal scores-accuracy audit, closing
generic_concept_overwrite_bugs_20260919's "neither fixed in code" gap for the AAOI shape):
AAOI (Applied Optoelectronics, CIK 1158114) tags its real debt under
"ConvertibleNotesPayable"/"ConvertibleLongTermNotesPayable" - but the plain "LongTermDebt"
concept, unlike its fallback-gated siblings, is not fallback-only at all, so its own
real-but-different, SMALLER figure unconditionally overwrote the already-resolved convertible
notes value via ordinary last-listed-wins.

Live-confirmed via real SEC companyfacts JSON 2026-09-19, re-verified through the actual
production loader pipeline (ConsolidatedFinancialStatementsLoader with
LOADER_STATEMENT_TYPE=balance/LOADER_PERIOD=annual, not just the isolated transform() call this
test uses): FY2022 $79,506,000, FY2023 $76,233,000, FY2025 $129,829,000 - all exact matches to
yfinance's independently-sourced flagged values once this guard is applied; FY2024 $134,497,000
vs yfinance $138,810,000 (~3% gap, plausibly a different point-in-time snapshot, not a fix
failure).

See loaders/helpers/sec_zero_component_guards.py's is_standard_debt_overwriting_convertible_notes
docstring for the guard this tests.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestAaoiStandardDebtOverwritingConvertibleNotes:
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
            "convertible_notes_payable": "long_term_debt",
            "convertible_long_term_notes_payable": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"convertible_notes_payable", "convertible_long_term_notes_payable"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_aaoi_real_fetch_order_convertible_notes_first_then_plain_long_term_debt(self) -> None:
        """The actual live AAOI shape: ConvertibleNotesPayable is listed before "LongTermDebt"
        in sec_balance_sheet.py's concept-fetch list, so it's processed (and written) first,
        then the plain standard concept - not fallback-gated at all - would otherwise
        unconditionally overwrite it via ordinary last-listed-wins."""
        loader = self._make_loader()
        row = {
            "symbol": "AAOI",
            "fiscal_year": 2025,
            "convertible_notes_payable": 129_829_000.0,
            "long_term_debt": 33_975_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 129_829_000.0

    def test_plain_long_term_debt_still_wins_when_it_is_the_larger_real_increase(self) -> None:
        """A genuine debt increase (the plain concept's value at or above the already-resolved
        convertible-notes figure) must still win normally - this guard only blocks a SMALLER
        incoming value, not a legitimate larger one."""
        loader = self._make_loader()
        row = {
            "symbol": "SOMECO",
            "fiscal_year": 2025,
            "convertible_notes_payable": 100_000_000.0,
            "long_term_debt": 150_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 150_000_000.0

    def test_plain_long_term_debt_unaffected_when_no_convertible_notes_value_present(self) -> None:
        """Ordinary filer with no convertible-notes concept at all - the plain concept must
        still write normally, unaffected by this narrow guard."""
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "long_term_debt": 95_281_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 95_281_000_000.0
