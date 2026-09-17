"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep, second
follow-up pass): TITN (Titan Machinery) tags BOTH "FinancingInterestExpense" AND
"InterestExpenseOther" as genuinely distinct, additive interest-expense line items every
fiscal year - live-confirmed via real SEC companyfacts JSON, FY2026:
$24,109,000 + $18,974,000 = $43,083,000, exactly matching the yfinance-flagged value.

_aggregate_concepts has no summing mechanism (both keep their own distinct snake_case
keys), so the collision happens in transform(): field_mapping maps both to db_field
"interest_expense", and the ordinary last-listed-wins rule would otherwise silently
discard whichever processed first - understating interest_expense by the other line's
amount. Same pattern as the existing payments_to_acquire_oil_and_gas_property/
payments_to_explore_and_develop_oil_and_gas_properties capex sum.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING


class TestTitnInterestExpenseOtherDualConceptSum:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "interest_expense", "data_unavailable", "reason"})
        loader._field_mapping = {
            "interest_and_debt_expense": "interest_expense",
            "financing_interest_expense": "interest_expense",
            "interest_expense_other": "interest_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_and_debt_expense", "financing_interest_expense"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wired(self) -> None:
        assert _INCOME_FIELD_MAPPING["interest_expense_other"] == "interest_expense"

    def test_titn_style_dual_concepts_summed_not_overwritten(self) -> None:
        loader = self._make_loader()
        # Dict-insertion order matches TITN's real concept-list order: interest_and_debt_
        # expense (real $0, fallback-only) processed first, then financing_interest_
        # expense (real, nonzero, fallback-only), then interest_expense_other (plain,
        # triggers the sum). The zero-first-write guard must let financing_interest_
        # expense through despite the earlier real $0, or the sum below would silently
        # be short by $24,109,000.
        row = {
            "symbol": "TITN",
            "fiscal_year": 2026,
            "interest_and_debt_expense": 0.0,
            "financing_interest_expense": 24_109_000.0,
            "interest_expense_other": 18_974_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 43_083_000.0

    def test_solo_interest_expense_other_still_fills_empty_field(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "SOMECORP", "fiscal_year": 2025, "interest_expense_other": 5_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 5_000.0
