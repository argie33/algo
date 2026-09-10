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
    _CASH_TOLERANCE_PCT,
    _DILUTED_LE_BASIC_EPS_TOLERANCE_FLOOR,
    _DILUTED_LE_BASIC_EPS_TOLERANCE_PCT,
    _GOODWILL_TOLERANCE_PCT,
    _MAX_REPORTED_PER_CHECK,
    _OPERATING_INCOME_BOUND_TOLERANCE_FLOOR,
    _OPERATING_INCOME_BOUND_TOLERANCE_PCT,
    _SHARE_COUNT_TOLERANCE_PCT,
)

logger = logging.getLogger(__name__)


class TieOutBoundsQuarterly2MiscMixin:
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

        def _check_nonnegative_cashflow_field(
            self, cur: Any, *, table: str, field: str, check_name: str, quarterly: bool
        ) -> None: ...

        def _check_shares_outstanding_dei_plausible_scale(
            self, cur: Any, *, table: str, check_name: str, quarterly: bool
        ) -> None: ...

    def check_quarterly_operating_income_upper_bound(self, cur: Any) -> None:
        """operating_income <= gross_profit - operating_expenses (+ tolerance)
        (quarterly_income_statement).

        ADDED 2026-09-07 (Round 3). Quarterly port of check_operating_income_upper_bound -
        reuses the annual tolerance unchanged. operating_expenses is barely backfilled on
        quarterly data yet (live-verified only 59 comparable rows, 2 violations) - same
        "not backfilled yet" situation the annual check's own docstring already notes for
        itself; will find more rows to evaluate once a reload runs.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.fiscal_quarter,
                    i.gross_profit, i.operating_expenses, i.operating_income
                FROM quarterly_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.gross_profit IS NOT NULL
                  AND i.operating_expenses IS NOT NULL
                  AND i.operating_income IS NOT NULL
                  AND i.gross_profit != 0
                ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC
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
                            "fiscal_quarter": row["fiscal_quarter"],
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
                    "quarterly_operating_income_upper_bound",
                    WARN,
                    "quarterly_income_statement",
                    f"{len(flagged)} symbol/quarter(s) fail operating_income <= gross_profit "
                    f"- operating_expenses beyond max(${_OPERATING_INCOME_BOUND_TOLERANCE_FLOOR:,.0f}, "
                    f"{_OPERATING_INCOME_BOUND_TOLERANCE_PCT:.0%} of gross_profit)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_operating_income_upper_bound failed: {e}", exc_info=True)
            self.log(
                "quarterly_operating_income_upper_bound",
                ERROR,
                "quarterly_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_goodwill_le_total_assets(self, cur: Any) -> None:
        """goodwill <= total_assets (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of check_goodwill_le_total_assets -
        reuses the annual _GOODWILL_TOLERANCE_PCT unchanged (live-verified 7/3,433).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter, b.total_assets, b.goodwill
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_assets IS NOT NULL
                  AND b.goodwill IS NOT NULL
                  AND b.total_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
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
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_assets": total_assets,
                            "goodwill": goodwill,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_goodwill_le_total_assets",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail goodwill <= total_assets beyond "
                    f"{_GOODWILL_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_goodwill_le_total_assets failed: {e}", exc_info=True)
            self.log(
                "quarterly_goodwill_le_total_assets",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_accounts_payable_le_current_liabilities(self, cur: Any) -> None:
        """accounts_payable <= current_liabilities (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_accounts_payable_le_current_liabilities - reuses the annual
        _ACCOUNTS_PAYABLE_TOLERANCE_PCT unchanged (live-verified 2/3,073).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter,
                    b.current_liabilities, b.accounts_payable
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_liabilities IS NOT NULL
                  AND b.accounts_payable IS NOT NULL
                  AND b.current_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
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
                            "fiscal_quarter": row["fiscal_quarter"],
                            "current_liabilities": current_liabilities,
                            "accounts_payable": accounts_payable,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_accounts_payable_le_current_liabilities",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail accounts_payable <= "
                    f"current_liabilities beyond {_ACCOUNTS_PAYABLE_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(
                f"[TieOutChecker] quarterly_accounts_payable_le_current_liabilities failed: {e}",
                exc_info=True,
            )
            self.log(
                "quarterly_accounts_payable_le_current_liabilities",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_cash_le_current_assets(self, cur: Any) -> None:
        """cash_and_equivalents <= current_assets (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of check_cash_le_current_assets - reuses
        the annual _CASH_TOLERANCE_PCT unchanged (live-verified 8/4,569).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter, b.current_assets, b.cash_and_equivalents
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_assets IS NOT NULL
                  AND b.cash_and_equivalents IS NOT NULL
                  AND b.current_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
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
                            "fiscal_quarter": row["fiscal_quarter"],
                            "current_assets": current_assets,
                            "cash_and_equivalents": cash_and_equivalents,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_cash_le_current_assets",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail cash_and_equivalents <= "
                    f"current_assets beyond {_CASH_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_cash_le_current_assets failed: {e}", exc_info=True)
            self.log(
                "quarterly_cash_le_current_assets",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_stock_scores_bounds(self, cur: Any) -> None:
        """composite_score/quality_score/growth_score/value_score/risk_score/momentum_score
        must all fall within [0, 100] (stock_scores).

        ADDED 2026-09-08 (goal: "check the factor/composite scores make sense" + "make sure
        we have all the right tie outs" sweep). Every pillar and the composite are built as
        cross-sectional percentile ranks (0-100 by construction, see GOVERNANCE.md's
        BASE_PILLAR_WEIGHTS), so a value outside that range can only mean a percentile-rank
        bug, a unit/scale mixup, or a stale non-percentile raw value leaking through - never a
        legitimate business fact the way e.g. a negative growth rate can be. Live-checked
        2026-09-08: 0 violations across all 5,448 rows (min composite_score 0.00, max 99.62) -
        this is a pure regression guard for a currently-clean invariant, not a fix for an
        existing violation.
        """
        try:
            cur.execute(
                """
                SELECT symbol, date, composite_score, quality_score, growth_score,
                       value_score, risk_score, momentum_score
                FROM stock_scores
                WHERE date = (SELECT MAX(date) FROM stock_scores)
                """
            )
            score_cols = (
                "composite_score",
                "quality_score",
                "growth_score",
                "value_score",
                "risk_score",
                "momentum_score",
            )
            flagged = []
            for row in cur.fetchall():
                for col in score_cols:
                    value = row[col]
                    if value is not None and not (0 <= float(value) <= 100):
                        flagged.append(
                            {"symbol": row["symbol"], "date": str(row["date"]), "field": col, "value": float(value)}
                        )
            if flagged:
                flagged.sort(key=lambda r: abs(r["value"] - 50), reverse=True)
                self.log(
                    "stock_scores_bounds",
                    WARN,
                    "stock_scores",
                    f"{len(flagged)} symbol/field pair(s) have a pillar or composite score outside [0, 100]",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] stock_scores_bounds failed: {e}", exc_info=True)
            self.log(
                "stock_scores_bounds",
                ERROR,
                "stock_scores",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_stock_based_compensation_nonnegative(self, cur: Any) -> None:
        """stock_based_compensation >= 0 (annual_cash_flow).

        ADDED 2026-09-07 (Round 5, goal: "run all the tie-outs" buildout). Regression guard
        for the sign-flip fix landed the same session - see _MIN_PLAUSIBLE_SHARES_OUTSTANDING's
        neighboring comment block for the live AAMI evidence (AllocatedShareBasedCompensation
        Expense tagged -$23.2M/-$47.7M for FY2024/2025) this fix and guard were built for.
        """
        self._check_nonnegative_cashflow_field(
            cur,
            table="annual_cash_flow",
            field="stock_based_compensation",
            check_name="stock_based_compensation_nonnegative",
            quarterly=False,
        )

    def check_quarterly_stock_based_compensation_nonnegative(self, cur: Any) -> None:
        """stock_based_compensation >= 0 (quarterly_cash_flow). Quarterly mirror of
        check_stock_based_compensation_nonnegative."""
        self._check_nonnegative_cashflow_field(
            cur,
            table="quarterly_cash_flow",
            field="stock_based_compensation",
            check_name="quarterly_stock_based_compensation_nonnegative",
            quarterly=True,
        )

    def check_common_stock_repurchased_nonnegative(self, cur: Any) -> None:
        """common_stock_repurchased >= 0 (annual_cash_flow).

        ADDED 2026-09-07 (Round 5, goal: "run all the tie-outs" buildout). Regression guard
        for the sign-flip fix landed the same session - live-confirmed via JCTC's own filed
        10-K/10-K-A XBRL: PaymentsForRepurchaseOfCommonStock tagged -$3,075,559/-$7,188 for
        FY2012/2013.
        """
        self._check_nonnegative_cashflow_field(
            cur,
            table="annual_cash_flow",
            field="common_stock_repurchased",
            check_name="common_stock_repurchased_nonnegative",
            quarterly=False,
        )

    def check_quarterly_common_stock_repurchased_nonnegative(self, cur: Any) -> None:
        """common_stock_repurchased >= 0 (quarterly_cash_flow). Quarterly mirror of
        check_common_stock_repurchased_nonnegative."""
        self._check_nonnegative_cashflow_field(
            cur,
            table="quarterly_cash_flow",
            field="common_stock_repurchased",
            check_name="quarterly_common_stock_repurchased_nonnegative",
            quarterly=True,
        )

    def check_shares_outstanding_dei_plausible_scale(self, cur: Any) -> None:
        """shares_outstanding_dei within a plausible real-share-count range
        (annual_income_statement).

        ADDED 2026-09-07 (Round 5, goal: "run all the tie-outs" buildout). Regression guard
        for the loader-side fix landed the same session - see
        _reject_implausible_shares_outstanding()'s docstring in load_financial_statements.py
        for the live EEFT evidence (dei:EntityCommonStockSharesOutstanding tagged
        52,752,851,000,000,000 for FY2020 vs a real ~52.2-52.3M per the filer's own FY2020
        10-Qs).
        """
        self._check_shares_outstanding_dei_plausible_scale(
            cur,
            table="annual_income_statement",
            check_name="shares_outstanding_dei_plausible_scale",
            quarterly=False,
        )

    def check_quarterly_shares_outstanding_dei_plausible_scale(self, cur: Any) -> None:
        """shares_outstanding_dei within a plausible real-share-count range
        (quarterly_income_statement). Quarterly mirror of
        check_shares_outstanding_dei_plausible_scale."""
        self._check_shares_outstanding_dei_plausible_scale(
            cur,
            table="quarterly_income_statement",
            check_name="quarterly_shares_outstanding_dei_plausible_scale",
            quarterly=True,
        )

    def check_quarterly_diluted_ge_basic_shares(self, cur: Any) -> None:
        """shares_outstanding_diluted >= shares_outstanding_basic, quarterly_income_statement.

        ADDED 2026-09-07 (same sweep as the two checks above). Mirrors
        check_diluted_ge_basic_shares - same strict structural GAAP inequality, same tight
        tolerance, just read from the quarterly table.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.fiscal_quarter,
                    i.shares_outstanding_basic, i.shares_outstanding_diluted
                FROM quarterly_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.shares_outstanding_basic IS NOT NULL
                  AND i.shares_outstanding_diluted IS NOT NULL
                  AND i.shares_outstanding_basic > 0
                ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC
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
                            "fiscal_quarter": row["fiscal_quarter"],
                            "shares_outstanding_basic": basic_shares,
                            "shares_outstanding_diluted": diluted_shares,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_diluted_ge_basic_shares",
                    WARN,
                    "quarterly_income_statement",
                    f"{len(flagged)} symbol(s) fail shares_outstanding_diluted >= "
                    f"shares_outstanding_basic beyond {_SHARE_COUNT_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_diluted_ge_basic_shares failed: {e}", exc_info=True)
            self.log(
                "quarterly_diluted_ge_basic_shares",
                ERROR,
                "quarterly_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_diluted_eps_le_basic_eps(self, cur: Any) -> None:
        """diluted_eps <= earnings_per_share (quarterly_income_statement, same row).

        ADDED 2026-09-07 (Round 3). ASC 260's antidilution rule (see
        _DILUTED_LE_BASIC_EPS_TOLERANCE_PCT's own comment) applied to quarterly_income_
        statement - no annual counterpart check exists yet, this is quarterly-only
        (live-verified 21/4,824).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.fiscal_quarter, i.diluted_eps, i.earnings_per_share
                FROM quarterly_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.diluted_eps IS NOT NULL
                  AND i.earnings_per_share IS NOT NULL
                ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                diluted_eps, basic_eps = (
                    float(row["diluted_eps"]),
                    float(row["earnings_per_share"]),
                )
                residual = diluted_eps - basic_eps
                tolerance = max(
                    _DILUTED_LE_BASIC_EPS_TOLERANCE_FLOOR, abs(basic_eps) * _DILUTED_LE_BASIC_EPS_TOLERANCE_PCT
                )
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "diluted_eps": diluted_eps,
                            "earnings_per_share": basic_eps,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_diluted_eps_le_basic_eps",
                    WARN,
                    "quarterly_income_statement",
                    f"{len(flagged)} symbol/quarter(s) fail diluted_eps <= earnings_per_share "
                    f"(ASC 260 antidilution) beyond max(${_DILUTED_LE_BASIC_EPS_TOLERANCE_FLOOR:.2f}, "
                    f"{_DILUTED_LE_BASIC_EPS_TOLERANCE_PCT:.0%} of basic eps)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_diluted_eps_le_basic_eps failed: {e}", exc_info=True)
            self.log(
                "quarterly_diluted_eps_le_basic_eps",
                ERROR,
                "quarterly_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_diluted_eps_le_basic_eps(self, cur: Any) -> None:
        """diluted_eps <= earnings_per_share (both from annual_income_statement, same row).

        ADDED 2026-09-07 (Round 3). Real GAAP rule (ASC 260 antidilution), not a heuristic -
        see _DILUTED_LE_BASIC_EPS_TOLERANCE_PCT's own comment for why a single signed
        inequality correctly handles both profit and loss periods, and for the live-
        feasibility numbers (13/2,964).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.diluted_eps, i.earnings_per_share
                FROM annual_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.diluted_eps IS NOT NULL
                  AND i.earnings_per_share IS NOT NULL
                ORDER BY i.symbol, i.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                diluted_eps, basic_eps = (
                    float(row["diluted_eps"]),
                    float(row["earnings_per_share"]),
                )
                residual = diluted_eps - basic_eps
                tolerance = max(
                    _DILUTED_LE_BASIC_EPS_TOLERANCE_FLOOR, abs(basic_eps) * _DILUTED_LE_BASIC_EPS_TOLERANCE_PCT
                )
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "diluted_eps": diluted_eps,
                            "earnings_per_share": basic_eps,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "diluted_eps_le_basic_eps",
                    WARN,
                    "annual_income_statement",
                    f"{len(flagged)} symbol(s) fail diluted_eps <= earnings_per_share "
                    f"(ASC 260 antidilution) beyond max(${_DILUTED_LE_BASIC_EPS_TOLERANCE_FLOOR:.2f}, "
                    f"{_DILUTED_LE_BASIC_EPS_TOLERANCE_PCT:.0%} of basic eps)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] diluted_eps_le_basic_eps failed: {e}", exc_info=True)
            self.log(
                "diluted_eps_le_basic_eps",
                ERROR,
                "annual_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )
