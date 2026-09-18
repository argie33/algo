"""Regression test for the 2026-09-18 fix (goal session: xbrl_yfinance_line_item_report
income_tax_expense remediation): ALLT (Allot Ltd) tags a real, current, nonzero
"IncomeTaxExpenseBenefit"=$1,895,000 FY2022 (exact yfinance match) while ALSO tagging
CurrentIncomeTaxExpenseBenefit=$391,000 + DeferredIncomeTaxExpenseBenefit=$0.
_fill_income_tax_expense_from_current_deferred_split()'s guard checked
`row.get("income_tax_expense")` - a DB column name that doesn't exist yet at this point in
the pipeline (this function runs INSIDE get_income_statement(), before transform() remaps
the raw "income_tax_expense_benefit" concept key onto that column) - so the guard was
always None regardless of whether the real value was present, and this fallback
unconditionally clobbered $1,895,000 down to $391,000.
"""

from utils.external.sec_income_statement_fallbacks import (
    _fill_income_tax_expense_from_current_deferred_split,
)


class TestIncomeTaxExpenseCurrentDeferredSplitWrongKeyGuardFixed:
    def test_allt_style_real_nonzero_top_level_tag_wins(self) -> None:
        rows = [
            {
                "symbol": "ALLT",
                "fiscal_year": 2022,
                "income_tax_expense_benefit": 1_895_000.0,
                "current_income_tax_expense_benefit": 391_000.0,
                "deferred_income_tax_expense_benefit": 0.0,
            }
        ]

        _fill_income_tax_expense_from_current_deferred_split(rows)

        assert rows[0]["income_tax_expense_benefit"] == 1_895_000.0
        assert "income_tax_expense" not in rows[0]

    def test_main_style_real_filed_zero_falls_through_to_split_sum(self) -> None:
        rows = [
            {
                "symbol": "MAIN",
                "fiscal_year": 2024,
                "income_tax_expense_benefit": 0.0,
                "current_income_tax_expense_benefit": 30_000_000.0,
                "deferred_income_tax_expense_benefit": 633_000.0,
            }
        ]

        _fill_income_tax_expense_from_current_deferred_split(rows)

        assert rows[0]["income_tax_expense"] == 30_633_000.0

    def test_no_top_level_tag_at_all_falls_through_to_split_sum(self) -> None:
        rows = [
            {
                "symbol": "CNS",
                "fiscal_year": 2025,
                "current_income_tax_expense_benefit": 46_671_000.0,
                "deferred_income_tax_expense_benefit": 561_000.0,
            }
        ]

        _fill_income_tax_expense_from_current_deferred_split(rows)

        assert rows[0]["income_tax_expense"] == 47_232_000.0
