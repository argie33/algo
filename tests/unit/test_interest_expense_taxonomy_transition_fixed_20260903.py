"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, interest_expense_not_itemized investigation): two filers stopped tagging plain
"InterestExpense" and switched to different replacement concepts with different overwrite
semantics.

JKHY (Jack Henry & Associates, CIK 779152): "InterestExpenseOperating" is a pure taxonomy
relabeling - live-confirmed identical values in the one overlap year (FY2023, period
2022-07-01 to 2023-06-30: $15,073,000 under either concept), then continuing alone with
real values through FY2026 ($5,387,000). Safe as a plain (non-fallback) concept.

EPAC (Enerpac Tool Group, CIK 6955): "FinancingInterestExpense" is EPAC's real, continuous
primary interest-expense concept for its entire filing history (2008-2025) - live-confirmed
EPAC has zero facts under plain "InterestExpense" at all, and its rare "InterestAndDebtExpense"
entries are a genuinely different, smaller line item (FY2012: $16,830,000 vs. this
concept's $29,561,000 the same year), not a duplicate. Must be fallback-only so it never
overwrites InterestAndDebtExpense's rare real value.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING, _REVENUE_FALLBACK_ONLY_FIELDS


class TestInterestExpenseTaxonomyTransitionFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "interest_expense", "data_unavailable", "reason"})
        loader._field_mapping = {
            "interest_expense": "interest_expense",
            "interest_expense_operating": "interest_expense",
            "interest_and_debt_expense": "interest_expense",
            "financing_interest_expense": "interest_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_and_debt_expense", "financing_interest_expense"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_both_concepts(self) -> None:
        assert _INCOME_FIELD_MAPPING["interest_expense_operating"] == "interest_expense"
        assert _INCOME_FIELD_MAPPING["financing_interest_expense"] == "interest_expense"
        assert "financing_interest_expense" in _REVENUE_FALLBACK_ONLY_FIELDS

    def test_jkhy_style_relabeled_concept_recovered_when_standard_concept_absent(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "JKHY",
            "fiscal_year": 2025,
            "interest_expense_operating": 10_438_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 10_438_000.0

    def test_epac_style_fallback_fills_gap_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "EPAC",
            "fiscal_year": 2025,
            "financing_interest_expense": 9_911_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 9_911_000.0

    def test_epac_style_fallback_does_not_overwrite_real_interest_and_debt_expense(self) -> None:
        # A filer with a real InterestAndDebtExpense value must keep it over the
        # fallback-only FinancingInterestExpense concept.
        loader = self._make_loader()
        row = {
            "symbol": "EPAC",
            "fiscal_year": 2012,
            "interest_and_debt_expense": 16_830_000.0,
            "financing_interest_expense": 29_561_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 16_830_000.0
