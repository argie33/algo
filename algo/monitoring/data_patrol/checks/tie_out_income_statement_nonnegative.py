"""Non-negativity guard checks for income-statement magnitude fields.

Added 2026-09-15 (/goal "make sure we have the right tie outs for all we should" session).
tie_out_nonnegative_magnitudes.py already covers this exact check class (DQC_0015/US1-style
"structurally non-negative by GAAP definition" guard) for every annual_balance_sheet/
quarterly_balance_sheet magnitude field - explicitly scoped to "balance-sheet magnitude
fields" in its own docstring. Nothing covered the income-statement side: interest_expense,
depreciation_expense, amortization_expense, research_development_expense, and
goodwill_impairment_loss are all reported as a cost/expense magnitude, never a real negative
value, under GAAP. A repo-wide audit of every annual/quarterly_income_statement column found
zero tie-out coverage for these five - a real, previously-uncovered gap, not a stale one
(unlike the balance-sheet fields, none of these had EVER had a nonnegative guard).

Live-checked BEFORE writing this file, not assumed safe: annual_income_statement alone
already has 400 negative interest_expense rows, 51 negative depreciation_expense, 139
negative amortization_expense, 24 negative research_development_expense, and 46 negative
goodwill_impairment_loss - a real, sizeable backlog this check surfaces for the first time,
not a false-positive risk. WARN (not ERROR), same severity this check class always uses -
see tie_out_shared.py's `_check_nonnegative_cashflow_field`'s own docstring: a review-queue
finding, since a small fraction could still be a legitimate quirky filer convention (e.g. a
filer reporting a NET interest income/expense line under this concept) rather than every
instance being a confirmed sign-extraction bug.

Deliberately EXCLUDES net_income_attributable_to_common (routinely and legitimately negative
for a loss-making company - not a magnitude field, same exclusion reasoning
tie_out_nonnegative_magnitudes.py's own docstring gives for stockholders_equity/
retained_earnings) and income_tax_expense/pretax_income/operating_expenses (already have
their own dedicated relative-bound checks elsewhere in this package, e.g.
pretax_to_net_income, operating_income_upper_bound).

Reuses tie_out_shared.py's `_check_nonnegative_cashflow_field` helper unchanged - already
fully generic (table/field/check_name/quarterly params), same as every other check in this
class.
"""

from typing import Any


class TieOutIncomeStatementNonnegativeMixin:
    def check_interest_expense_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_income_statement",
            field="interest_expense",
            check_name="interest_expense_nonnegative",
            quarterly=False,
        )

    def check_quarterly_interest_expense_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_income_statement",
            field="interest_expense",
            check_name="quarterly_interest_expense_nonnegative",
            quarterly=True,
        )

    def check_depreciation_expense_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_income_statement",
            field="depreciation_expense",
            check_name="depreciation_expense_nonnegative",
            quarterly=False,
        )

    def check_quarterly_depreciation_expense_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_income_statement",
            field="depreciation_expense",
            check_name="quarterly_depreciation_expense_nonnegative",
            quarterly=True,
        )

    def check_amortization_expense_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_income_statement",
            field="amortization_expense",
            check_name="amortization_expense_nonnegative",
            quarterly=False,
        )

    def check_quarterly_amortization_expense_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_income_statement",
            field="amortization_expense",
            check_name="quarterly_amortization_expense_nonnegative",
            quarterly=True,
        )

    def check_research_development_expense_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_income_statement",
            field="research_development_expense",
            check_name="research_development_expense_nonnegative",
            quarterly=False,
        )

    def check_quarterly_research_development_expense_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_income_statement",
            field="research_development_expense",
            check_name="quarterly_research_development_expense_nonnegative",
            quarterly=True,
        )

    def check_goodwill_impairment_loss_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_income_statement",
            field="goodwill_impairment_loss",
            check_name="goodwill_impairment_loss_nonnegative",
            quarterly=False,
        )

    def check_quarterly_goodwill_impairment_loss_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_income_statement",
            field="goodwill_impairment_loss",
            check_name="quarterly_goodwill_impairment_loss_nonnegative",
            quarterly=True,
        )
