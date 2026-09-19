"""Regression test for the 2026-09-19 fix (/goal data-confidence audit): O (Realty Income Corp,
CIK 0000726728, SIC 6798 equity REIT) live-confirmed via real SEC companyfacts JSON - tags a
real but immaterial "SecuredDebt" fact (a single mortgage note: $37,761,000 FY2025) alongside a
real, dramatically larger "NotesPayable" fact ($25,031,947,000 FY2025, close to yfinance's
flagged $26,771,323,000). redirect_secured_debt_for_reit correctly routes "secured_debt" to
long_term_debt for REIT filers, but "SecuredDebt" is not fallback-gated at all, so it processed
first and permanently blocked "NotesPayable" (fallback-only) from ever writing the real total via
the ordinary "db_field in row" fallback-only skip.

See loaders/helpers/sec_zero_component_guards.py's
is_narrow_secured_debt_blocking_notes_payable_total docstring for the guard this tests.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestOSecuredDebtBlockingNotesPayableFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "long_term_debt", "short_term_debt", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "secured_debt": "long_term_debt",
            "notes_payable": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"notes_payable"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_o_style_tiny_secured_debt_overridden_by_much_larger_notes_payable(self) -> None:
        loader = self._make_loader()
        # Dict-insertion order matches O's real concept-list order: "secured_debt" (not
        # fallback-gated) processed before "notes_payable" (fallback-only).
        row = {
            "symbol": "O",
            "fiscal_year": 2025,
            "secured_debt": 37_761_000.0,
            "notes_payable": 25_031_947_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 25_031_947_000.0

    def test_notes_payable_does_not_override_a_close_or_comparable_secured_debt_value(self) -> None:
        """A modest gap (well under the 5x floor) must not trigger the override - a REIT whose
        SecuredDebt genuinely IS close to its real total (OLP-class) must not be touched."""
        loader = self._make_loader()
        row = {
            "symbol": "OLP",
            "fiscal_year": 2025,
            "secured_debt": 500_000_000.0,
            "notes_payable": 600_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 500_000_000.0

    def test_secured_debt_still_never_overwrites_a_real_large_notes_payable_total(self) -> None:
        """Unchanged case: a real, large secured_debt value already correctly resolved must
        still be protected against being replaced by an immaterial notes_payable fact."""
        loader = self._make_loader()
        row = {
            "symbol": "SOMEREIT",
            "fiscal_year": 2025,
            "secured_debt": 2_000_000_000.0,
            "notes_payable": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 2_000_000_000.0
