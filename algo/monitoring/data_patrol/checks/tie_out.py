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
# prior_retained_earnings + net_income - |dividends_paid| ~= curr_retained_earnings ignores
# share buybacks, stock-comp-driven equity reclasses, and OCI items (none tracked as separate
# columns here) - live feasibility check against the local DB (2026-09-07) found this genuinely
# clean at the median (p50=0%, p75=3.3% relative error) unlike the segment-sum-to-consolidated
# check that was rejected for being noisy even at p90 (see this file's docstring) - a much
# looser tolerance than gross_profit/balance_sheet's tight identities, similar to cashflow's,
# since buybacks/OCI are real and common enough to not be pure noise.
_RETAINED_EARNINGS_TOLERANCE_PCT = 0.25
_RETAINED_EARNINGS_TOLERANCE_FLOOR = 1_000_000.0
# operating_cash_flow - capex == free_cash_flow is a load-time derived identity (load_
# financial_statements.py computes free_cash_flow FROM these two fields, it is not an
# independently-tagged XBRL fact) - live feasibility check against the local DB (2026-09-07,
# 4,439 comparable rows) found p50/p75/p90 relative error == 0%, tighter even than gross_profit's
# identity, so a tolerance this tight has near-zero false-positive risk.
_FREE_CASH_FLOW_TOLERANCE_PCT = 0.02
_FREE_CASH_FLOW_TOLERANCE_FLOOR = 250_000.0
# operating_cash_flow + investing_cash_flow + financing_cash_flow ~= net_change_cash omits the
# real filing's own "effect of exchange rate changes on cash" line (not tracked as a separate
# column here) - same missing-FX-effect gap check_cashflow_reconciliation already documents, so
# reuses that check's tolerance rather than a new number. Unlike that check, this one needs no
# cross-year balance-sheet join (no risk of colliding cash-concept definitions between
# "cash_and_equivalents" and the cash-flow statement's own reconciliation figure) and needs no
# live feasibility percentile check against the local DB - net_change_cash was a fully unfetched
# column (0 rows anywhere) until the 2026-09-07 fix that wired it up, so there is no existing
# data to sample yet; re-derive tolerance from real post-reload data if this proves noisy.
_NET_CHANGE_CASH_TOLERANCE_PCT = _CASHFLOW_TOLERANCE_PCT
_NET_CHANGE_CASH_TOLERANCE_FLOOR = _CASHFLOW_TOLERANCE_FLOOR
# quick_ratio <= current_ratio is a strict structural inequality by construction (quick_ratio's
# numerator is current_assets minus inventory, a subset of current_ratio's numerator, over the
# same denominator) - both are computed by the SAME loader call from the SAME current_assets/
# current_liabilities/inventory inputs (loaders/helpers/vqg_quality.py), so unlike every other
# check in this file there is no legitimate measurement-difference source for a violation; a
# tiny slack is kept only for float rounding, not real-world noise.
_QUICK_RATIO_TOLERANCE = 0.0001
# current_assets <= total_assets and current_liabilities <= total_liabilities are strict
# structural inequalities (current is a subset/category of total, same row, same table,
# same loader call) - no legitimate measurement-difference source for a violation, same
# reasoning as _SHARE_COUNT_TOLERANCE_PCT and _QUICK_RATIO_TOLERANCE above. Live feasibility
# check against the local DB (2026-09-07) found this is genuinely rare: 1/4,180 symbols for
# current_assets vs total_assets (SSL, a real magnitude-swap bug - current_assets tagged at
# $130.2B vs total_assets $20.2B, a ~6.4x mismatch) and 8/4,171 for current_liabilities vs
# total_liabilities, both far below the noise floor of the loosest checks in this file.
_CURRENT_VS_TOTAL_TOLERANCE_PCT = 0.001
# long_term_debt <= total_liabilities is the same subset/category structural inequality as
# current_assets/current_liabilities above (long-term debt is one liability line item, never
# the whole liability side), but is noisier in practice - live feasibility check against the
# local DB (2026-09-07) found 64/4,244 comparable symbol/years beyond a 0.1% slack, higher than
# current_assets_le_total_assets's 1/4,180 but still a small minority driven by real
# wrong-magnitude bugs, not filer-side convention differences (spot-checked: INCY FY2018
# long_term_debt tagged at $19.094B vs a real total_liabilities of $719.8M, a ~26.5x mismatch -
# Incyte's real 2018 debt was a ~$402M convertible note). Deliberately compares long_term_debt
# ALONE, not long_term_debt + short_term_debt - summing introduced ~30% more false positives in
# the same feasibility check (87/4,396) because some filers double-tag the current portion of
# long-term debt under both concepts, the same double-counting risk this file's own O&G capex
# dual-concept-sum fix and the rejected operating_income=gross_profit-opex check ran into.
_LONG_TERM_DEBT_TOLERANCE_PCT = 0.001
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
        self.check_retained_earnings_rollforward(cur)
        self.check_free_cash_flow_identity(cur)
        self.check_cashflow_activities_sum_to_net_change(cur)
        self.check_quick_ratio_le_current_ratio(cur)
        self.check_current_assets_le_total_assets(cur)
        self.check_current_liabilities_le_total_liabilities(cur)
        self.check_long_term_debt_le_total_liabilities(cur)
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

    def check_retained_earnings_rollforward(self, cur: Any) -> None:
        """prior_year retained_earnings + net_income - |dividends_paid| ~= curr_year retained_earnings.

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
                    SELECT symbol, fiscal_year, dividends_paid
                    FROM annual_cash_flow
                    WHERE data_unavailable = FALSE
                )
                SELECT
                    curr.symbol, curr.fiscal_year,
                    prior.retained_earnings AS prior_retained_earnings,
                    curr.retained_earnings AS curr_retained_earnings,
                    ni.net_income,
                    div.dividends_paid
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
                implied_curr_re = prior_re + net_income - dividends_paid
                residual = implied_curr_re - curr_re
                tolerance = max(_RETAINED_EARNINGS_TOLERANCE_FLOOR, abs(curr_re) * _RETAINED_EARNINGS_TOLERANCE_PCT)
                if abs(residual) > tolerance:
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
