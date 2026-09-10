"""Non-negativity guard checks for balance-sheet magnitude fields (Round 7, goal session
2026-09-10: "full XBRL best-practices" review). Same check class as the real-world XBRL US
Data Quality Committee's DQC_0015/US1 "negative values" rule - a set of GAAP concepts that
are structurally impossible to be negative on the face of the balance sheet (an asset, a
liability magnitude) regardless of what the filer's own numbers say, so a negative value here
is always an extraction/sign bug, never a legitimate business outcome.

This is a genuinely different check class from tie_out.py's existing `X <= Y` bound checks
(e.g. ppe_net_le_total_assets, short_term_debt_le_current_liabilities): a relative bound check
still passes if BOTH sides are wrong-signed (ppe_net=-50 and total_assets=-100 still satisfies
ppe_net <= total_assets). Nothing before this file verified these balance-sheet magnitude
fields are non-negative in isolation - only 4 narrower cash-flow-statement fields had this
guard (check_stock_based_compensation_nonnegative/check_common_stock_repurchased_nonnegative
in tie_out_bounds_quarterly2_misc.py, Round 5). Reuses that same file's
TieOutSharedMixin._check_nonnegative_cashflow_field helper unchanged - it's already fully
generic (table/field/check_name/quarterly params, no cashflow-specific logic inside) despite
its name.

Deliberately EXCLUDES net-position/equity fields (stockholders_equity, retained_earnings,
noncontrolling_interest, temporary_equity) - those can be, and routinely are, legitimately
negative (distressed-company negative equity, accumulated deficit). Only fields non-negative
BY DEFINITION regardless of the filer's financial health are included - same selection
principle the real DQC rule uses.
"""

from typing import Any


class TieOutNonnegativeMagnitudesMixin:
    def check_total_assets_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="total_assets",
            check_name="total_assets_nonnegative",
            quarterly=False,
        )

    def check_quarterly_total_assets_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="total_assets",
            check_name="quarterly_total_assets_nonnegative",
            quarterly=True,
        )

    def check_current_assets_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="current_assets",
            check_name="current_assets_nonnegative",
            quarterly=False,
        )

    def check_quarterly_current_assets_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="current_assets",
            check_name="quarterly_current_assets_nonnegative",
            quarterly=True,
        )

    def check_total_liabilities_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="total_liabilities",
            check_name="total_liabilities_nonnegative",
            quarterly=False,
        )

    def check_quarterly_total_liabilities_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="total_liabilities",
            check_name="quarterly_total_liabilities_nonnegative",
            quarterly=True,
        )

    def check_current_liabilities_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="current_liabilities",
            check_name="current_liabilities_nonnegative",
            quarterly=False,
        )

    def check_quarterly_current_liabilities_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="current_liabilities",
            check_name="quarterly_current_liabilities_nonnegative",
            quarterly=True,
        )

    def check_inventory_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="inventory",
            check_name="inventory_nonnegative",
            quarterly=False,
        )

    def check_quarterly_inventory_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="inventory",
            check_name="quarterly_inventory_nonnegative",
            quarterly=True,
        )

    def check_cash_and_equivalents_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="cash_and_equivalents",
            check_name="cash_and_equivalents_nonnegative",
            quarterly=False,
        )

    def check_quarterly_cash_and_equivalents_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="cash_and_equivalents",
            check_name="quarterly_cash_and_equivalents_nonnegative",
            quarterly=True,
        )

    def check_accounts_receivable_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="accounts_receivable",
            check_name="accounts_receivable_nonnegative",
            quarterly=False,
        )

    def check_quarterly_accounts_receivable_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="accounts_receivable",
            check_name="quarterly_accounts_receivable_nonnegative",
            quarterly=True,
        )

    def check_ppe_net_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="ppe_net",
            check_name="ppe_net_nonnegative",
            quarterly=False,
        )

    def check_quarterly_ppe_net_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="ppe_net",
            check_name="quarterly_ppe_net_nonnegative",
            quarterly=True,
        )

    def check_goodwill_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="goodwill",
            check_name="goodwill_nonnegative",
            quarterly=False,
        )

    def check_quarterly_goodwill_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="goodwill",
            check_name="quarterly_goodwill_nonnegative",
            quarterly=True,
        )

    def check_long_term_debt_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="long_term_debt",
            check_name="long_term_debt_nonnegative",
            quarterly=False,
        )

    def check_quarterly_long_term_debt_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="long_term_debt",
            check_name="quarterly_long_term_debt_nonnegative",
            quarterly=True,
        )

    def check_short_term_debt_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="short_term_debt",
            check_name="short_term_debt_nonnegative",
            quarterly=False,
        )

    def check_quarterly_short_term_debt_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="short_term_debt",
            check_name="quarterly_short_term_debt_nonnegative",
            quarterly=True,
        )

    def check_operating_lease_liability_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="operating_lease_liability",
            check_name="operating_lease_liability_nonnegative",
            quarterly=False,
        )

    def check_quarterly_operating_lease_liability_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="operating_lease_liability",
            check_name="quarterly_operating_lease_liability_nonnegative",
            quarterly=True,
        )

    def check_finance_lease_liability_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="finance_lease_liability",
            check_name="finance_lease_liability_nonnegative",
            quarterly=False,
        )

    def check_quarterly_finance_lease_liability_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="finance_lease_liability",
            check_name="quarterly_finance_lease_liability_nonnegative",
            quarterly=True,
        )

    def check_accounts_payable_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="accounts_payable",
            check_name="accounts_payable_nonnegative",
            quarterly=False,
        )

    def check_quarterly_accounts_payable_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="accounts_payable",
            check_name="quarterly_accounts_payable_nonnegative",
            quarterly=True,
        )

    def check_cash_and_restricted_cash_combined_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="annual_balance_sheet",
            field="cash_and_restricted_cash_combined",
            check_name="cash_and_restricted_cash_combined_nonnegative",
            quarterly=False,
        )

    def check_quarterly_cash_and_restricted_cash_combined_nonnegative(self, cur: Any) -> None:
        self._check_nonnegative_cashflow_field(  # type: ignore[attr-defined]
            cur,
            table="quarterly_balance_sheet",
            field="cash_and_restricted_cash_combined",
            check_name="quarterly_cash_and_restricted_cash_combined_nonnegative",
            quarterly=True,
        )
