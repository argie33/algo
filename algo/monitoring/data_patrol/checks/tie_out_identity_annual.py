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
    _BALANCE_SHEET_TOLERANCE_PCT,
    _CASHFLOW_INTERMEDIARY_SYMBOL_ALLOWLIST,
    _CASHFLOW_TOLERANCE_FLOOR,
    _CASHFLOW_TOLERANCE_PCT,
    _DEPOSITORY_INSTITUTION_SIC_CODES,
    _EPS_TOLERANCE_FLOOR,
    _EPS_TOLERANCE_PCT,
    _FINANCIAL_INTERMEDIARY_SIC_CODES,
    _GROSS_PROFIT_TOLERANCE_FLOOR,
    _GROSS_PROFIT_TOLERANCE_PCT,
    _MAX_REPORTED_PER_CHECK,
    _PRETAX_NET_INCOME_TOLERANCE_FLOOR,
    _PRETAX_NET_INCOME_TOLERANCE_PCT,
    _RETAINED_EARNINGS_TOLERANCE_FLOOR,
    _RETAINED_EARNINGS_TOLERANCE_PCT,
)

logger = logging.getLogger(__name__)


class TieOutIdentityAnnualMixin:
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

    def check_balance_sheet_identity(self, cur: Any) -> None:
        """total_assets == total_liabilities + stockholders_equity.

        NOTE: load_financial_statements.py derives total_liabilities = total_assets -
        stockholders_equity whenever a filer never tags "Liabilities" directly - those rows
        tie out by construction (0 residual) and are harmlessly uninformative here, not a
        false pass of a check that was never really performed for them.

        NOTE (2026-09-06, goal: "SEC/XBRL missing data to zero" / tie-out sweep): a real,
        currently-unresolvable population of ex-SPAC/Up-C-structure filers (live-verified via
        SEC's own companyfacts API: PROK/ProKidney Corp - FY2025 LiabilitiesAndStockholdersEquity
        = $335,574,000 exactly matches this table's total_assets, and BOTH total_liabilities
        ($34,781,000) and stockholders_equity (-$1,011,197,000) are individually the correct,
        real SEC-tagged values - but they only sum to -$976,416,000, a ~$1.31B gap) carries a
        real "temporary/mezzanine equity" balance-sheet component (Up-C pre-IPO holder units,
        redeemable NCI, etc.) between Liabilities and permanent StockholdersEquity that this
        schema has no column for at all (StockholdersEquityIncludingPortionAttributableTo
        NoncontrollingInterest and MinorityInterest both don't exist for this filer either, so
        it isn't a simple missing-concept-mapping fix). ATTO/FAC/LTGO/SCTX show the identical
        shape (modest assets/liabilities, huge negative equity) and are likely the same
        explanation. This flags as a genuine WARN here - not a false positive of extraction,
        but a structural gap in this two-term identity for this capital-structure class. Don't
        spend time trying to "fix" this population via extraction changes without first adding
        a real mezzanine-equity column and loader support.

        NOTE (2026-09-07, goal: stock_scores factor/composite sanity audit): the PROK-style
        mezzanine-equity population above is NOT the main source of noise on this check - it's
        a small minority. The dominant cause (before the fix below), live-measured against the
        local DB: **761/5,078 symbols (15.0%) fail this check at the 1% tolerance**, and 85%+ of
        those have *positive* stockholders_equity (not the PROK pattern's negative equity),
        including large, well-covered names with material noncontrolling interests (XOM, CVX,
        KKR, APO, CB, RTX, BLK, NEE, D, ENB, VOYA, FNF, IBKR). Root-caused via a fresh SEC
        companyfacts pull for XOM: `liabilities`($117,931M) + `stockholders_equity`($110,569M)
        + directly-tagged `MinorityInterest`($4,823M) = `assets`($233,323M) EXACTLY - this
        schema's `stockholders_equity` column stores the narrower parent-only concept, and the
        NCI portion had no column to land in at all.

        FIXED 2026-09-07 (migration 1265): added `noncontrolling_interest` (annual + quarterly
        balance sheet), extracted from the directly-tagged `MinorityInterest` XBRL concept (see
        `sec_balance_sheet.py`'s comment on that concept for the XOM evidence above) - not a
        derived subtraction, XOM and the other flagged large-caps tag it directly. This check's
        identity is now `assets == liabilities + stockholders_equity + noncontrolling_interest`.
        Rows for filers who don't tag `MinorityInterest` at all (the true PROK-style mezzanine-
        equity population, and ordinary single-entity filers with no NCI) are unaffected -
        `COALESCE(noncontrolling_interest, 0)` makes the identity degrade to the original
        two-term form when the column is NULL. Expect the ~15% WARN rate to collapse close to
        the <1% baseline of this check's siblings once affected symbols reload; PROK/ATTO/FAC/
        LTGO/SCTX-style true mezzanine-equity gaps remain unfixed (still no column for that).

        FIXED 2026-09-09 (migration 1274): added `temporary_equity`, extracted from the
        directly-tagged `TemporaryEquityCarryingAmountAttributableToParent` XBRL concept -
        live-confirmed this closes OBAI/LTGO/SCTX's residuals exactly (see that concept's
        comment in sec_balance_sheet.py's get_balance_sheet() for the numbers). Identity is now
        `assets == liabilities + temporary_equity + stockholders_equity +
        noncontrolling_interest`, same `COALESCE(..., 0)` degrade-when-NULL discipline as
        noncontrolling_interest. PROK itself tags a sibling concept
        (RedeemableNoncontrollingInterestEquityOtherCarryingAmount) instead, so it is NOT
        expected to fully close from this column alone - don't re-triage PROK specifically as
        still-broken without checking that.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.total_assets, b.total_liabilities,
                    b.stockholders_equity, b.noncontrolling_interest, b.temporary_equity
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
                assets, liabilities, equity, nci, temp_equity = (
                    float(row["total_assets"]),
                    float(row["total_liabilities"]),
                    float(row["stockholders_equity"]),
                    float(row["noncontrolling_interest"] or 0),
                    float(row["temporary_equity"] or 0),
                )
                residual = assets - (liabilities + equity + nci + temp_equity)
                relative_error = abs(residual) / abs(assets)
                if relative_error > _BALANCE_SHEET_TOLERANCE_PCT:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "total_assets": assets,
                            "total_liabilities": liabilities,
                            "stockholders_equity": equity,
                            "noncontrolling_interest": nci,
                            "temporary_equity": temp_equity,
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
            self.log(
                "balance_sheet_identity",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_balance_sheet_identity(self, cur: Any) -> None:
        """total_assets == total_liabilities + stockholders_equity + noncontrolling_interest,
        quarterly mirror of check_balance_sheet_identity.

        ADDED 2026-09-07 (goal: tie-out CI coverage sweep). Deferred earlier this session
        pending two schema gaps on quarterly_balance_sheet - noncontrolling_interest (migration
        1265, `1d0e48378`) and retained_earnings (migration 1266, `c72e7e007`) - both landed;
        this check only needs the former.

        Live-verified against the local DB immediately before adding: 731/5,092 (14.4%) of
        quarterly rows fail at the same 1% tolerance as the annual check - same magnitude and,
        by inspection, the same top offenders (LTGO/PROK/OMEX/SCTX/ATTO - the documented
        PROK-style mezzanine-equity population with no noncontrolling_interest/MinorityInterest
        concept at all) plus a long tail of NCI-bearing names whose quarterly
        noncontrolling_interest column is still NULL - the metrics reload that repairs this
        (same one backfilling the annual NCI gap) had not yet reached most quarterly rows as of
        when this check was added. Expect this rate to collapse toward the <1% baseline of this
        check's siblings once that reload completes, same trajectory as the annual check
        followed earlier the same day. Don't re-triage this rate as a new bug without first
        confirming the reload has actually finished.

        FIXED 2026-09-09 (migration 1274): added `temporary_equity` to the identity, same fix
        and same evidence as check_balance_sheet_identity's own 2026-09-09 update above - see
        that docstring.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter, b.total_assets, b.total_liabilities,
                    b.stockholders_equity, b.noncontrolling_interest, b.temporary_equity
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_assets IS NOT NULL
                  AND b.total_liabilities IS NOT NULL
                  AND b.stockholders_equity IS NOT NULL
                  AND b.total_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                assets, liabilities, equity, nci, temp_equity = (
                    float(row["total_assets"]),
                    float(row["total_liabilities"]),
                    float(row["stockholders_equity"]),
                    float(row["noncontrolling_interest"] or 0),
                    float(row["temporary_equity"] or 0),
                )
                residual = assets - (liabilities + equity + nci + temp_equity)
                relative_error = abs(residual) / abs(assets)
                if relative_error > _BALANCE_SHEET_TOLERANCE_PCT:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_assets": assets,
                            "total_liabilities": liabilities,
                            "stockholders_equity": equity,
                            "noncontrolling_interest": nci,
                            "temporary_equity": temp_equity,
                            "residual": residual,
                            "relative_error_pct": round(relative_error * 100, 2),
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["relative_error_pct"], reverse=True)
                self.log(
                    "quarterly_balance_sheet_identity",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail total_assets == total_liabilities + "
                    f"stockholders_equity + noncontrolling_interest + temporary_equity beyond "
                    f"{_BALANCE_SHEET_TOLERANCE_PCT:.0%} tolerance",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_balance_sheet_identity failed: {e}", exc_info=True)
            self.log(
                "quarterly_balance_sheet_identity",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_cashflow_reconciliation(self, cur: Any) -> None:
        """prior_year cash + OCF + ICF + FCF ~= current_year cash, where "cash" prefers
        cash_and_restricted_cash_combined over cash_and_equivalents when present.

        FIXED 2026-09-07 (goal session: live tie-out run against production DB, ADP live-
        confirmed): per ASU 2016-18, a filer's cash-flow statement reconciles OCF+ICF+FCF to
        its COMBINED cash+restricted-cash total when it holds material restricted cash (payroll
        processors like ADP - funds held for clients, banks/trust companies, escrow-heavy
        businesses), not to unrestricted cash_and_equivalents alone. See migration 1267's own
        header for the full ADP evidence (OCF+ICF+FCF=$5.608B FY2026 matches the real combined-
        cash change of $5.571B, not the $0.882B change in unrestricted cash_and_equivalents
        alone). cash_and_restricted_cash_combined is NULL for the majority of filers with no
        material restricted cash, where cash_and_equivalents alone already reconciles - no
        regression for that population.

        Excludes depository institutions and financial intermediaries (exchanges/clearinghouses/
        broker-dealers), plus individually-verified embedded-fintech exceptions - see
        _DEPOSITORY_INSTITUTION_SIC_CODES, _FINANCIAL_INTERMEDIARY_SIC_CODES, and
        _CASHFLOW_INTERMEDIARY_SYMBOL_ALLOWLIST comments above.
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
                    SELECT symbol, fiscal_year,
                        COALESCE(cash_and_restricted_cash_combined, cash_and_equivalents) AS cash_and_equivalents
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
                AND NOT (cf.symbol = ANY(%s))
                """,
                (
                    list(_DEPOSITORY_INSTITUTION_SIC_CODES + _FINANCIAL_INTERMEDIARY_SIC_CODES),
                    list(_CASHFLOW_INTERMEDIARY_SYMBOL_ALLOWLIST),
                ),
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
            self.log(
                "cashflow_reconciliation",
                ERROR,
                "annual_cash_flow",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

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
            self.log(
                "eps_reconciliation",
                ERROR,
                "annual_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_basic_eps_reconciliation(self, cur: Any) -> None:
        """earnings_per_share * shares_outstanding_basic ~= net_income.

        ADDED 2026-09-07 (goal: stock_scores factor/composite sanity audit + "make sure we
        have all the right tie outs in CI"): mirrors check_eps_reconciliation above exactly,
        but for basic EPS/shares - that check only ever covered diluted, leaving the basic
        pair with no periodic monitoring-layer coverage at all. load_financial_statements.py
        already has a LOAD-TIME guard cross-checking implied EPS against
        shares_outstanding_basic/diluted to reject scale errors (see that file's
        `_reject_implausible_shares_outstanding` docstring, "FIXED 2026-08-21"/"FIXED
        2026-09-06") - this is a separate, complementary DETECTION-layer check: it catches
        anything that guard doesn't (a future regression in the guard itself, a new bad-data
        pattern not yet covered by it, or drift introduced after load time), same as how
        eps_reconciliation (diluted) already coexists with that same load-time guard rather
        than being made redundant by it. Same tolerance constants as the diluted check - the
        same untracked noise sources (preferred dividends, discontinued-ops allocations,
        NCI carve-outs) apply identically to basic EPS.

        FIXED 2026-09-07 (same-day follow-up, goal: "SEC/XBRL...tie outs...tying out right
        way" sweep): the original query read `annual_income_statement.eps`, which is a dead
        legacy column - live-confirmed 0 of 67,746 rows have it non-NULL, ever. The real,
        actually-populated basic-EPS column is `earnings_per_share` (59,868 non-NULL rows) -
        `diluted_eps`'s sibling above it in the same table, populated by the same loader.
        This meant the check as originally written matched zero rows and always silently
        "passed", giving false confidence that basic EPS ties out when it was never actually
        being tested at all - the exact failure mode this whole checker exists to catch in
        OTHER tables, just self-inflicted here via a wrong column name.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.net_income, i.earnings_per_share, i.shares_outstanding_basic
                FROM annual_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.net_income IS NOT NULL
                  AND i.earnings_per_share IS NOT NULL
                  AND i.shares_outstanding_basic IS NOT NULL
                  AND i.shares_outstanding_basic != 0
                  AND i.net_income != 0
                ORDER BY i.symbol, i.fiscal_year DESC
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
                tolerance = max(_EPS_TOLERANCE_FLOOR, abs(net_income) * _EPS_TOLERANCE_PCT)
                if abs(residual) > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
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
                    "basic_eps_reconciliation",
                    WARN,
                    "annual_income_statement",
                    f"{len(flagged)} symbol(s) fail earnings_per_share * shares_outstanding_basic ~= "
                    f"net_income beyond max(${_EPS_TOLERANCE_FLOOR:,.0f}, {_EPS_TOLERANCE_PCT:.0%} "
                    "of net_income)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] basic_eps_reconciliation failed: {e}", exc_info=True)
            self.log(
                "basic_eps_reconciliation",
                ERROR,
                "annual_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_gross_profit_identity(self, cur: Any) -> None:
        """revenue - cost_of_revenue ~= gross_profit.

        Only checks symbols where all three fields are independently tagged in the same
        filing - not derived from each other by load_financial_statements.py (a filer that
        never tags one of the three isn't in scope for this identity, same treatment as
        balance_sheet_identity's derived-liabilities note above).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.revenue, i.cost_of_revenue, i.gross_profit
                FROM annual_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.revenue IS NOT NULL
                  AND i.cost_of_revenue IS NOT NULL
                  AND i.gross_profit IS NOT NULL
                  AND i.revenue != 0
                ORDER BY i.symbol, i.fiscal_year DESC
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
                    "gross_profit_identity",
                    WARN,
                    "annual_income_statement",
                    f"{len(flagged)} symbol(s) fail revenue - cost_of_revenue ~= gross_profit "
                    f"beyond max(${_GROSS_PROFIT_TOLERANCE_FLOOR:,.0f}, "
                    f"{_GROSS_PROFIT_TOLERANCE_PCT:.0%} of revenue)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] gross_profit_identity failed: {e}", exc_info=True)
            self.log(
                "gross_profit_identity",
                ERROR,
                "annual_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_pretax_to_net_income(self, cur: Any) -> None:
        """pretax_income - income_tax_expense ~= net_income.

        Not itemized here (see _PRETAX_NET_INCOME_TOLERANCE_PCT comment): noncontrolling-
        interest carve-outs, discontinued-operations adjustments.
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (i.symbol)
                    i.symbol, i.fiscal_year, i.pretax_income, i.income_tax_expense, i.net_income
                FROM annual_income_statement i
                JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
                WHERE i.data_unavailable = FALSE
                  AND i.pretax_income IS NOT NULL
                  AND i.income_tax_expense IS NOT NULL
                  AND i.net_income IS NOT NULL
                  AND i.net_income != 0
                ORDER BY i.symbol, i.fiscal_year DESC
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
                tolerance = max(_PRETAX_NET_INCOME_TOLERANCE_FLOOR, abs(net_income) * _PRETAX_NET_INCOME_TOLERANCE_PCT)
                if abs(residual) > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
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
                    "pretax_to_net_income",
                    WARN,
                    "annual_income_statement",
                    f"{len(flagged)} symbol(s) fail pretax_income - income_tax_expense ~= "
                    f"net_income beyond max(${_PRETAX_NET_INCOME_TOLERANCE_FLOOR:,.0f}, "
                    f"{_PRETAX_NET_INCOME_TOLERANCE_PCT:.0%} of net_income)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] pretax_to_net_income failed: {e}", exc_info=True)
            self.log(
                "pretax_to_net_income",
                ERROR,
                "annual_income_statement",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_retained_earnings_rollforward(self, cur: Any) -> None:
        """prior_year retained_earnings + net_income - |dividends_paid| ~= curr_year retained_earnings,
        OR (when that fails) the same identity with common_stock_repurchased also subtracted.

        ADDED 2026-09-07 (goal: "make sure we have all the right tie outs" sweep, CI tie-out
        coverage audit's #2 recommendation). Ignores share buybacks, stock-comp equity reclasses,
        and OCI items - none tracked as separate columns here, same class of untracked noise as
        cashflow_reconciliation's FX effects - hence the loose tolerance, looser than every other
        check here except cashflow's. dividends_paid is treated as 0 when NULL/absent (a symbol
        that never tagged it may simply pay none, not have missing data) rather than excluding
        the row - narrower exclusion than the other checks' "all fields must be present" pattern
        because dividends_paid's absence is itself informative, not a data gap.

        Live feasibility check against the local DB (2026-09-07) found this genuinely clean at
        the median - p50=0%, p75=3.3% relative error - unlike the segment-sum-to-consolidated
        check above that was rejected for being noisy even at p90 (55%).

        FIXED 2026-09-07 (goal session: score-review sweep, live tie-out run against production
        DB): AAPL/NVDA/META/etc. all failed this check by amounts matching their own
        common_stock_repurchased almost exactly (AAPL FY2025: residual $91.699B vs real
        buyback $90.711B; NVDA FY2026: residual $40.158B vs real buyback $40.086B; consistent
        across all 10 years of AAPL history checked, residual-with-buyback-subtracted stays
        under ~$2.5B every year vs $30-97B without). A filer using the constructive-retirement
        method for treasury stock charges repurchases in excess of par directly against
        retained earnings - AAPL's persistently negative retained earnings (a well-known real
        fact, not a bug - see load_stock_scores.py's own comment on quarterly_retained_
        earnings_column) is a direct consequence of this. Not every filer uses this method
        (some use cost-method treasury stock, which doesn't touch retained earnings at all) -
        a live population check found unconditionally subtracting buybacks for EVERY symbol
        makes MORE rows fail, not fewer, so this uses OR-logic instead: flag only when BOTH
        the original identity AND the buyback-adjusted identity fail tolerance. This can only
        reduce false positives relative to the original single-path check, never introduce new
        ones - a symbol that already passed the original identity still passes exactly as
        before.
        """
        try:
            cur.execute(
                """
                WITH re AS (
                    SELECT DISTINCT ON (symbol)
                        symbol, fiscal_year, retained_earnings
                    FROM annual_balance_sheet
                    WHERE data_unavailable = FALSE AND retained_earnings IS NOT NULL
                    ORDER BY symbol, fiscal_year DESC
                ),
                re_prior AS (
                    SELECT symbol, fiscal_year, retained_earnings
                    FROM annual_balance_sheet
                    WHERE data_unavailable = FALSE AND retained_earnings IS NOT NULL
                ),
                ni AS (
                    SELECT symbol, fiscal_year, net_income
                    FROM annual_income_statement
                    WHERE data_unavailable = FALSE AND net_income IS NOT NULL
                ),
                div AS (
                    SELECT symbol, fiscal_year, dividends_paid, common_stock_repurchased
                    FROM annual_cash_flow
                    WHERE data_unavailable = FALSE
                )
                SELECT
                    curr.symbol, curr.fiscal_year,
                    prior.retained_earnings AS prior_retained_earnings,
                    curr.retained_earnings AS curr_retained_earnings,
                    ni.net_income,
                    div.dividends_paid,
                    div.common_stock_repurchased
                FROM re curr
                JOIN stock_symbols s ON s.symbol = curr.symbol AND s.active = true
                JOIN re_prior prior ON prior.symbol = curr.symbol AND prior.fiscal_year = curr.fiscal_year - 1
                JOIN ni ON ni.symbol = curr.symbol AND ni.fiscal_year = curr.fiscal_year
                LEFT JOIN div ON div.symbol = curr.symbol AND div.fiscal_year = curr.fiscal_year
                """
            )
            flagged = []
            for row in cur.fetchall():
                prior_re, curr_re, net_income = (
                    float(row["prior_retained_earnings"]),
                    float(row["curr_retained_earnings"]),
                    float(row["net_income"]),
                )
                dividends_paid = abs(float(row["dividends_paid"])) if row["dividends_paid"] is not None else 0.0
                buybacks = (
                    abs(float(row["common_stock_repurchased"])) if row["common_stock_repurchased"] is not None else 0.0
                )
                implied_curr_re = prior_re + net_income - dividends_paid
                residual = implied_curr_re - curr_re
                tolerance = max(_RETAINED_EARNINGS_TOLERANCE_FLOOR, abs(curr_re) * _RETAINED_EARNINGS_TOLERANCE_PCT)
                if abs(residual) > tolerance:
                    implied_curr_re_with_buybacks = implied_curr_re - buybacks
                    residual_with_buybacks = implied_curr_re_with_buybacks - curr_re
                    if buybacks > 0 and abs(residual_with_buybacks) <= tolerance:
                        continue  # Constructive-retirement filer: buybacks explain the gap, not a real bug
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "prior_retained_earnings": prior_re,
                            "curr_retained_earnings": curr_re,
                            "net_income": net_income,
                            "dividends_paid": dividends_paid,
                            "implied_curr_retained_earnings": implied_curr_re,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: abs(r["residual"]), reverse=True)
                self.log(
                    "retained_earnings_rollforward",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail prior_retained_earnings + net_income - "
                    f"|dividends_paid| ~= curr_retained_earnings beyond max("
                    f"${_RETAINED_EARNINGS_TOLERANCE_FLOOR:,.0f}, "
                    f"{_RETAINED_EARNINGS_TOLERANCE_PCT:.0%} of curr_retained_earnings)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] retained_earnings_rollforward failed: {e}", exc_info=True)
            self.log(
                "retained_earnings_rollforward",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )
