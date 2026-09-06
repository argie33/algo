#!/usr/bin/env python3
"""Cross-statement tie-out checks - balance sheet identity and cash flow reconciliation.

Added 2026-09-06 (goal session: "should we track more XBRL data" review). Every field in
annual_balance_sheet/annual_cash_flow is picked independently by loaders/helpers/sec_base.py's
concept-priority/magnitude-resolution chain - nothing in the pipeline cross-checks that a
symbol/year's picked values are internally consistent with each other. Every real bug the
2026-09 SEC/XBRL campaign found by hand (BBVA/HSBC revenue magnitude collision, ORLY revenue
clobbered by an interest-income fact, Berkshire's split-entity debt, etc.) was a case where
some extracted value was wrong in a way that would have failed a basic accounting identity.
This is the same read-only diagnostic logic as scripts/audit_statement_tie_outs.py, wired into
the DataPatrol framework so a real violation reaches the existing notify() alert pipeline
(DataPatrol.run(), same as every other checker) instead of only being visible to whoever
happens to run the standalone script manually.

Deliberately WARN, not ERROR/CRIT: these checks are new and their false-positive rate isn't
yet fully characterized in production (e.g. multinational filers' cash flow always shows FX
noise this schema has no concept to net out) - see the cash flow check's bank-exclusion note
below for one already-known false-positive class. Escalate to ERROR once a period of
production runs shows the flagged set is consistently real bugs, not noise.

Deliberately does NOT write data_unavailable or any DB row - same as every other data_patrol
checker, this only ever reports; it never changes what scoring treats as usable data. That is
a separate, deliberate policy decision (see coverage_category_rules.py) not made here.

Latest-real-fiscal-year dedup (added 2026-09-06, same session): first production run against
the live DB flagged 8,430 balance-sheet and 7,049 cash-flow symbol/years by scanning full
history. That's the same "every historical row" overcounting bug class scripts/
audit_unavailable_reasons.py and lambda/api/routes/scores.py's coverage endpoint both had to
fix (see audit_unavailable_reasons.py's 2026-09-02 comment) - a stale FY2015 XBRL extraction
quirk that's already been superseded by a clean FY2020+ history re-flags every year forever,
which is noise, not signal: nothing downstream (scoring, position sizing) ever reads a non-
latest fiscal year, so a tie-out failure only on an old year is not an active data-integrity
risk. Both checks below now use `DISTINCT ON (symbol) ORDER BY fiscal_year DESC` to check only
each symbol's latest real (non-data_unavailable, values-present) row, matching that same
convention. Full-history detail is not lost - it's still queryable directly, just not what
reaches the WARN-severity alert.
"""

import logging
from typing import Any

from ..base import BaseCheck, CheckResult
from ..config import WARN

logger = logging.getLogger(__name__)

_BALANCE_SHEET_TOLERANCE_PCT = 0.01  # 1% of total_assets - fixed contract, not configurable
_CASHFLOW_TOLERANCE_PCT = 0.10  # 10% of |ending cash| - no FX-effect concept tracked in this schema
_CASHFLOW_TOLERANCE_FLOOR = 1_000_000.0  # never flag a sub-$1M residual (rounding/immateriality)
# 15% of |net_income|, not the tighter 10% used for cash flow: diluted_eps * diluted_shares
# vs. net_income legitimately diverges for preferred dividends, discontinued operations, and
# noncontrolling-interest allocations - none of which this schema tracks as separate columns -
# on top of per-share rounding to 2 decimals compounding across large share counts.
_EPS_TOLERANCE_PCT = 0.15
_EPS_TOLERANCE_FLOOR = 500_000.0  # never flag a sub-$500K residual (rounding/immateriality)
_MAX_REPORTED_PER_CHECK = 20  # cap alert payload size - full detail still in the DB for follow-up

# Depository institutions never tag a cash flow statement whose "cash_and_equivalents" concept
# means what it means for an industrial filer - their real cash position sits mostly in
# interest-earning deposits/securities the balance-sheet field this schema tracks doesn't
# capture. Same SIC-code set as sec_base.py's _get_depository_institution_symbols (kept in
# sync with that file's own comment for the rationale) - live-confirmed via this checker's
# first production run: JPM/BAC/MUFG/KT/SKM all showed 9-13 digit "residuals" that are just
# this measurement mismatch, not a real reconciliation failure.
_DEPOSITORY_INSTITUTION_SIC_CODES = (6020, 6021, 6022, 6029, 6035, 6036, 6712)


class TieOutChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_balance_sheet_identity(cur)
        self.check_cashflow_reconciliation(cur)
        self.check_eps_reconciliation(cur)
        return self.results

    def check_balance_sheet_identity(self, cur: Any) -> None:
        """total_assets == total_liabilities + stockholders_equity.

        NOTE: load_financial_statements.py derives total_liabilities = total_assets -
        stockholders_equity whenever a filer never tags "Liabilities" directly - those rows
        tie out by construction (0 residual) and are harmlessly uninformative here, not a
        false pass of a check that was never really performed for them.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.total_assets, b.total_liabilities, b.stockholders_equity
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_assets IS NOT NULL
                  AND b.total_liabilities IS NOT NULL
                  AND b.stockholders_equity IS NOT NULL
                  AND b.total_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                assets, liabilities, equity = (
                    float(row["total_assets"]),
                    float(row["total_liabilities"]),
                    float(row["stockholders_equity"]),
                )
                residual = assets - (liabilities + equity)
                relative_error = abs(residual) / abs(assets)
                if relative_error > _BALANCE_SHEET_TOLERANCE_PCT:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "total_assets": assets,
                            "total_liabilities": liabilities,
                            "stockholders_equity": equity,
                            "residual": residual,
                            "relative_error_pct": round(relative_error * 100, 2),
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["relative_error_pct"], reverse=True)
                self.log(
                    "balance_sheet_identity",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol/year(s) fail total_assets == total_liabilities + "
                    f"stockholders_equity beyond {_BALANCE_SHEET_TOLERANCE_PCT:.0%} tolerance",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] balance_sheet_identity failed: {e}", exc_info=True)

    def check_cashflow_reconciliation(self, cur: Any) -> None:
        """prior_year cash_and_equivalents + OCF + ICF + FCF ~= current_year cash_and_equivalents.

        Excludes depository institutions - see _DEPOSITORY_INSTITUTION_SIC_CODES comment above.
        """
        try:
            cur.execute(
                """
                WITH cf AS (
                    SELECT DISTINCT ON (symbol)
                        symbol, fiscal_year, operating_cash_flow, investing_cash_flow, financing_cash_flow
                    FROM annual_cash_flow
                    WHERE data_unavailable = FALSE
                      AND operating_cash_flow IS NOT NULL
                      AND investing_cash_flow IS NOT NULL
                      AND financing_cash_flow IS NOT NULL
                    ORDER BY symbol, fiscal_year DESC
                ),
                cash AS (
                    SELECT symbol, fiscal_year, cash_and_equivalents
                    FROM annual_balance_sheet
                    WHERE data_unavailable = FALSE AND cash_and_equivalents IS NOT NULL
                )
                SELECT
                    cf.symbol, cf.fiscal_year,
                    cf.operating_cash_flow, cf.investing_cash_flow, cf.financing_cash_flow,
                    prior.cash_and_equivalents AS prior_cash,
                    curr.cash_and_equivalents AS curr_cash
                FROM cf
                JOIN stock_symbols s ON s.symbol = cf.symbol AND s.active = true
                JOIN cash curr ON curr.symbol = cf.symbol AND curr.fiscal_year = cf.fiscal_year
                JOIN cash prior ON prior.symbol = cf.symbol AND prior.fiscal_year = cf.fiscal_year - 1
                WHERE NOT EXISTS (
                    SELECT 1 FROM company_info_sec ci
                    WHERE ci.symbol = cf.symbol AND ci.sic_code = ANY(%s)
                )
                """,
                (list(_DEPOSITORY_INSTITUTION_SIC_CODES),),
            )
            flagged = []
            for row in cur.fetchall():
                ocf, icf, fcf = (
                    float(row["operating_cash_flow"]),
                    float(row["investing_cash_flow"]),
                    float(row["financing_cash_flow"]),
                )
                prior_cash, curr_cash = float(row["prior_cash"]), float(row["curr_cash"])
                implied_curr = prior_cash + ocf + icf + fcf
                residual = implied_curr - curr_cash
                tolerance = max(_CASHFLOW_TOLERANCE_FLOOR, abs(curr_cash) * _CASHFLOW_TOLERANCE_PCT)
                if abs(residual) > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "operating_cash_flow": ocf,
                            "investing_cash_flow": icf,
                            "financing_cash_flow": fcf,
                            "prior_cash": prior_cash,
                            "curr_cash": curr_cash,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: abs(r["residual"]), reverse=True)
                self.log(
                    "cashflow_reconciliation",
                    WARN,
                    "annual_cash_flow",
                    f"{len(flagged)} symbol/year(s) fail prior_cash + OCF + ICF + FCF ~= curr_cash "
                    f"beyond max(${_CASHFLOW_TOLERANCE_FLOOR:,.0f}, {_CASHFLOW_TOLERANCE_PCT:.0%} of ending cash)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] cashflow_reconciliation failed: {e}", exc_info=True)

    def check_eps_reconciliation(self, cur: Any) -> None:
        """diluted_eps * shares_outstanding_diluted ~= net_income.

        Not itemized here (see _EPS_TOLERANCE_PCT comment): preferred dividends,
        discontinued-operations allocations, noncontrolling-interest carve-outs.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.net_income, i.diluted_eps, i.shares_outstanding_diluted
                FROM annual_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.net_income IS NOT NULL
                  AND i.diluted_eps IS NOT NULL
                  AND i.shares_outstanding_diluted IS NOT NULL
                  AND i.shares_outstanding_diluted != 0
                  AND i.net_income != 0
                ORDER BY i.symbol, i.fiscal_year DESC
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
                tolerance = max(_EPS_TOLERANCE_FLOOR, abs(net_income) * _EPS_TOLERANCE_PCT)
                if abs(residual) > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
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
                    "eps_reconciliation",
                    WARN,
                    "annual_income_statement",
                    f"{len(flagged)} symbol(s) fail diluted_eps * shares_outstanding_diluted ~= "
                    f"net_income beyond max(${_EPS_TOLERANCE_FLOOR:,.0f}, {_EPS_TOLERANCE_PCT:.0%} "
                    "of net_income)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] eps_reconciliation failed: {e}", exc_info=True)
