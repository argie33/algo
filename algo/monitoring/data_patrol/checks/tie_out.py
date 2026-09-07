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
risk. Every check below uses `DISTINCT ON (symbol) ORDER BY fiscal_year DESC` to check only
each symbol's latest real (non-data_unavailable, values-present) row, matching that same
convention. Full-history detail is not lost - it's still queryable directly, just not what
reaches the WARN-severity alert.

Round 2 (added 2026-09-06, same-day follow-up goal session "figure out all the tie-out gaps"):
added gross_profit_identity and pretax_to_net_income. Both immediately flagged what looks like
a genuine, systemic magnitude bug rather than noise - large well-covered names with no reason
to have bad data (ABBV/GILD/AMGN/ABT all show a tagged gross_profit far too low for a pharma
company's ~70% gross margin; ORCL/MCD/PYPL/PSX all show net_income exceeding what
pretax_income - income_tax_expense implies, which is only possible with unusual items this
schema doesn't itemize, or a same-row vintage mismatch between fields). This smells like the
same class of bug as the SEC/XBRL campaign's "wrong-context value" findings (a dimensioned/
non-default XBRL fact winning over the true consolidated total) - see
sec_xbrl_stray_value_cascade_index_20260906 in memory for that pattern's precedent. NOT yet
root-caused (that's a separate, likely large investigation into sec_base.py's gross_profit/
pretax_income/income_tax_expense concept-priority chains, out of scope for this checker-
building session) - flagging both as WARN here is exactly the mechanism to surface it for that
follow-up, not a claim that the root cause is already found.

Segment-sum-to-consolidated (revenue rolled up from sec_segment_info's operating segments vs.
annual_income_statement.revenue) was investigated and deliberately NOT added, for two
successive reasons found across two sessions:

1. (2026-09-06) Spot-checking it against the live DB showed 100x-1,400x magnitude errors
   concentrated in foreign filers (AKO.A/AKO.B/KWM/LGPS/MRM/LFS/LRE/PDC/PAYP) -
   sec_segment_info's segment_revenue wasn't going through the same USD-normalization step
   annual_income_statement.revenue does. FIXED 2026-09-07 (commit `5bc20eb11`,
   utils/external/sec_xbrl_segments.py's XBRLSegmentParser now reuses the same
   _fx_rate_cache.get_usd_rate() pattern as the income-statement loader) - live-reverified
   AKO.A/KWM/LGPS/MRM/LFS/LRE/PDC/PAYP all now show plausibly-scaled segment_revenue.

2. (2026-09-07, same-day follow-up after the FX fix above) Still NOT viable as a simple sum,
   for a DIFFERENT, more fundamental reason: a live DB-wide scan (1,841 comparable symbol/years)
   found the segment-sum-vs-consolidated relative error is nowhere near noise-level even for
   well-known, correctly-FX-normalized USD domestic filers - p90=55%, p95=~100%, p99=154%. Root
   cause, confirmed via EA's raw sec_segment_info rows (FY2026): the parser tags BOTH true ASC
   280 reportable-segment facts AND ASC 606 revenue-disaggregation-by-product-type facts
   (StatementBusinessSegmentsAxis vs. a ProductOrServiceAxis-style disaggregation) as
   segment_type='operating' with no way to distinguish which axis a row came from - EA's rows
   include "Reportable Segment" ($7.531B, the correct, real total) ALONGSIDE "Mobile Net
   Revenue"/"Full Game Net Revenue"/"Total Consoles Net Revenue"/etc. (a full, separate
   disaggregation-by-category breakdown that ALSO sums to ~$7.5B on its own) - summing every row
   double-counts the same revenue under two different reporting dimensions. This is a parser/
   schema gap (sec_xbrl_segments.py needs to identify and tag which XBRL axis each segment row
   came from, then this check would need to sum only true business-segment-axis rows) - not a
   tolerance-tuning problem, and a distinct, larger piece of work than anything else in this
   file. Don't naively raise the tolerance to "fix" this - a residual this large is a real
   double-counting bug in the underlying data, not measurement noise to paper over.

Income-statement chain (revenue - total operating expenses ~= operating_income) was also
considered and NOT added: there is no single "total operating expenses" column in
annual_income_statement to subtract - it would require assembling cost_of_revenue + opex
sub-line-items whose completeness varies by filer (R&D/SG&A tagged inconsistently), and
gross_profit_identity above already covers the cleanest slice of this chain (revenue vs.
cost_of_revenue) without that assembly problem.
"""

import logging
from typing import Any

from ..base import BaseCheck, CheckResult
from ..config import ERROR, WARN

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
# revenue - cost_of_revenue == gross_profit is a strict GAAP definitional identity (gross_profit
# IS that subtraction, not an independently-reported line most filers choose to tag separately)
# - tight tolerance is appropriate, unlike the other checks here which cross real independent
# facts subject to legitimate measurement differences.
_GROSS_PROFIT_TOLERANCE_PCT = 0.02
_GROSS_PROFIT_TOLERANCE_FLOOR = 250_000.0
# pretax_income - income_tax_expense == net_income ignores noncontrolling-interest carve-outs
# and discontinued-operations adjustments (neither tracked as separate columns here) - looser
# than gross profit's tolerance but tighter than EPS's, since this skips the extra share-count
# rounding EPS reconciliation compounds.
_PRETAX_NET_INCOME_TOLERANCE_PCT = 0.10
_PRETAX_NET_INCOME_TOLERANCE_FLOOR = 500_000.0
# diluted shares >= basic shares is a strict structural inequality (dilution can only add
# share-count, never remove it) - no measurement-noise tolerance is conceptually justified the
# way it is for the other checks here, but a small slack is kept anyway to avoid flagging
# genuine same-period rounding where a filer's diluted and basic counts are reported equal
# because there were no dilutive securities outstanding that period.
_SHARE_COUNT_TOLERANCE_PCT = 0.001
_MAX_REPORTED_PER_CHECK = 20  # cap alert payload size - full detail still in the DB for follow-up

# Depository institutions never tag a cash flow statement whose "cash_and_equivalents" concept
# means what it means for an industrial filer - their real cash position sits mostly in
# interest-earning deposits/securities the balance-sheet field this schema tracks doesn't
# capture. Same SIC-code set as sec_base.py's _get_depository_institution_symbols (kept in
# sync with that file's own comment for the rationale) - live-confirmed via this checker's
# first production run: JPM/BAC/MUFG/KT/SKM all showed 9-13 digit "residuals" that are just
# this measurement mismatch, not a real reconciliation failure.
_DEPOSITORY_INSTITUTION_SIC_CODES = (6020, 6021, 6022, 6029, 6035, 6036, 6712)

# Security/commodity exchanges, clearinghouses, and broker-dealers hold huge gross customer
# margin/settlement/segregated cash balances that flow through financing/operating activities
# in ways that don't relate to their OWN retained cash the way an industrial filer's would -
# same class of measurement mismatch as depository institutions above, just a different SIC
# family. Live-confirmed 2026-09-06 via SEC's own companyconcept API: CME Group's real, SEC-
# tagged NetCashProvidedByUsedInFinancingActivities for FY2025 genuinely is $56.5099B (not an
# extraction bug) - a derivatives clearinghouse's daily performance-bond/settlement cash
# movements dwarf its own retained cash position. IBKR/FUTU (SIC 6211, broker-dealers) and
# ICE/SNEX (SIC 6200, exchange/broker) showed the identical shape in this same checker's
# cashflow_reconciliation run. Scoped to cashflow_reconciliation only (not the other 4 identity
# checks) - a broker-dealer/exchange's balance-sheet/EPS/gross-profit/pretax identities aren't
# known to have this same structural exception.
_FINANCIAL_INTERMEDIARY_SIC_CODES = (6200, 6211, 6221)

# Individually-verified symbols with the identical "embedded fintech float dwarfs the parent's
# own cash flow" shape as _FINANCIAL_INTERMEDIARY_SIC_CODES above, but whose SIC code doesn't
# reflect it (SIC classifies the parent's primary/legacy business, not a large embedded
# fintech segment) - same "curated allowlist, not SIC-derivable" pattern already established
# for _INSURANCE_CAPEX_EXEMPT_SYMBOLS in loaders/helpers/sec_base.py. Add here only after
# individually confirming via SEC's own companyconcept API (not by SIC-code guessing) that the
# real, SEC-tagged cash-flow figure genuinely produces this shape.
#
# MELI (MercadoLibre, SIC 7389 "business services" - e-commerce, not finance): live-confirmed
# 2026-09-06 that its real, SEC-tagged NetCashProvidedByUsedInOperatingActivities for FY2025
# genuinely is $12.116B - driven by Mercado Pago's embedded-fintech credit-portfolio/payments
# float, the same "operations dwarf retained cash" shape as a broker-dealer, just under an
# e-commerce SIC code that a blanket 7389 exclusion would be far too broad to safely add (that
# code covers many unrelated ordinary "business services" filers).
#
# AXP (American Express, SIC 6199 "finance services" - too broad a catch-all to exclude
# wholesale, also covers ordinary non-intermediary finance companies): live-confirmed FY2025
# NetCashProvidedByUsedInFinancingActivities is a real, SEC-tagged $11.21B against
# CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents of $47.79B, most of it
# card-member-deposit restricted float - the same "gross customer balance dwarfs the filer's
# own cash flow" shape as the SIC-excluded broker-dealers/exchanges above.
#
# CRCL (Circle, stablecoin issuer, also SIC 6199): live-confirmed FY2025 financing activities
# is a real $31.94B against $77.42B of (mostly USDC reserve) restricted cash - stablecoin
# mint/redeem flows are the entire business, not a reconciliation error.
_CASHFLOW_INTERMEDIARY_SYMBOL_ALLOWLIST = frozenset({"MELI", "AXP", "CRCL"})


class TieOutChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_balance_sheet_identity(cur)
        self.check_cashflow_reconciliation(cur)
        self.check_eps_reconciliation(cur)
        self.check_basic_eps_reconciliation(cur)
        self.check_gross_profit_identity(cur)
        self.check_pretax_to_net_income(cur)
        self.check_diluted_ge_basic_shares(cur)
        return self.results

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
            self.log(
                "balance_sheet_identity",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_cashflow_reconciliation(self, cur: Any) -> None:
        """prior_year cash_and_equivalents + OCF + ICF + FCF ~= current_year cash_and_equivalents.

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
