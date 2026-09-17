"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep,
our_value=0-vs-real-yfinance-value audit): TER (Teradyne), TRUG, SIF (SIFCO), PVLA, TITN -
each tags a real "$0 of interest specifically on debt instruments" fact under
InterestExpenseDebt for the SAME fiscal year they also report a real, nonzero total under
plain InterestExpense/InterestExpenseNonoperating.

InterestExpenseDebt was a PLAIN (non-fallback) concept, so whichever of the two got
processed last in the concept list won unconditionally - for these filers
InterestExpenseDebt is listed after the real total, so its real $0 silently clobbered the
correct figure via ordinary last-processed-wins. Made fallback-only so it can never
overwrite a real value the standard interest_expense concepts already found, while still
filling the field for filers (like WMT) that report ONLY InterestExpenseDebt.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING, _REVENUE_FALLBACK_ONLY_FIELDS


class TestInterestExpenseDebtFallbackOnly:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "interest_expense", "data_unavailable", "reason"})
        loader._field_mapping = {
            "interest_expense": "interest_expense",
            "interest_expense_debt": "interest_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_expense_debt"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_fallback_only(self) -> None:
        assert _INCOME_FIELD_MAPPING["interest_expense_debt"] == "interest_expense"
        assert "interest_expense_debt" in _REVENUE_FALLBACK_ONLY_FIELDS

    def test_wmt_style_bare_concept_still_fills_empty_field(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "WMT", "fiscal_year": 2025, "interest_expense_debt": 2_614_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 2_614_000_000.0

    def test_ter_style_real_zero_debt_component_never_overwrites_real_total(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "TER",
            "fiscal_year": 2025,
            "interest_expense": 6_846_000.0,
            "interest_expense_debt": 0.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 6_846_000.0
