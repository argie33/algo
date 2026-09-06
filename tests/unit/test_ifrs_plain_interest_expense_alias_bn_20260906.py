"""Regression test for the 2026-09-06 fix (goal session: "SEC/XBRL missing data" sweep,
interest_expense_not_itemized investigation): Brookfield Corporation (BN, CIK 0001001085)
tags the plain ifrs-full:"InterestExpense" concept directly for FY2021/FY2022 (live-confirmed
real, large, growing values: $7.604B FY2021, $10.702B FY2022) - previously unmapped, leaving
interest_expense (and interest_coverage) NULL despite real data being on file.

Deliberately does NOT map the narrower sibling "InterestExpenseOnBorrowings": live-checked on
the SAME BN filing, it's only $527M-$742M/year (2022-2025) - 15x smaller than BN's own plain
InterestExpense for the same fiscal years, proving it's a narrow sub-component (e.g. parent-level
corporate borrowings only), not BN's real total consolidated interest expense. No independent
value exists to validate it against, so it stays unmapped (same discipline as the still-rejected
ARW InterestIncomeExpenseNet candidate).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from utils.external.sec_statements import _INCOME_IFRS_ALIASES


class TestIfrsPlainInterestExpenseAliasFallback:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "interest_expense", "data_unavailable", "reason"})
        loader._field_mapping = {
            "finance_costs": "interest_expense",
            "interest_expense": "interest_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_alias_is_registered_for_ifrs_full_namespace(self) -> None:
        aliases = dict(_INCOME_IFRS_ALIASES)
        assert aliases["InterestExpense"] == "interest_expense"
        # The narrower, unvalidated sub-component sibling must stay unmapped.
        assert "InterestExpenseOnBorrowings" not in aliases

    def test_bn_style_interest_expense_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "BN", "fiscal_year": 2022, "interest_expense": 10_702_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 10_702_000_000.0

    def test_narrower_finance_costs_still_wins_when_it_is_the_only_source_present(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "ASR", "fiscal_year": 2024, "finance_costs": 826_700_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 826_700_000.0
