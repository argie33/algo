"""Shared constants and private helper mixin for TieOutChecker, extracted from
tie_out.py (file-size ratchet split, pure extraction - no behavior change). Every
tolerance/threshold constant and SIC-code/symbol allowlist used by more than one
check lives here so every split-out check file can import exactly what it needs.
TieOutSharedMixin holds the 2 private helpers shared across multiple check methods.
"""

import logging
from typing import TYPE_CHECKING, Any

from ..base import CheckResult
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
# operating_income <= gross_profit - operating_expenses + tolerance is a one-directional
# bound, not a two-sided identity (see this file's module docstring for why): operating_expenses
# (SG&A) is only one of several real expense lines between gross_profit and operating_income
# (R&D, D&A-when-broken-out, restructuring, impairments also apply), so operating_income
# legitimately falls BELOW gross_profit - operating_expenses for almost every filer that reports
# any of those other lines - a violation in that direction is not flaggable noise. Only a
# violation in the mathematically-impossible direction (operating_income exceeding what SG&A
# alone would allow) is a real data problem. operating_expenses was only just wired up
# (2026-09-07) and is not backfilled yet - this tolerance is a placeholder based on this file's
# other loose-tolerance checks (cashflow/retained-earnings), not a live-data percentile check
# like gross_profit_identity's; re-derive from real post-reload data if this proves noisy.
_OPERATING_INCOME_BOUND_TOLERANCE_PCT = 0.10
_OPERATING_INCOME_BOUND_TOLERANCE_FLOOR = 500_000.0
# goodwill <= total_assets is the same subset/category structural inequality as
# current_assets/current_liabilities/long_term_debt above - goodwill is one asset line item,
# never the whole asset side. Live feasibility check against the local DB (2026-09-07) found
# 9/3,355 comparable symbol/years beyond a 0.1% slack, a clean noise floor (0.27%) comparable
# to current_assets_le_total_assets's. Spot-checked 3 of the 9 via a fresh get_balance_sheet()
# call (not just the stale DB row) to confirm these are live bugs, not pending-reload noise:
# ILLR FY2024 (goodwill $1.0058B vs real total_assets $50.578M, ~20x mismatch), BTCT FY2022,
# and MTC FY2025 all still reproduce with current extraction code.
_GOODWILL_TOLERANCE_PCT = 0.001
_MAX_REPORTED_PER_CHECK = 20  # cap alert payload size - full detail still in the DB for follow-up

# Round 5 (2026-09-07, goal: "run all the tie-outs" buildout). stock_based_compensation/
# common_stock_repurchased should always be non-negative magnitudes (a non-cash addback and a
# cash outflow, respectively) - load_financial_statements.py's transform() now abs()'s both
# the same way it already does for dividends_paid, so any row still negative in the DB is
# either pending that fix's reload or a future extraction regression this guard exists to
# catch. See that fix's commit for the live AAMI/JCTC evidence this bug is real, not
# speculative.
_MIN_PLAUSIBLE_SHARES_OUTSTANDING = 100_000
_MAX_PLAUSIBLE_SHARES_OUTSTANDING = 500_000_000_000
# ^ mirrors load_financial_statements.py's _reject_implausible_shares_outstanding() bounds
# exactly (kept in sync intentionally, not re-derived) - shares_outstanding_dei sits in the
# same EPS-derivation fallback chain as shares_outstanding_basic/diluted, and this check is
# the same "regression guard for a loader-side fix" role every bound check in this file plays
# for its own field. See that fix's commit for the live EEFT evidence (dei tagged
# 52,752,851,000,000,000 for FY2020 vs a real ~52.2-52.3M).

# accounts_payable <= current_liabilities: same subset/category structural inequality as
# goodwill_le_total_assets above - AP is one liability line item, never the whole current-
# liability side. Live feasibility check against the local DB (2026-09-07, same session as the
# migration-1263 accounts_payable extraction landing) found 3/2,827 comparable symbol/years
# beyond a 0.1% slack (WALD FY2021, GLND FY2026, ATPC FY2018). Spot-checked all 3 via a fresh
# get_balance_sheet() call: all now return None for both fields - stale DB rows pending reload,
# same class as despac_current_assets_stale_not_a_bug, not a live extraction bug. Kept as a
# permanent WARN-level guard since the check itself is correct and the false-positive rate is
# in line with the other structural-inequality checks above.
_ACCOUNTS_PAYABLE_TOLERANCE_PCT = 0.001

# cash_and_equivalents <= current_assets: same subset/category structural inequality as
# accounts_payable_le_current_liabilities above - cash is one current-asset line item, never
# the whole current-asset side. Live feasibility check against the local DB (2026-09-07) found
# 26/4,207 comparable symbol/years beyond a 0.1% slack, dominated by the already-known
# despac_current_assets_stale_not_a_bug_20260907 cohort (HIPO/PWP/BETR/SOFI/IGIC/OWL all
# reappear here). Spot-checked 2 of the non-despac outliers (SHO, PHVS) via a fresh
# get_balance_sheet() call: both now return None for current_assets/cash_and_equivalents -
# stale rows pending reload (same root cause as
# [[score_sanity_value_growth_loader_failure_20260907]]'s force-null bug, actively being fixed
# by a concurrent session as of this check), not a live extraction bug.
_CASH_TOLERANCE_PCT = 0.001

# inventory <= current_assets: same subset/category structural inequality as
# cash_le_current_assets above - inventory is one current-asset line item, never the whole
# current-asset side. Live feasibility check against the local DB (2026-09-07) found
# 14/2,754 comparable symbol/years beyond a 0.1% slack. Unlike the other structural-
# inequality checks' false-positive population (stale rows pending a routine reload), the
# top hit here is a genuine, permanent data-integrity bug, not staleness: PARA's
# annual_balance_sheet carries current_assets/total_assets correctly re-pulled from the
# CIK SEC EDGAR's ticker file currently resolves "PARA" to (Banzai International, Inc. -
# our own stock_symbols.security_name already says so: "Banzai International, Inc. -
# Class A Common Stock"), but FY2020-2022's inventory ($1.5-1.8B) is frozen at a huge
# stale value left over from whichever much larger company held the "PARA" ticker before
# it was recycled - Banzai's real filings apparently never tag InventoryNet at all, so
# preserve_on_missing_fields' COALESCE has nothing to overwrite that stale value with and
# it survives indefinitely. Confirmed via a fresh SEC EDGAR company_tickers.json pull
# (CIK 0001826011, entityName "Banzai International, Inc.") and a fresh
# fetch_incremental("PARA") call, whose FY2022 row has assets_current=1,021,603 matching
# the DB's current stale-free current_assets exactly, with no inventory concept present
# in the raw fetch at all. preserve_on_missing_fields' "financial facts are immutable once
# real" assumption holds within one continuously-existing company but breaks the moment a
# ticker is recycled to an unrelated entity - out of scope to fix generally this session
# (would need a ticker-recycling/entity-discontinuity detector, not attempted), but this
# check at least surfaces the resulting impossibility going forward.
_INVENTORY_TOLERANCE_PCT = 0.001

# accounts_receivable/ppe_net/short_term_debt/operating_lease_liability/finance_lease_liability
# vs. their parent total: the same subset/category structural inequality as inventory/goodwill/
# long_term_debt above - each is one line item, never the whole asset or liability side. Live
# feasibility checks against the local DB (2026-09-07, Round 3 sweep) all landed clean:
# accounts_receivable_le_current_assets 5/3,786, ppe_net_le_total_assets 4/4,757,
# short_term_debt_le_current_liabilities 44/1,945 (2.3%, the noisiest of the five - still a
# small minority, comparable to long_term_debt_le_total_liabilities's own noise floor),
# operating_lease_liability_le_total_liabilities 3/4,326, finance_lease_liability_le_total_
# liabilities 3/1,652.
_ACCOUNTS_RECEIVABLE_TOLERANCE_PCT = 0.001
_PPE_NET_TOLERANCE_PCT = 0.001
_SHORT_TERM_DEBT_TOLERANCE_PCT = 0.001
_OPERATING_LEASE_LIABILITY_TOLERANCE_PCT = 0.001
_FINANCE_LEASE_LIABILITY_TOLERANCE_PCT = 0.001

# diluted_eps <= earnings_per_share (basic) is a real GAAP rule (ASC 260's antidilution
# provision), not a heuristic: a filer may never report a diluted per-share figure MORE
# favorable than basic - dilutive securities are excluded from the diluted calculation
# whenever including them would raise EPS (or shrink a loss per share), so diluted can only
# ever equal or fall below basic. Because "more favorable" means numerically larger
# regardless of sign (a less-negative loss-per-share is just as much an antidilution
# violation as an inflated profit-per-share), a single signed inequality - diluted_eps -
# earnings_per_share > tolerance - correctly catches both directions without a separate
# branch per sign; live-verified against the local DB (2026-09-07, quarterly_income_statement):
# of 65 raw loss-period "violations" (diluted less negative than basic) essentially all were
# genuine magnitude-swap bugs (e.g. RETO diluted -0.16 vs basic -377.10, a ~2,356x mismatch),
# not a sign-handling artifact. Tolerance tuned looser than _SHARE_COUNT_TOLERANCE_PCT's
# near-zero slack because per-share figures are rounded to 2 decimals at the source (a real
# source of small legitimate divergence tiny share-count tolerances don't have) - pct=2%/
# floor=$0.01 landed a clean 13/2,964 (0.44%) noise floor, in line with this file's other
# structural checks. Quarterly-only for now - no annual counterpart check exists yet.
_DILUTED_LE_BASIC_EPS_TOLERANCE_PCT = 0.02
_DILUTED_LE_BASIC_EPS_TOLERANCE_FLOOR = 0.01

# Quarterly-table tolerances (Round 3/4, 2026-09-07 evening): the structural-inequality and
# derived-identity checks (current_assets/current_liabilities/long_term_debt/goodwill/
# accounts_payable/cash/inventory/accounts_receivable/ppe_net/short_term_debt/
# operating_lease_liability/finance_lease_liability, gross_profit_identity,
# free_cash_flow_identity, diluted_ge_basic_shares, diluted_le_basic_eps) all live-
# feasibility-checked clean at the EXACT SAME tolerance as their annual sibling - quarterly
# reuses the annual constants directly for those, no new constants needed. Only
# eps_reconciliation/basic_eps_reconciliation, pretax_to_net_income, and
# cashflow_activities_sum_to_net_change needed a genuinely looser quarterly tolerance -
# quarterly tax true-ups, seasonality, and smaller per-quarter denominators produce
# measurably more legitimate divergence than a full fiscal year smooths out (p90 relative
# error 25-33% vs annual's clean single digits). Tuned to land in the same ~8-11%
# flag-rate ballpark as this file's other loose-tolerance checks (annual
# cashflow_reconciliation/retained_earnings_rollforward) rather than flagging on
# legitimate quarterly noise.
_QUARTERLY_EPS_TOLERANCE_PCT = 0.30
_QUARTERLY_EPS_TOLERANCE_FLOOR = 250_000.0
_QUARTERLY_PRETAX_NET_INCOME_TOLERANCE_PCT = 0.30
_QUARTERLY_PRETAX_NET_INCOME_TOLERANCE_FLOOR = 250_000.0
_QUARTERLY_NET_CHANGE_CASH_TOLERANCE_PCT = 0.20
_QUARTERLY_NET_CHANGE_CASH_TOLERANCE_FLOOR = 500_000.0

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


class TieOutSharedMixin:
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
    ) -> None:
        """Shared implementation for the 4 Round 5 sign-flip guard checks below - `field`
        should always be >= 0 (a non-cash addback or cash outflow magnitude), same
        "loader-side abs() fix, DB-side regression guard" pairing every other Round 5 check
        uses. Not a generic helper other rounds should extend - kept private/narrow like the
        rest of this file's single-purpose check methods.
        """
        try:
            order_cols = (
                "b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" if quarterly else "b.symbol, b.fiscal_year DESC"
            )
            quarter_col = ", b.fiscal_quarter" if quarterly else ""
            cur.execute(
                f"""
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year{quarter_col}, b.{field}
                FROM {table} b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.{field} IS NOT NULL
                ORDER BY {order_cols}
                """
            )
            flagged = []
            for row in cur.fetchall():
                value = float(row[field])
                if value < 0:
                    example = {"symbol": row["symbol"], "fiscal_year": row["fiscal_year"], field: value}
                    if quarterly:
                        example["fiscal_quarter"] = row["fiscal_quarter"]
                    flagged.append(example)
            if flagged:
                flagged.sort(key=lambda r: r[field])
                unit = "symbol/quarter(s)" if quarterly else "symbol(s)"
                self.log(
                    check_name,
                    WARN,
                    table,
                    f"{len(flagged)} {unit} have negative {field} (should always be >= 0)",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] {check_name} failed: {e}", exc_info=True)
            self.log(
                check_name,
                ERROR,
                table,
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def _check_shares_outstanding_dei_plausible_scale(
        self, cur: Any, *, table: str, check_name: str, quarterly: bool
    ) -> None:
        """Shared implementation for the annual/quarterly shares_outstanding_dei scale-guard
        checks below."""
        try:
            order_cols = (
                "b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" if quarterly else "b.symbol, b.fiscal_year DESC"
            )
            quarter_col = ", b.fiscal_quarter" if quarterly else ""
            cur.execute(
                f"""
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year{quarter_col}, b.shares_outstanding_dei
                FROM {table} b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.shares_outstanding_dei IS NOT NULL
                  AND b.shares_outstanding_dei > 0
                ORDER BY {order_cols}
                """
            )
            flagged = []
            for row in cur.fetchall():
                value = float(row["shares_outstanding_dei"])
                if value < _MIN_PLAUSIBLE_SHARES_OUTSTANDING or value > _MAX_PLAUSIBLE_SHARES_OUTSTANDING:
                    example = {
                        "symbol": row["symbol"],
                        "fiscal_year": row["fiscal_year"],
                        "shares_outstanding_dei": value,
                    }
                    if quarterly:
                        example["fiscal_quarter"] = row["fiscal_quarter"]
                    flagged.append(example)
            if flagged:
                flagged.sort(key=lambda r: r["shares_outstanding_dei"], reverse=True)
                unit = "symbol/quarter(s)" if quarterly else "symbol(s)"
                self.log(
                    check_name,
                    WARN,
                    table,
                    f"{len(flagged)} {unit} have an implausible shares_outstanding_dei "
                    f"(outside [{_MIN_PLAUSIBLE_SHARES_OUTSTANDING:,}, "
                    f"{_MAX_PLAUSIBLE_SHARES_OUTSTANDING:,}]) - likely a filer/filing-agent "
                    "XBRL tagging error, same class as EEFT's FY2020 case.",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] {check_name} failed: {e}", exc_info=True)
            self.log(
                check_name,
                ERROR,
                table,
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )
