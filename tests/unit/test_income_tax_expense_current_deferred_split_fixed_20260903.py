"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, income_tax_expense investigation): CNS (Cohen & Steers) stopped tagging plain
"IncomeTaxExpenseBenefit" after FY2024 - live-confirmed via real SEC companyfacts JSON that
FY2025 instead splits the same total across "CurrentIncomeTaxExpenseBenefit" ($46,671,000) +
"DeferredIncomeTaxExpenseBenefit" ($561,000) = $47,232,000, consistent with FY2024's real
total ($46,749,000). Both are completely standard ASC 740 tax-note concepts - current +
deferred tax provision sums to total tax expense by definition, not an approximation (unlike
the previously investigated-and-rejected pretax_income = net_income + tax reconstruction,
which only matched ~75% of the time universe-wide).
"""

import inspect

from utils.external import sec_statements
from utils.external.sec_statements import _fill_income_tax_expense_from_current_deferred_split


class TestIncomeTaxExpenseCurrentDeferredSplitFixed:
    def test_concepts_are_actually_fetched(self) -> None:
        # A fill function alone is not enough - get_income_statement()'s concept list must
        # actually request both concepts from SEC or the fallback never has data to sum.
        source = inspect.getsource(sec_statements.get_income_statement)
        assert "CurrentIncomeTaxExpenseBenefit" in source
        assert "DeferredIncomeTaxExpenseBenefit" in source

    def test_cns_style_split_summed_when_plain_concept_absent(self) -> None:
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
        assert "current_income_tax_expense_benefit" not in rows[0]
        assert "deferred_income_tax_expense_benefit" not in rows[0]

    def test_split_never_overwrites_a_real_income_tax_expense_value(self) -> None:
        # FIXED 2026-09-18 (goal session, xbrl_yfinance_line_item_report income_tax_expense
        # remediation): this test originally checked "income_tax_expense" - a DB column
        # name that doesn't exist yet at this point in the pipeline (this function runs
        # INSIDE get_income_statement(), before transform() remaps the raw
        # "income_tax_expense_benefit" concept key onto that column) - so the guard it was
        # meant to exercise was actually a no-op in production (live-confirmed via ALLT:
        # a real, nonzero IncomeTaxExpenseBenefit=$1,895,000 got silently overwritten to
        # $391,000 by this exact fallback). Uses the REAL raw key now.
        rows = [
            {
                "symbol": "CNS",
                "fiscal_year": 2024,
                "income_tax_expense_benefit": 46_749_000.0,
                "current_income_tax_expense_benefit": 1.0,
                "deferred_income_tax_expense_benefit": 1.0,
            }
        ]

        _fill_income_tax_expense_from_current_deferred_split(rows)

        assert rows[0]["income_tax_expense_benefit"] == 46_749_000.0
        assert "income_tax_expense" not in rows[0]

    def test_real_filed_zero_still_falls_through_to_the_split_sum(self) -> None:
        # MAIN (Main Street Capital, a BDC) real-world case: the top-level
        # "IncomeTaxExpenseBenefit" tag is a real, filed $0 (doesn't capture a taxable
        # subsidiary's own tax provision), and yfinance agrees with the current+deferred
        # sum instead ($30,633,000) - a real filed zero must NOT be treated the same as a
        # real nonzero value here.
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

    def test_requires_both_halves_present_unlike_debt_current_zero_default(self) -> None:
        # Unlike LongTermDebtCurrent (defaults to 0 when absent), a missing current-or-
        # deferred component here means the filer genuinely hasn't reported its total tax
        # provision this way - don't guess a partial sum.
        rows = [
            {
                "symbol": "XYZ",
                "fiscal_year": 2025,
                "current_income_tax_expense_benefit": 5_000_000.0,
            }
        ]

        _fill_income_tax_expense_from_current_deferred_split(rows)

        assert rows[0].get("income_tax_expense") is None
        assert "current_income_tax_expense_benefit" not in rows[0]
