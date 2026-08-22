"""Regression test for the foreign IFRS-bank revenue gap found live 2026-08-22
(goal session: "Insufficient history"/revenue-gap audit).

WF (Woori Financial Group, a major Korean bank holding company, $55B market cap)
live-confirmed via real companyfacts JSON: reports neither "Revenue" nor
"RevenuesNetOfInterestExpense" for fiscal years 2015-2024, despite real, growing
NetIncomeLoss on file for every one of those years (e.g. FY2022 $2.67B) - revenue was
NULL for 10 straight years, wrongly presenting downstream as "insufficient_history" in
growth_metrics despite WF having 16+ years of real SEC data on file. Real gross
interest income/expense line under ifrs-full:InterestRevenueExpense has full USD-unit
coverage for the same years (e.g. FY2022 $6.9B - a plausible bank revenue figure, well
above net_income). Mapping it (last in the revenue-concept list, so it only wins when
nothing else is present) recovers the real figure without risking a clobber for any
filer that reports a standard revenue concept.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from utils.external.sec_statements import _INCOME_IFRS_ALIASES


class TestIfrsBankInterestRevenueExpenseFallback:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "revenues_net_of_interest_expense": "revenue",
            "interest_revenue_expense": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_revenue_expense"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_alias_is_registered_for_ifrs_full_namespace(self) -> None:
        aliases = dict(_INCOME_IFRS_ALIASES)
        assert aliases["InterestRevenueExpense"] == "interest_revenue_expense"

    def test_interest_revenue_expense_populates_revenue_when_nothing_else_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "WF",
            "fiscal_year": 2022,
            "interest_revenue_expense": 6_901_170_486.29,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 6_901_170_486.29

    def test_interest_revenue_expense_does_not_overwrite_real_total_revenue(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMEBANK",
            "fiscal_year": 2022,
            "revenues": 10_000_000_000.0,
            "interest_revenue_expense": 6_901_170_486.29,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 10_000_000_000.0
