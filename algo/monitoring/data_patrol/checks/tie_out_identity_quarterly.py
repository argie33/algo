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
    _FREE_CASH_FLOW_TOLERANCE_FLOOR,
    _FREE_CASH_FLOW_TOLERANCE_PCT,
    _GROSS_PROFIT_TOLERANCE_FLOOR,
    _GROSS_PROFIT_TOLERANCE_PCT,
    _MAX_REPORTED_PER_CHECK,
    _NET_CHANGE_CASH_TOLERANCE_FLOOR,
    _NET_CHANGE_CASH_TOLERANCE_PCT,
    _QUARTERLY_EPS_TOLERANCE_FLOOR,
    _QUARTERLY_EPS_TOLERANCE_PCT,
    _QUARTERLY_NET_CHANGE_CASH_TOLERANCE_FLOOR,
    _QUARTERLY_NET_CHANGE_CASH_TOLERANCE_PCT,
    _QUARTERLY_PRETAX_NET_INCOME_TOLERANCE_FLOOR,
    _QUARTERLY_PRETAX_NET_INCOME_TOLERANCE_PCT,
)

logger = logging.getLogger(__name__)


class TieOutIdentityQuarterlyMixin:
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

    def check_free_cash_flow_identity(self, cur: Any) -> None:
        """operating_cash_flow - capex ~= free_cash_flow.

        ADDED 2026-09-07 (goal: "make sure we have all the right tie outs" sweep, CI tie-out
        coverage audit's #1 recommendation). Unlike gross_profit_identity/pretax_to_net_income
        (which cross independently-tagged XBRL facts), free_cash_flow is DERIVED at load time
        from operating_cash_flow and capex by load_financial_statements.py - so this check is
        really a regression guard against that derivation getting broken (e.g. a future capex
        fallback-concept change writing to the wrong column), not a hunt for XBRL extraction
        bugs. A real violation here indicates the load-time computation itself is wrong for
        that symbol/year, not a tagging/magnitude problem upstream.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (symbol)
                    symbol, fiscal_year, operating_cash_flow, capex, free_cash_flow
                FROM annual_cash_flow
                WHERE data_unavailable = FALSE
                  AND operating_cash_flow IS NOT NULL
                  AND capex IS NOT NULL
                  AND free_cash_flow IS NOT NULL
                ORDER BY symbol, fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                ocf, capex, fcf = (
                    float(row["operating_cash_flow"]),
                    float(row["capex"]),
                    float(row["free_cash_flow"]),
                )
                implied_fcf = ocf - capex
                residual = implied_fcf - fcf
                tolerance = max(_FREE_CASH_FLOW_TOLERANCE_FLOOR, abs(fcf) * _FREE_CASH_FLOW_TOLERANCE_PCT)
                if abs(residual) > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "operating_cash_flow": ocf,
                            "capex": capex,
                            "free_cash_flow": fcf,
                            "implied_free_cash_flow": implied_fcf,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: abs(r["residual"]), reverse=True)
                self.log(
                    "free_cash_flow_identity",
                    WARN,
                    "annual_cash_flow",
                    f"{len(flagged)} symbol(s) fail operating_cash_flow - capex ~= free_cash_flow "
                    f"beyond max(${_FREE_CASH_FLOW_TOLERANCE_FLOOR:,.0f}, "
                    f"{_FREE_CASH_FLOW_TOLERANCE_PCT:.0%} of free_cash_flow)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] free_cash_flow_identity failed: {e}", exc_info=True)
            self.log(
                "free_cash_flow_identity",
                ERROR,
                "annual_cash_flow",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_cashflow_activities_sum_to_net_change(self, cur: Any) -> None:
        """operating_cash_flow + investing_cash_flow + financing_cash_flow ~= net_change_cash.

        ADDED 2026-09-07 (goal: "SEC/XBRL missing data" + tie-out sweep). net_change_cash is a
        real, standard XBRL concept (SEC's "total change in cash for the period" line - see
        load_financial_statements.py's field_mapping comment for the live AMZN evidence) that was
        never fetched or mapped anywhere until this same session - a declared schema column with
        0/66,580 rows populated across its entire history. Once populated, this is a clean,
        self-contained identity: unlike check_cashflow_reconciliation (which cross-checks against
        a DIFFERENT statement's cash concept, one fiscal year apart, and can be thrown off by a
        genuine concept-definition mismatch between "cash_and_equivalents" and the cash-flow
        statement's own reconciliation figure - e.g. restricted cash treatment), this one only
        ever compares four numbers from the SAME cash-flow-statement row, so it isolates a real
        activities-sum extraction bug from that other check's cross-statement noise sources.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (symbol)
                    symbol, fiscal_year, operating_cash_flow, investing_cash_flow,
                    financing_cash_flow, net_change_cash
                FROM annual_cash_flow
                WHERE data_unavailable = FALSE
                  AND operating_cash_flow IS NOT NULL
                  AND investing_cash_flow IS NOT NULL
                  AND financing_cash_flow IS NOT NULL
                  AND net_change_cash IS NOT NULL
                ORDER BY symbol, fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                ocf, icf, fcf, net_change = (
                    float(row["operating_cash_flow"]),
                    float(row["investing_cash_flow"]),
                    float(row["financing_cash_flow"]),
                    float(row["net_change_cash"]),
                )
                implied_net_change = ocf + icf + fcf
                residual = implied_net_change - net_change
                tolerance = max(_NET_CHANGE_CASH_TOLERANCE_FLOOR, abs(net_change) * _NET_CHANGE_CASH_TOLERANCE_PCT)
                if abs(residual) > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "operating_cash_flow": ocf,
                            "investing_cash_flow": icf,
                            "financing_cash_flow": fcf,
                            "net_change_cash": net_change,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: abs(r["residual"]), reverse=True)
                self.log(
                    "cashflow_activities_sum_to_net_change",
                    WARN,
                    "annual_cash_flow",
                    f"{len(flagged)} symbol(s) fail OCF + ICF + FCF ~= net_change_cash beyond "
                    f"max(${_NET_CHANGE_CASH_TOLERANCE_FLOOR:,.0f}, "
                    f"{_NET_CHANGE_CASH_TOLERANCE_PCT:.0%} of net_change_cash)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] cashflow_activities_sum_to_net_change failed: {e}", exc_info=True)
            self.log(
                "cashflow_activities_sum_to_net_change",
                ERROR,
                "annual_cash_flow",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_gross_profit_identity(self, cur: Any) -> None:
        """revenue - cost_of_revenue ~= gross_profit, quarterly_income_statement.

        ADDED 2026-09-07 (goal: "make sure we have all the right tie outs in CI" sweep -
        every existing check in this file only ever reads annual_* tables; quarterly_income_
        statement/quarterly_balance_sheet/quarterly_cash_flow feed sec_valuations_checks.py's
        TTM/valuation metrics with zero tie-out coverage of their own). Mirrors
        check_gross_profit_identity exactly (same tolerance - this is a strict GAAP
        definitional identity regardless of period length) but reads the quarterly table.

        Dedup is DISTINCT ON (symbol) ORDER BY fiscal_year DESC, fiscal_quarter DESC - a
        simpler heuristic than migration 1256's period_end-based true-chronological-order fix
        for non-December-fiscal-year-end filers (see load_financial_statements.py's
        _QUARTERLY_INCOME_EXTRA comment). That precision matters for picking THE single most
        recent quarter; it doesn't matter here since this identity must hold for any given
        row regardless of which quarter is picked, so an occasional off-by-one-quarter
        selection doesn't affect this check's correctness, only which quarter's residual
        (if any) gets surfaced first.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.fiscal_quarter, i.revenue, i.cost_of_revenue, i.gross_profit
                FROM quarterly_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.revenue IS NOT NULL
                  AND i.cost_of_revenue IS NOT NULL
                  AND i.gross_profit IS NOT NULL
                  AND i.revenue != 0
                ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                revenue, cost_of_revenue, gross_profit = (
                    float(row["revenue"]),
                    float(row["cost_of_revenue"]),
                    float(row["gross_profit"]),
                )
                implied_gross_profit = revenue - cost_of_revenue
                residual = implied_gross_profit - gross_profit
                tolerance = max(_GROSS_PROFIT_TOLERANCE_FLOOR, abs(revenue) * _GROSS_PROFIT_TOLERANCE_PCT)
                if abs(residual) > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "revenue": revenue,
                            "cost_of_revenue": cost_of_revenue,
                            "gross_profit": gross_profit,
                            "implied_gross_profit": implied_gross_profit,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: abs(r["residual"]), reverse=True)
                self.log(
                    "quarterly_gross_profit_identity",
                    WARN,
                    "quarterly_income_statement",
                    f"{len(flagged)} symbol(s) fail revenue - cost_of_revenue ~= gross_profit "
                    f"beyond max(${_GROSS_PROFIT_TOLERANCE_FLOOR:,.0f}, "
                    f"{_GROSS_PROFIT_TOLERANCE_PCT:.0%} of revenue)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_gross_profit_identity failed: {e}", exc_info=True)
            self.log(
                "quarterly_gross_profit_identity",
                ERROR,
                "quarterly_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_free_cash_flow_identity(self, cur: Any) -> None:
        """operating_cash_flow - capex ~= free_cash_flow, quarterly_cash_flow.

        ADDED 2026-09-07 (same sweep as check_quarterly_gross_profit_identity above). Mirrors
        check_free_cash_flow_identity - free_cash_flow is derived at load time from
        operating_cash_flow/capex the same way for quarterly rows as annual, so this is a
        regression guard on that same derivation, not an XBRL-extraction-bug hunt.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (symbol)
                    symbol, fiscal_year, fiscal_quarter, operating_cash_flow, capex, free_cash_flow
                FROM quarterly_cash_flow
                WHERE data_unavailable = FALSE
                  AND operating_cash_flow IS NOT NULL
                  AND capex IS NOT NULL
                  AND free_cash_flow IS NOT NULL
                ORDER BY symbol, fiscal_year DESC, fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                ocf, capex, fcf = (
                    float(row["operating_cash_flow"]),
                    float(row["capex"]),
                    float(row["free_cash_flow"]),
                )
                implied_fcf = ocf - capex
                residual = implied_fcf - fcf
                tolerance = max(_FREE_CASH_FLOW_TOLERANCE_FLOOR, abs(fcf) * _FREE_CASH_FLOW_TOLERANCE_PCT)
                if abs(residual) > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "operating_cash_flow": ocf,
                            "capex": capex,
                            "free_cash_flow": fcf,
                            "implied_free_cash_flow": implied_fcf,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: abs(r["residual"]), reverse=True)
                self.log(
                    "quarterly_free_cash_flow_identity",
                    WARN,
                    "quarterly_cash_flow",
                    f"{len(flagged)} symbol(s) fail operating_cash_flow - capex ~= free_cash_flow "
                    f"beyond max(${_FREE_CASH_FLOW_TOLERANCE_FLOOR:,.0f}, "
                    f"{_FREE_CASH_FLOW_TOLERANCE_PCT:.0%} of free_cash_flow)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_free_cash_flow_identity failed: {e}", exc_info=True)
            self.log(
                "quarterly_free_cash_flow_identity",
                ERROR,
                "quarterly_cash_flow",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_eps_reconciliation(self, cur: Any) -> None:
        """diluted_eps * shares_outstanding_diluted ~= net_income (quarterly_income_statement).

        ADDED 2026-09-07 (Round 3). Quarterly port of check_eps_reconciliation - looser
        tolerance than the annual check (_QUARTERLY_EPS_TOLERANCE_PCT vs _EPS_TOLERANCE_PCT,
        see that constant's own comment for the live p50/p90 percentiles that justify it).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.fiscal_quarter,
                    i.net_income, i.diluted_eps, i.shares_outstanding_diluted
                FROM quarterly_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.net_income IS NOT NULL
                  AND i.diluted_eps IS NOT NULL
                  AND i.shares_outstanding_diluted IS NOT NULL
                  AND i.shares_outstanding_diluted != 0
                  AND i.net_income != 0
                ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                net_income, diluted_eps, diluted_shares = (
                    float(row["net_income"]),
                    float(row["diluted_eps"]),
                    float(row["shares_outstanding_diluted"]),
                )
                implied_net_income = diluted_eps * diluted_shares
                residual = implied_net_income - net_income
                tolerance = max(_QUARTERLY_EPS_TOLERANCE_FLOOR, abs(net_income) * _QUARTERLY_EPS_TOLERANCE_PCT)
                if abs(residual) > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "net_income": net_income,
                            "diluted_eps": diluted_eps,
                            "shares_outstanding_diluted": diluted_shares,
                            "implied_net_income": implied_net_income,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: abs(r["residual"]), reverse=True)
                self.log(
                    "quarterly_eps_reconciliation",
                    WARN,
                    "quarterly_income_statement",
                    f"{len(flagged)} symbol/quarter(s) fail diluted_eps * "
                    f"shares_outstanding_diluted ~= net_income beyond "
                    f"max(${_QUARTERLY_EPS_TOLERANCE_FLOOR:,.0f}, {_QUARTERLY_EPS_TOLERANCE_PCT:.0%} "
                    "of net_income)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_eps_reconciliation failed: {e}", exc_info=True)
            self.log(
                "quarterly_eps_reconciliation",
                ERROR,
                "quarterly_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_basic_eps_reconciliation(self, cur: Any) -> None:
        """earnings_per_share * shares_outstanding_basic ~= net_income (quarterly_income_statement).

        ADDED 2026-09-07 (Round 3). Quarterly port of check_basic_eps_reconciliation - same
        looser _QUARTERLY_EPS_TOLERANCE_PCT as check_quarterly_eps_reconciliation above.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.fiscal_quarter,
                    i.net_income, i.earnings_per_share, i.shares_outstanding_basic
                FROM quarterly_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.net_income IS NOT NULL
                  AND i.earnings_per_share IS NOT NULL
                  AND i.shares_outstanding_basic IS NOT NULL
                  AND i.shares_outstanding_basic != 0
                  AND i.net_income != 0
                ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                net_income, basic_eps, basic_shares = (
                    float(row["net_income"]),
                    float(row["earnings_per_share"]),
                    float(row["shares_outstanding_basic"]),
                )
                implied_net_income = basic_eps * basic_shares
                residual = implied_net_income - net_income
                tolerance = max(_QUARTERLY_EPS_TOLERANCE_FLOOR, abs(net_income) * _QUARTERLY_EPS_TOLERANCE_PCT)
                if abs(residual) > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "net_income": net_income,
                            "earnings_per_share": basic_eps,
                            "shares_outstanding_basic": basic_shares,
                            "implied_net_income": implied_net_income,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: abs(r["residual"]), reverse=True)
                self.log(
                    "quarterly_basic_eps_reconciliation",
                    WARN,
                    "quarterly_income_statement",
                    f"{len(flagged)} symbol/quarter(s) fail earnings_per_share * "
                    f"shares_outstanding_basic ~= net_income beyond "
                    f"max(${_QUARTERLY_EPS_TOLERANCE_FLOOR:,.0f}, {_QUARTERLY_EPS_TOLERANCE_PCT:.0%} "
                    "of net_income)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_basic_eps_reconciliation failed: {e}", exc_info=True)
            self.log(
                "quarterly_basic_eps_reconciliation",
                ERROR,
                "quarterly_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_pretax_to_net_income(self, cur: Any) -> None:
        """pretax_income - income_tax_expense ~= net_income (quarterly_income_statement).

        ADDED 2026-09-07 (Round 3). Quarterly port of check_pretax_to_net_income - looser
        tolerance than annual (_QUARTERLY_PRETAX_NET_INCOME_TOLERANCE_PCT, see that
        constant's own comment for the live p90 that justifies it - quarterly tax true-ups
        are noisier than a full fiscal year's tax provision).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.fiscal_quarter,
                    i.pretax_income, i.income_tax_expense, i.net_income
                FROM quarterly_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.pretax_income IS NOT NULL
                  AND i.income_tax_expense IS NOT NULL
                  AND i.net_income IS NOT NULL
                  AND i.net_income != 0
                ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                pretax_income, income_tax_expense, net_income = (
                    float(row["pretax_income"]),
                    float(row["income_tax_expense"]),
                    float(row["net_income"]),
                )
                implied_net_income = pretax_income - income_tax_expense
                residual = implied_net_income - net_income
                tolerance = max(
                    _QUARTERLY_PRETAX_NET_INCOME_TOLERANCE_FLOOR,
                    abs(net_income) * _QUARTERLY_PRETAX_NET_INCOME_TOLERANCE_PCT,
                )
                if abs(residual) > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "pretax_income": pretax_income,
                            "income_tax_expense": income_tax_expense,
                            "net_income": net_income,
                            "implied_net_income": implied_net_income,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: abs(r["residual"]), reverse=True)
                self.log(
                    "quarterly_pretax_to_net_income",
                    WARN,
                    "quarterly_income_statement",
                    f"{len(flagged)} symbol/quarter(s) fail pretax_income - "
                    f"income_tax_expense ~= net_income beyond "
                    f"max(${_QUARTERLY_PRETAX_NET_INCOME_TOLERANCE_FLOOR:,.0f}, "
                    f"{_QUARTERLY_PRETAX_NET_INCOME_TOLERANCE_PCT:.0%} of net_income)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_pretax_to_net_income failed: {e}", exc_info=True)
            self.log(
                "quarterly_pretax_to_net_income",
                ERROR,
                "quarterly_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_cashflow_activities_sum_to_net_change(self, cur: Any) -> None:
        """operating_cash_flow + investing_cash_flow + financing_cash_flow ~= net_change_cash
        (quarterly_cash_flow).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_cashflow_activities_sum_to_net_change - looser tolerance than annual
        (_QUARTERLY_NET_CHANGE_CASH_TOLERANCE_PCT, see that constant's own comment for the
        live percentiles that justify it).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (symbol)
                    symbol, fiscal_year, fiscal_quarter, operating_cash_flow,
                    investing_cash_flow, financing_cash_flow, net_change_cash
                FROM quarterly_cash_flow
                WHERE data_unavailable = FALSE
                  AND operating_cash_flow IS NOT NULL
                  AND investing_cash_flow IS NOT NULL
                  AND financing_cash_flow IS NOT NULL
                  AND net_change_cash IS NOT NULL
                ORDER BY symbol, fiscal_year DESC, fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                ocf, icf, fcf, net_change = (
                    float(row["operating_cash_flow"]),
                    float(row["investing_cash_flow"]),
                    float(row["financing_cash_flow"]),
                    float(row["net_change_cash"]),
                )
                implied_net_change = ocf + icf + fcf
                residual = implied_net_change - net_change
                tolerance = max(
                    _QUARTERLY_NET_CHANGE_CASH_TOLERANCE_FLOOR,
                    abs(net_change) * _QUARTERLY_NET_CHANGE_CASH_TOLERANCE_PCT,
                )
                if abs(residual) > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "operating_cash_flow": ocf,
                            "investing_cash_flow": icf,
                            "financing_cash_flow": fcf,
                            "net_change_cash": net_change,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: abs(r["residual"]), reverse=True)
                self.log(
                    "quarterly_cashflow_activities_sum_to_net_change",
                    WARN,
                    "quarterly_cash_flow",
                    f"{len(flagged)} symbol/quarter(s) fail OCF + ICF + FCF ~= "
                    f"net_change_cash beyond max(${_QUARTERLY_NET_CHANGE_CASH_TOLERANCE_FLOOR:,.0f}, "
                    f"{_QUARTERLY_NET_CHANGE_CASH_TOLERANCE_PCT:.0%} of net_change_cash)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_cashflow_activities_sum_to_net_change failed: {e}", exc_info=True)
            self.log(
                "quarterly_cashflow_activities_sum_to_net_change",
                ERROR,
                "quarterly_cash_flow",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_revenue_annual_duplicate(self, cur: Any) -> None:
        """quarterly_income_statement.revenue should not be IDENTICAL across all 4 quarters
        of a fiscal year AND equal to that year's annual_income_statement.revenue.

        ADDED 2026-09-08 (goal: "check the scores make sense" stock_scores/tie-out sweep,
        quarterly-sum-to-annual reconciliation gap). A live spot-check of quarterly-sum-vs-
        annual revenue reconciliation (no prior tie-out check covered this cross-table
        relationship at all) surfaced 51 latest-fiscal-year symbol/year pairs off by >5% -
        the overwhelming majority were legitimate (discontinued operations, restatements,
        FX), EXCEPT one exact, repeating, single-symbol signature: APA (Apache/APA
        Corporation, a real active S&P 500 energy major, not an obscure filer) has all 4
        quarterly_income_statement.revenue rows identically equal to that year's full annual
        total for FY2023/2024/2025 running (live-confirmed: $8.327B/$9.739B/$8.951B), i.e.
        the loader is stamping the ANNUAL duration fact onto all four quarters instead of
        real per-quarter figures - not a business fact, a duration-context extraction bug.
        This narrower "identical-across-all-4-quarters AND equals annual" signature is
        deliberately used instead of a generic sum-mismatch tolerance check: a same-quarter-
        as-annual match for a SINGLE quarter is common and legitimate for small/pre-revenue
        filers whose revenue is concentrated in one quarter (spot-checked separately, 160+
        such cases, all real), but four-for-four is only reachable by this duration-context
        bug. ROOT-CAUSED 2026-09-08: not a live bug - a fresh extraction call returns
        revenue=None for APA every quarter now, so the DB rows were stale, pre-dating the
        quarterly duration guards; corrected via targeted UPDATE reusing the identical
        2026-09-03 'quarterly_row_orphaned_annual_duplicate' reason (coverage_category_rules.py).

        REOPENED 2026-09-10 (goal session: data-quality triage): the 2026-09-08 fix did NOT
        hold - a live patrol run that same week re-found the identical duplicate for FY2025
        (all 4 quarters = $8.951B = the FY2025 annual figure), with fresh `updated_at`
        timestamps and `data_source='sec_audited'` (not a derived-field marker). Re-verified
        `get_income_statement(client, 'APA', period='quarterly')` TODAY still returns
        revenue=None for every quarter - so the 2026-09-08 conclusion ("not a live bug") is
        still true of the CURRENT extraction code path, yet the DB had the bad value anyway.
        That contradiction (raw extraction = None, but DB = duplicated annual value with a
        real-looking data_source/timestamp) was NOT resolved this session - re-applied the
        same DB-only correction as 2026-09-08 (safe, but not durable: a data patch, not a
        code fix) rather than guess at a code change without understanding the actual write
        path. APA's quarterly net_income for the same rows IS correctly distinct per quarter
        (not duplicated), which rules out "extraction is globally broken for APA" - whatever
        writes revenue=annual_total into all 4 quarterly rows is either concept-specific to
        revenue, or is not going through get_income_statement()/sec_income_statement.py at
        all. Needs a dedicated follow-up session with logging/tracing across a real loader
        run (not just the raw extraction call in isolation) to catch it in the act.
        """
        try:
            cur.execute(
                """
                WITH latest_fy AS (
                    SELECT symbol, MAX(fiscal_year) AS fiscal_year
                    FROM annual_income_statement
                    WHERE data_unavailable = FALSE AND revenue IS NOT NULL
                    GROUP BY symbol
                )
                SELECT q.symbol, q.fiscal_year, MIN(q.revenue) AS q_revenue, a.revenue AS a_revenue,
                       COUNT(*) AS n_quarters, COUNT(DISTINCT q.revenue) AS n_distinct
                FROM quarterly_income_statement q
                JOIN annual_income_statement a ON a.symbol = q.symbol AND a.fiscal_year = q.fiscal_year
                    AND a.data_unavailable = FALSE
                JOIN latest_fy l ON l.symbol = q.symbol AND l.fiscal_year = q.fiscal_year
                JOIN stock_symbols s ON s.symbol = q.symbol AND s.active = true
                WHERE q.data_unavailable = FALSE AND q.revenue IS NOT NULL AND q.revenue != 0
                GROUP BY q.symbol, q.fiscal_year, a.revenue
                HAVING COUNT(*) = 4 AND COUNT(DISTINCT q.revenue) = 1
                """
            )
            flagged = []
            for row in cur.fetchall():
                q_revenue, a_revenue = float(row["q_revenue"]), float(row["a_revenue"])
                if abs(q_revenue - a_revenue) < 1.0:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "quarterly_revenue": q_revenue,
                            "annual_revenue": a_revenue,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["symbol"])
                self.log(
                    "quarterly_revenue_annual_duplicate",
                    WARN,
                    "quarterly_income_statement",
                    f"{len(flagged)} symbol(s) have all 4 quarters of revenue identically "
                    f"equal to the full annual revenue (duration-context extraction bug, "
                    f"not a real quarterly figure)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_revenue_annual_duplicate failed: {e}", exc_info=True)
            self.log(
                "quarterly_revenue_annual_duplicate",
                ERROR,
                "quarterly_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )
