"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep, second
follow-up pass): QS (QuantumScape) - the real "IncomeTaxExpenseBenefit" concept correctly
resolves $1,544,000 FY2025 (matching the yfinance-flagged value), but
sec_statements.py's _fill_income_tax_expense_from_current_deferred_split() then computes
a real $0 from CurrentIncomeTaxExpenseBenefit + DeferredIncomeTaxExpenseBenefit for this
filer and writes it directly to the SAME "income_tax_expense" identity key, processed
LAST in dict order, unconditionally overwriting the correct total via plain
(non-fallback) last-write-wins.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestQsIncomeTaxExpenseDerivedZeroOverwrite:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "income_tax_expense", "data_unavailable", "reason"})
        loader._field_mapping = {
            "income_tax_expense_benefit": "income_tax_expense",
            "income_tax_expense": "income_tax_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_derived_zero_never_overwrites_a_real_income_tax_expense_value(self) -> None:
        loader = self._make_loader()
        # Dict-insertion order matters: income_tax_expense_benefit (real, nonzero) is
        # processed first, then the derived-split identity key (real $0) processed last,
        # matching QS's real concept-list order.
        row = {
            "symbol": "QS",
            "fiscal_year": 2025,
            "income_tax_expense_benefit": 1_544_000.0,
            "income_tax_expense": 0.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["income_tax_expense"] == 1_544_000.0

    def test_genuine_zero_still_preserved_when_no_other_value_exists(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "NOZEROTAXCORP", "fiscal_year": 2025, "income_tax_expense": 0.0}

        transformed = loader.transform([row])

        assert transformed[0]["income_tax_expense"] == 0.0
