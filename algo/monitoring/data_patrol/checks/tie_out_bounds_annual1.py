"""TieOutChecker mixin, extracted from tie_out.py (file-size ratchet split, pure
extraction - no behavior change). Methods moved verbatim; mixed into TieOutChecker
via multiple inheritance in tie_out.py - every `self.` call here (self.results,
self.config, and any shared private helper from TieOutSharedMixin) resolves
normally through the instance regardless of which mixin file defines it.
"""

import logging
from typing import TYPE_CHECKING, Any

from ..base import CheckResult
from ..config import ERROR, WARN
from .tie_out_shared import (
    _ACCOUNTS_PAYABLE_TOLERANCE_PCT,
    _ACCOUNTS_RECEIVABLE_TOLERANCE_PCT,
    _CASH_TOLERANCE_PCT,
    _CURRENT_VS_TOTAL_TOLERANCE_PCT,
    _GOODWILL_TOLERANCE_PCT,
    _INVENTORY_TOLERANCE_PCT,
    _LONG_TERM_DEBT_TOLERANCE_PCT,
    _MAX_REPORTED_PER_CHECK,
    _OPERATING_INCOME_BOUND_TOLERANCE_FLOOR,
    _OPERATING_INCOME_BOUND_TOLERANCE_PCT,
    _PPE_NET_TOLERANCE_PCT,
    _QUICK_RATIO_TOLERANCE,
    _SHARE_COUNT_TOLERANCE_PCT,
)

logger = logging.getLogger(__name__)


class TieOutBoundsAnnual1Mixin:
    if TYPE_CHECKING:
        results: list[CheckResult]

        def log(
            self,
            check_name: str,
            severity: str,
            target: str,
            message: str,
            details: dict[str, Any] | None = None,
        ) -> CheckResult: ...

    def check_quick_ratio_le_current_ratio(self, cur: Any) -> None:
        """quick_ratio <= current_ratio (both from quality_metrics, one row per symbol).

        ADDED 2026-09-07 (goal: "make sure we have all the right tie outs" sweep, CI tie-out
        coverage audit's #2 recommendation). Live feasibility check against the local DB
        (2026-09-07, 4,448 rows) found zero violations currently - this is a pure regression
        guard against loaders/helpers/vqg_quality.py's current_ratio/quick_ratio computation
        drifting apart (e.g. a future change computing one from a different current_assets/
        current_liabilities snapshot than the other), not an active bug hunt. quality_metrics
        is keyed one row per symbol (no fiscal_year/as_of_date column), unlike the annual_*
        tables the other checks in this file query.
        """
        try:
            cur.execute(
                """
                SELECT symbol, current_ratio, quick_ratio
                FROM quality_metrics
                WHERE data_unavailable = FALSE
                  AND current_ratio IS NOT NULL
                  AND quick_ratio IS NOT NULL
                """
            )
            flagged = []
            for row in cur.fetchall():
                current_ratio, quick_ratio = (
                    float(row["current_ratio"]),
                    float(row["quick_ratio"]),
                )
                residual = quick_ratio - current_ratio
                if residual > _QUICK_RATIO_TOLERANCE:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "current_ratio": current_ratio,
                            "quick_ratio": quick_ratio,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quick_ratio_le_current_ratio",
                    WARN,
                    "quality_metrics",
                    f"{len(flagged)} symbol(s) have quick_ratio > current_ratio "
                    f"(structurally impossible - quick_ratio excludes inventory)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quick_ratio_le_current_ratio failed: {e}", exc_info=True)
            self.log(
                "quick_ratio_le_current_ratio",
                ERROR,
                "quality_metrics",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_current_assets_le_total_assets(self, cur: Any) -> None:
        """current_assets <= total_assets (both from annual_balance_sheet, same row).

        ADDED 2026-09-07 (goal: stock_scores factor/composite sanity audit + tie-out CI
        completeness review). Strict structural inequality: current_assets is a GAAP subtotal
        of total_assets (cash/receivables/inventory/other short-term items), never the whole
        balance sheet or more - a violation is a strong signal of a swapped-concept or
        wrong-magnitude extraction bug (e.g. current_assets picking up a total-assets-scale
        fact), not filer-side measurement noise, same reasoning as
        check_diluted_ge_basic_shares. Live feasibility check against the local DB (2026-09-07)
        found this genuinely rare - 1 violation out of 4,180 comparable symbol/years (SSL).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.total_assets, b.current_assets
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_assets IS NOT NULL
                  AND b.current_assets IS NOT NULL
                  AND b.total_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_assets, current_assets = (
                    float(row["total_assets"]),
                    float(row["current_assets"]),
                )
                residual = current_assets - total_assets
                tolerance = abs(total_assets) * _CURRENT_VS_TOTAL_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "total_assets": total_assets,
                            "current_assets": current_assets,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "current_assets_le_total_assets",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail current_assets <= total_assets beyond "
                    f"{_CURRENT_VS_TOTAL_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] current_assets_le_total_assets failed: {e}", exc_info=True)
            self.log(
                "current_assets_le_total_assets",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_current_liabilities_le_total_liabilities(self, cur: Any) -> None:
        """current_liabilities <= total_liabilities (both from annual_balance_sheet, same row).

        ADDED 2026-09-07, mirrors check_current_assets_le_total_assets above exactly but for
        the liabilities side of the same subtotal-vs-total structural relationship. Live
        feasibility check against the local DB (2026-09-07) found 8 violations out of 4,171
        comparable symbol/years - still far below the noise floor of the loosest checks in
        this file (cashflow_reconciliation, retained_earnings_rollforward).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.total_liabilities, b.current_liabilities
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.current_liabilities IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_liabilities, current_liabilities = (
                    float(row["total_liabilities"]),
                    float(row["current_liabilities"]),
                )
                residual = current_liabilities - total_liabilities
                tolerance = abs(total_liabilities) * _CURRENT_VS_TOTAL_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "total_liabilities": total_liabilities,
                            "current_liabilities": current_liabilities,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "current_liabilities_le_total_liabilities",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail current_liabilities <= total_liabilities "
                    f"beyond {_CURRENT_VS_TOTAL_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] current_liabilities_le_total_liabilities failed: {e}", exc_info=True)
            self.log(
                "current_liabilities_le_total_liabilities",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_long_term_debt_le_total_liabilities(self, cur: Any) -> None:
        """long_term_debt <= total_liabilities (both from annual_balance_sheet, same row).

        ADDED 2026-09-07 (goal: stock_scores factor/composite sanity audit + tie-out CI
        completeness review), same subset/category structural inequality as
        check_current_assets_le_total_assets/check_current_liabilities_le_total_liabilities
        above - long_term_debt is one liability line item, never the whole liability side. See
        _LONG_TERM_DEBT_TOLERANCE_PCT's own comment for why this compares long_term_debt alone
        (not summed with short_term_debt) and for the live-feasibility numbers (64/4,244).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.total_liabilities, b.long_term_debt
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.long_term_debt IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_liabilities, long_term_debt = (
                    float(row["total_liabilities"]),
                    float(row["long_term_debt"]),
                )
                residual = long_term_debt - total_liabilities
                tolerance = abs(total_liabilities) * _LONG_TERM_DEBT_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "total_liabilities": total_liabilities,
                            "long_term_debt": long_term_debt,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "long_term_debt_le_total_liabilities",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail long_term_debt <= total_liabilities beyond "
                    f"{_LONG_TERM_DEBT_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] long_term_debt_le_total_liabilities failed: {e}", exc_info=True)
            self.log(
                "long_term_debt_le_total_liabilities",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_operating_income_upper_bound(self, cur: Any) -> None:
        """operating_income <= gross_profit - operating_expenses (+ tolerance).

        ADDED 2026-09-07 (goal: stock_scores factor/composite sanity audit + "make sure we
        have all the right tie outs" sweep). See this file's module docstring and
        _OPERATING_INCOME_BOUND_TOLERANCE_PCT for why this is a one-directional bound, not a
        two-sided identity like gross_profit_identity: operating_expenses (SG&A, added this
        same session) is only one of several real expense lines between gross_profit and
        operating_income (R&D, D&A-when-broken-out, restructuring, impairments), so
        operating_income legitimately runs BELOW gross_profit - operating_expenses for most
        filers that report any of those other lines - only flags the mathematically-impossible
        direction (operating_income exceeding what SG&A alone would allow), which indicates a
        real extraction bug (e.g. a swapped/duplicated concept), not a missing-line-item gap.

        operating_expenses was only wired up this same session and is not backfilled yet - this
        will find ~0 non-NULL rows to evaluate until the next reload, same as
        check_cashflow_activities_sum_to_net_change's first run when net_change_cash was new.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.gross_profit, i.operating_expenses, i.operating_income
                FROM annual_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.gross_profit IS NOT NULL
                  AND i.operating_expenses IS NOT NULL
                  AND i.operating_income IS NOT NULL
                  AND i.gross_profit != 0
                ORDER BY i.symbol, i.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                gross_profit, operating_expenses, operating_income = (
                    float(row["gross_profit"]),
                    float(row["operating_expenses"]),
                    float(row["operating_income"]),
                )
                implied_ceiling = gross_profit - operating_expenses
                residual = operating_income - implied_ceiling
                tolerance = max(
                    _OPERATING_INCOME_BOUND_TOLERANCE_FLOOR,
                    abs(gross_profit) * _OPERATING_INCOME_BOUND_TOLERANCE_PCT,
                )
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "gross_profit": gross_profit,
                            "operating_expenses": operating_expenses,
                            "operating_income": operating_income,
                            "implied_ceiling": implied_ceiling,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "operating_income_upper_bound",
                    WARN,
                    "annual_income_statement",
                    f"{len(flagged)} symbol(s) fail operating_income <= gross_profit - "
                    f"operating_expenses beyond max(${_OPERATING_INCOME_BOUND_TOLERANCE_FLOOR:,.0f}, "
                    f"{_OPERATING_INCOME_BOUND_TOLERANCE_PCT:.0%} of gross_profit)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] operating_income_upper_bound failed: {e}", exc_info=True)
            self.log(
                "operating_income_upper_bound",
                ERROR,
                "annual_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_goodwill_le_total_assets(self, cur: Any) -> None:
        """goodwill <= total_assets (both from annual_balance_sheet, same row).

        ADDED 2026-09-07 (goal: stock_scores factor/composite sanity audit + tie-out CI
        completeness review), same subset/category structural inequality as
        check_current_assets_le_total_assets/check_long_term_debt_le_total_liabilities above -
        goodwill is one asset line item, never the whole asset side. See
        _GOODWILL_TOLERANCE_PCT's own comment for the live-feasibility numbers (9/3,355) and
        confirmation that this catches live bugs, not stale/pending-reload data.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.total_assets, b.goodwill
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_assets IS NOT NULL
                  AND b.goodwill IS NOT NULL
                  AND b.total_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_assets, goodwill = (
                    float(row["total_assets"]),
                    float(row["goodwill"]),
                )
                residual = goodwill - total_assets
                tolerance = abs(total_assets) * _GOODWILL_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "total_assets": total_assets,
                            "goodwill": goodwill,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "goodwill_le_total_assets",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail goodwill <= total_assets beyond "
                    f"{_GOODWILL_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] goodwill_le_total_assets failed: {e}", exc_info=True)
            self.log(
                "goodwill_le_total_assets",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_accounts_payable_le_current_liabilities(self, cur: Any) -> None:
        """accounts_payable <= current_liabilities (both from annual_balance_sheet, same row).

        ADDED 2026-09-07 (goal: stock_scores factor/composite sanity audit + tie-out CI
        completeness review). See _ACCOUNTS_PAYABLE_TOLERANCE_PCT's own comment for the
        live-feasibility numbers (3/2,827) and confirmation these are stale-pending-reload
        rows, not a live extraction bug.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.current_liabilities, b.accounts_payable
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_liabilities IS NOT NULL
                  AND b.accounts_payable IS NOT NULL
                  AND b.current_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                current_liabilities, accounts_payable = (
                    float(row["current_liabilities"]),
                    float(row["accounts_payable"]),
                )
                residual = accounts_payable - current_liabilities
                tolerance = abs(current_liabilities) * _ACCOUNTS_PAYABLE_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "current_liabilities": current_liabilities,
                            "accounts_payable": accounts_payable,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "accounts_payable_le_current_liabilities",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail accounts_payable <= current_liabilities "
                    f"beyond {_ACCOUNTS_PAYABLE_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(
                f"[TieOutChecker] accounts_payable_le_current_liabilities failed: {e}",
                exc_info=True,
            )
            self.log(
                "accounts_payable_le_current_liabilities",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_cash_le_current_assets(self, cur: Any) -> None:
        """cash_and_equivalents <= current_assets (both from annual_balance_sheet, same row).

        ADDED 2026-09-07 (goal: stock_scores factor/composite sanity audit + tie-out CI
        completeness review). See _CASH_TOLERANCE_PCT's own comment for the live-feasibility
        numbers (26/4,207) and confirmation the non-despac outliers are stale-pending-reload
        rows, not a live extraction bug.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.current_assets, b.cash_and_equivalents
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_assets IS NOT NULL
                  AND b.cash_and_equivalents IS NOT NULL
                  AND b.current_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                current_assets, cash_and_equivalents = (
                    float(row["current_assets"]),
                    float(row["cash_and_equivalents"]),
                )
                residual = cash_and_equivalents - current_assets
                tolerance = abs(current_assets) * _CASH_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "current_assets": current_assets,
                            "cash_and_equivalents": cash_and_equivalents,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "cash_le_current_assets",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail cash_and_equivalents <= current_assets "
                    f"beyond {_CASH_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] cash_le_current_assets failed: {e}", exc_info=True)
            self.log(
                "cash_le_current_assets",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_inventory_le_current_assets(self, cur: Any) -> None:
        """inventory <= current_assets (both from annual_balance_sheet, same row).

        ADDED 2026-09-07 (goal: stock_scores factor/composite sanity audit + tie-out CI
        completeness review). See _INVENTORY_TOLERANCE_PCT's own comment for the
        live-feasibility numbers (14/2,754) and the PARA ticker-recycling root cause found
        for the top hit.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.current_assets, b.inventory
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_assets IS NOT NULL
                  AND b.inventory IS NOT NULL
                  AND b.current_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                current_assets, inventory = (
                    float(row["current_assets"]),
                    float(row["inventory"]),
                )
                residual = inventory - current_assets
                tolerance = abs(current_assets) * _INVENTORY_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "current_assets": current_assets,
                            "inventory": inventory,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "inventory_le_current_assets",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail inventory <= current_assets "
                    f"beyond {_INVENTORY_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] inventory_le_current_assets failed: {e}", exc_info=True)
            self.log(
                "inventory_le_current_assets",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_accounts_receivable_le_current_assets(self, cur: Any) -> None:
        """accounts_receivable <= current_assets (both from annual_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3, goal: "figure out all the tie-out checks we should have
        and build all of them"). Same subset/category structural inequality as
        inventory_le_current_assets/cash_le_current_assets above - AR is one current-asset
        line item, never the whole current-asset side. See
        _ACCOUNTS_RECEIVABLE_TOLERANCE_PCT's own comment for the live-feasibility numbers
        (5/3,786).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.current_assets, b.accounts_receivable
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_assets IS NOT NULL
                  AND b.accounts_receivable IS NOT NULL
                  AND b.current_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                current_assets, accounts_receivable = (
                    float(row["current_assets"]),
                    float(row["accounts_receivable"]),
                )
                residual = accounts_receivable - current_assets
                tolerance = abs(current_assets) * _ACCOUNTS_RECEIVABLE_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "current_assets": current_assets,
                            "accounts_receivable": accounts_receivable,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "accounts_receivable_le_current_assets",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail accounts_receivable <= current_assets "
                    f"beyond {_ACCOUNTS_RECEIVABLE_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] accounts_receivable_le_current_assets failed: {e}", exc_info=True)
            self.log(
                "accounts_receivable_le_current_assets",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_ppe_net_le_total_assets(self, cur: Any) -> None:
        """ppe_net <= total_assets (both from annual_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Same subset/category structural inequality as
        goodwill_le_total_assets above - net PP&E is one asset line item, never the whole
        asset side. See _PPE_NET_TOLERANCE_PCT's own comment for the live-feasibility
        numbers (4/4,757).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.total_assets, b.ppe_net
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_assets IS NOT NULL
                  AND b.ppe_net IS NOT NULL
                  AND b.total_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_assets, ppe_net = (
                    float(row["total_assets"]),
                    float(row["ppe_net"]),
                )
                residual = ppe_net - total_assets
                tolerance = abs(total_assets) * _PPE_NET_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "total_assets": total_assets,
                            "ppe_net": ppe_net,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "ppe_net_le_total_assets",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail ppe_net <= total_assets beyond {_PPE_NET_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] ppe_net_le_total_assets failed: {e}", exc_info=True)
            self.log(
                "ppe_net_le_total_assets",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_diluted_ge_basic_shares(self, cur: Any) -> None:
        """shares_outstanding_diluted >= shares_outstanding_basic.

        ADDED 2026-09-07 (goal: "make sure we have all the right tie outs" sweep, follow-up to
        the CI tie-out coverage audit that flagged this as missing). Structural GAAP inequality,
        not a measurement identity: dilutive securities (options/RSUs/converts) can only ever
        add to the diluted count via the treasury-stock/if-converted method, never subtract from
        it - a filer with zero dilutive securities reports diluted == basic, never diluted <
        basic. A violation here is a strong signal of a swapped-column or wrong-concept-priority
        bug in the extraction chain (the exact bug class this whole checker exists to catch),
        not filer-side measurement noise - hence the much tighter tolerance than every other
        check in this file.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.shares_outstanding_basic, i.shares_outstanding_diluted
                FROM annual_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.shares_outstanding_basic IS NOT NULL
                  AND i.shares_outstanding_diluted IS NOT NULL
                  AND i.shares_outstanding_basic > 0
                ORDER BY i.symbol, i.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                basic_shares, diluted_shares = (
                    float(row["shares_outstanding_basic"]),
                    float(row["shares_outstanding_diluted"]),
                )
                residual = basic_shares - diluted_shares
                tolerance = basic_shares * _SHARE_COUNT_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "shares_outstanding_basic": basic_shares,
                            "shares_outstanding_diluted": diluted_shares,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "diluted_ge_basic_shares",
                    WARN,
                    "annual_income_statement",
                    f"{len(flagged)} symbol(s) fail shares_outstanding_diluted >= "
                    f"shares_outstanding_basic beyond {_SHARE_COUNT_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] diluted_ge_basic_shares failed: {e}", exc_info=True)
            self.log(
                "diluted_ge_basic_shares",
                ERROR,
                "annual_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )
