"""Regression test for the 2026-08-18 interest_expense fallback concepts.

Live-confirmed via real SEC companyfacts JSON that TXN (Texas Instruments, FY2025 $543M)
and BA (Boeing, FY2025 $2,771M) tag their real income-statement interest expense only
under "InterestAndDebtExpense" - neither has any fact under "InterestExpense",
"InterestExpenseNonoperating", or "InterestExpenseDebt". NEE (NextEra Energy) has none of
those four either, only the cash-flow-statement supplemental disclosure "InterestPaidNet"
(FY2025 $3,501M) - a cash-paid, not accrued-expense, figure, so it's the lowest-priority
fallback.

Both added as fallback-only fields: live-confirmed TRV reports BOTH a real "InterestExpense"
($425M FY2025) AND "InterestPaidNet" ($393M FY2025, a different, less precise cash-paid
figure) for the same fiscal year, so a plain always-overwrite mapping would have silently
downgraded TRV's real interest_expense on every filer that reports both.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _REVENUE_FALLBACK_ONLY_FIELDS
from utils.external.sec_statements import _to_snake


class TestInterestExpenseFallbackConceptMappings:
    def test_fallback_concepts_map_to_interest_expense_and_are_fallback_only(self) -> None:
        for concept in ("InterestAndDebtExpense", "InterestPaidNet"):
            target_key = _to_snake(concept)
            assert target_key in _REVENUE_FALLBACK_ONLY_FIELDS


class TestInterestExpenseFallbackNotOverwritingRealInterestExpense:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "interest_expense", "data_unavailable", "reason"})
        loader._field_mapping = {
            "interest_expense": "interest_expense",
            "interest_expense_nonoperating": "interest_expense",
            "interest_expense_debt": "interest_expense",
            "interest_and_debt_expense": "interest_expense",
            "interest_paid_net": "interest_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _REVENUE_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_real_interest_expense_not_overwritten_by_interest_paid_net(self) -> None:
        # TRV-style filer: reports both a real InterestExpense and the less-precise
        # cash-basis InterestPaidNet for the same fiscal year - the real one must win.
        loader = self._make_loader()
        row = {
            "symbol": "TRV",
            "fiscal_year": 2025,
            "interest_expense": 425_000_000.0,
            "interest_paid_net": 393_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 425_000_000.0

    def test_interest_and_debt_expense_fallback_populates_when_standard_concept_absent(self) -> None:
        # TXN/BA-style filer: never tags InterestExpense/InterestExpenseNonoperating/
        # InterestExpenseDebt at all, only InterestAndDebtExpense.
        loader = self._make_loader()
        row = {
            "symbol": "TXN",
            "fiscal_year": 2025,
            "interest_and_debt_expense": 543_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 543_000_000.0

    def test_interest_paid_net_fallback_populates_when_no_other_concept_present(self) -> None:
        # NEE-style filer: no InterestExpense-family or InterestAndDebtExpense concept at
        # all, only the cash-flow-statement InterestPaidNet.
        loader = self._make_loader()
        row = {
            "symbol": "NEE",
            "fiscal_year": 2025,
            "interest_paid_net": 3_501_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 3_501_000_000.0
