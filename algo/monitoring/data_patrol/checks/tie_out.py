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

Income-statement chain (revenue - total operating expenses ~= operating_income) was
reconsidered and PARTIALLY added 2026-09-07 once `operating_expenses` (SG&A) extraction
landed (see check_operating_income_upper_bound below) - but it remains a one-directional
upper-bound sanity check, not a full identity: `operating_expenses` covers SG&A only, not
R&D/D&A-when-broken-out/restructuring/impairments/other opex lines, all of which also
reduce operating_income further but aren't tracked as separate summable columns here. The
original objection (no single "total operating expenses" column to assemble a strict
identity) still holds - what changed is that a partial term is now enough to build a
one-sided bound (operating_income can only be LOWER than gross_profit - operating_expenses,
never higher, since further real expenses only subtract more) rather than a two-sided
identity.

Round 3/4 (2026-09-07 evening, goal: "figure out all the ones we really should and want to
have if we could and build out all that we need" - a live-DB schema introspection of all
six statement tables (annual + quarterly balance sheet/income statement/cash flow) sized
the realistic ceiling at ~48 checks. This session had HEAVY concurrent-session load on this
exact file - several sessions (including this one's own earlier, partially-lost attempts,
recovered via isolated worktrees) landed overlapping pieces of the same plan: inventory_le_
current_assets, a real noncontrolling_interest column (fixing check_balance_sheet_identity's
~15% NCI gap - see that check's own docstring), and 10 quarterly ports (gross_profit_
identity, free_cash_flow_identity, diluted_ge_basic_shares, plus 7 Batch-C-style structural
checks: inventory/accounts_receivable/ppe_net/short_term_debt/operating_lease_liability/
finance_lease_liability/diluted_eps vs. their quarterly parent totals) all landed before
this final pass. Landed 47 total - one short of the ~48 estimate because quarterly
cashflow_reconciliation was investigated and REJECTED (see below), the same "don't force a
check that doesn't hold" call already made above for segment-sum-to-consolidated and the
full operating-income identity.

Remaining annual structural checks added this pass (6): accounts_receivable<=current_assets,
ppe_net<=total_assets, short_term_debt<=current_liabilities, operating_lease_liability<=
total_liabilities, finance_lease_liability<=total_liabilities, diluted_eps<=earnings_per_
share (ASC 260 antidilution rule - a filer may never report a diluted per-share figure MORE
favorable than basic, whether the period was profitable or a loss; verified this holds
correctly for both signs using a single signed inequality diluted_eps - earnings_per_share >
tolerance, not a separate branch per sign - live-checked at pct=2%/floor=$0.01, 13/2,964
violations, same clean noise floor as the other structural checks, largely magnitude-swap
bugs like RETO (diluted -0.16 vs basic -377.10, a ~2,356x mismatch)).

Remaining quarterly ports added this pass (12 of the pre-existing annual checks, keyed by
(symbol, fiscal_year, fiscal_quarter) instead of (symbol, fiscal_year)): balance_sheet_
identity, eps_reconciliation, basic_eps_reconciliation, pretax_to_net_income, cashflow_
activities_sum_to_net_change, current_assets_le_total_assets, current_liabilities_le_total_
liabilities, long_term_debt_le_total_liabilities, operating_income_upper_bound, goodwill_le_
total_assets, accounts_payable_le_current_liabilities, cash_le_current_assets. NOT ported,
with reasons:
- quick_ratio_le_current_ratio: source table quality_metrics has no quarterly variant
  (one row per symbol, no fiscal_quarter column) - nothing to port against.
- retained_earnings_rollforward: quarterly_balance_sheet had no retained_earnings column
  when this pass's live-feasibility work was done (only annual_balance_sheet had it, via
  migration 1234). A concurrent session's WIP (migration 1266, uncommitted as of this
  writing) may close this gap - re-evaluate porting this check once that lands and is
  confirmed live, don't assume it yet.
- cashflow_reconciliation (prior-period cash + OCF+ICF+FCF ~= curr-period cash): INVESTIGATED
  AND REJECTED. First confirmed quarterly OCF/ICF/FCF are genuinely quarter-discrete, not
  FY-to-date cumulative (loaders/helpers/financial_statements_q4_sweeps.py's
  `_sweep_derive_missing_q4_cash_flow` derives a missing Q4 as FY_annual - (Q1+Q2+Q3), which
  is only a valid identity if Q1-Q3 are each already discrete quarterly flows - confirmed via
  929 successfully-derived rows) - so the identity itself is the right shape in principle.
  But a live feasibility scan of prior_quarter_cash + OCF+ICF+FCF vs curr_quarter_cash across
  3,927 comparable symbol/quarters found p50 relative error = 22%, p90 = 144%, p99 = 1,532% -
  nowhere near noise-level even at the loosest tolerance this file uses anywhere (annual
  cashflow's own 10%, retained_earnings' 25%). Root cause not tracked down (candidates:
  quarterly restatement/re-presentation between filings, or a quarter-boundary cash-concept
  mismatch the annual check's year-over-year comparison doesn't hit as hard) - flagging this
  as a "known-broken, needs its own investigation" gap rather than shipping a check with a
  >50% false-positive rate that would train operators to ignore WARN alerts from this file.

eps_reconciliation/basic_eps_reconciliation and pretax_to_net_income needed a genuinely
looser quarterly tolerance than their annual siblings (_QUARTERLY_EPS_TOLERANCE_PCT/
_QUARTERLY_PRETAX_NET_INCOME_TOLERANCE_PCT, both 30% vs annual's 15%/10%) - quarterly p90
relative error is 25-33% (vs annual's clean single-digit percentiles), quarterly tax
true-ups/seasonality/smaller per-quarter denominators genuinely produce more legitimate
divergence than a full fiscal year smooths out. Tuned to land in the same ~8-11% flag-rate
ballpark as this file's other loose-tolerance checks rather than either flagging on
legitimate quarterly noise or being tuned so loose it stops catching anything.
cashflow_activities_sum_to_net_change similarly loosened to 20% (from annual's 10%) -
noisier than annual but cleaner than the EPS/pretax pair. Every other ported check in this
batch reuses its annual sibling's tolerance constant unchanged - all live-feasibility-
checked clean at that same tolerance on quarterly data too.
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


class TieOutChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_balance_sheet_identity(cur)
        self.check_quarterly_balance_sheet_identity(cur)
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
        self.check_operating_income_upper_bound(cur)
        self.check_goodwill_le_total_assets(cur)
        self.check_accounts_payable_le_current_liabilities(cur)
        self.check_cash_le_current_assets(cur)
        self.check_inventory_le_current_assets(cur)
        self.check_quarterly_gross_profit_identity(cur)
        self.check_quarterly_free_cash_flow_identity(cur)
        self.check_quarterly_diluted_ge_basic_shares(cur)
        self.check_quarterly_inventory_le_current_assets(cur)
        self.check_quarterly_accounts_receivable_le_current_assets(cur)
        self.check_quarterly_ppe_net_le_total_assets(cur)
        self.check_quarterly_short_term_debt_le_current_liabilities(cur)
        self.check_quarterly_operating_lease_liability_le_total_liabilities(cur)
        self.check_quarterly_finance_lease_liability_le_total_liabilities(cur)
        self.check_quarterly_diluted_eps_le_basic_eps(cur)
        # Batch A (Round 4): remaining new annual structural checks
        self.check_accounts_receivable_le_current_assets(cur)
        self.check_ppe_net_le_total_assets(cur)
        self.check_short_term_debt_le_current_liabilities(cur)
        self.check_operating_lease_liability_le_total_liabilities(cur)
        self.check_finance_lease_liability_le_total_liabilities(cur)
        self.check_diluted_eps_le_basic_eps(cur)
        # Batch B (Round 4): remaining existing checks ported to quarterly tables
        # (check_quarterly_balance_sheet_identity already called above - landed via a
        # concurrent session before this round's rebase)
        self.check_quarterly_eps_reconciliation(cur)
        self.check_quarterly_basic_eps_reconciliation(cur)
        self.check_quarterly_pretax_to_net_income(cur)
        self.check_quarterly_cashflow_activities_sum_to_net_change(cur)
        self.check_quarterly_current_assets_le_total_assets(cur)
        self.check_quarterly_current_liabilities_le_total_liabilities(cur)
        self.check_quarterly_long_term_debt_le_total_liabilities(cur)
        self.check_quarterly_operating_income_upper_bound(cur)
        self.check_quarterly_goodwill_le_total_assets(cur)
        self.check_quarterly_accounts_payable_le_current_liabilities(cur)
        self.check_quarterly_cash_le_current_assets(cur)
        # Round 5 (2026-09-07, goal: "run all the tie-outs" buildout): guard checks for the
        # 3 fields found live-verified-broken this round (sign-flip fix + dei scale guard,
        # see load_financial_statements.py) - these fire on ANY row the fix hasn't reached
        # yet (pre-reload) or that somehow bypasses the loader-side guard in the future.
        self.check_stock_based_compensation_nonnegative(cur)
        self.check_quarterly_stock_based_compensation_nonnegative(cur)
        self.check_common_stock_repurchased_nonnegative(cur)
        self.check_quarterly_common_stock_repurchased_nonnegative(cur)
        self.check_shares_outstanding_dei_plausible_scale(cur)
        self.check_quarterly_shares_outstanding_dei_plausible_scale(cur)
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
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.total_assets, b.total_liabilities,
                    b.stockholders_equity, b.noncontrolling_interest
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
                assets, liabilities, equity, nci = (
                    float(row["total_assets"]),
                    float(row["total_liabilities"]),
                    float(row["stockholders_equity"]),
                    float(row["noncontrolling_interest"] or 0),
                )
                residual = assets - (liabilities + equity + nci)
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
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter, b.total_assets, b.total_liabilities,
                    b.stockholders_equity, b.noncontrolling_interest
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
                assets, liabilities, equity, nci = (
                    float(row["total_assets"]),
                    float(row["total_liabilities"]),
                    float(row["stockholders_equity"]),
                    float(row["noncontrolling_interest"] or 0),
                )
                residual = assets - (liabilities + equity + nci)
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
                    f"stockholders_equity + noncontrolling_interest beyond "
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

    def check_quarterly_inventory_le_current_assets(self, cur: Any) -> None:
        """inventory <= current_assets (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of check_inventory_le_current_assets -
        reuses the annual _INVENTORY_TOLERANCE_PCT unchanged (live-verified 2/2,800).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter, b.current_assets, b.inventory
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_assets IS NOT NULL
                  AND b.inventory IS NOT NULL
                  AND b.current_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
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
                            "fiscal_quarter": row["fiscal_quarter"],
                            "current_assets": current_assets,
                            "inventory": inventory,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_inventory_le_current_assets",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail inventory <= current_assets "
                    f"beyond {_INVENTORY_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_inventory_le_current_assets failed: {e}", exc_info=True)
            self.log(
                "quarterly_inventory_le_current_assets",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_accounts_receivable_le_current_assets(self, cur: Any) -> None:
        """accounts_receivable <= current_assets (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_accounts_receivable_le_current_assets - reuses the annual
        _ACCOUNTS_RECEIVABLE_TOLERANCE_PCT unchanged (live-verified 5/3,786).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter,
                    b.current_assets, b.accounts_receivable
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_assets IS NOT NULL
                  AND b.accounts_receivable IS NOT NULL
                  AND b.current_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
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
                            "fiscal_quarter": row["fiscal_quarter"],
                            "current_assets": current_assets,
                            "accounts_receivable": accounts_receivable,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_accounts_receivable_le_current_assets",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail accounts_receivable <= "
                    f"current_assets beyond {_ACCOUNTS_RECEIVABLE_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_accounts_receivable_le_current_assets failed: {e}", exc_info=True)
            self.log(
                "quarterly_accounts_receivable_le_current_assets",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_ppe_net_le_total_assets(self, cur: Any) -> None:
        """ppe_net <= total_assets (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of check_ppe_net_le_total_assets - reuses
        the annual _PPE_NET_TOLERANCE_PCT unchanged (live-verified 4/4,757).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter, b.total_assets, b.ppe_net
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_assets IS NOT NULL
                  AND b.ppe_net IS NOT NULL
                  AND b.total_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
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
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_assets": total_assets,
                            "ppe_net": ppe_net,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_ppe_net_le_total_assets",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail ppe_net <= total_assets beyond "
                    f"{_PPE_NET_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_ppe_net_le_total_assets failed: {e}", exc_info=True)
            self.log(
                "quarterly_ppe_net_le_total_assets",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_short_term_debt_le_current_liabilities(self, cur: Any) -> None:
        """short_term_debt <= current_liabilities (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_short_term_debt_le_current_liabilities - reuses the annual
        _SHORT_TERM_DEBT_TOLERANCE_PCT unchanged (live-verified 44/1,945, the noisiest of
        the Batch C ports at 2.3% but still a small minority, comparable to
        long_term_debt_le_total_liabilities's own noise floor).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter,
                    b.current_liabilities, b.short_term_debt
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_liabilities IS NOT NULL
                  AND b.short_term_debt IS NOT NULL
                  AND b.current_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                current_liabilities, short_term_debt = (
                    float(row["current_liabilities"]),
                    float(row["short_term_debt"]),
                )
                residual = short_term_debt - current_liabilities
                tolerance = abs(current_liabilities) * _SHORT_TERM_DEBT_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "current_liabilities": current_liabilities,
                            "short_term_debt": short_term_debt,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_short_term_debt_le_current_liabilities",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail short_term_debt <= "
                    f"current_liabilities beyond {_SHORT_TERM_DEBT_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_short_term_debt_le_current_liabilities failed: {e}", exc_info=True)
            self.log(
                "quarterly_short_term_debt_le_current_liabilities",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_operating_lease_liability_le_total_liabilities(self, cur: Any) -> None:
        """operating_lease_liability <= total_liabilities (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_operating_lease_liability_le_total_liabilities - reuses the annual
        _OPERATING_LEASE_LIABILITY_TOLERANCE_PCT unchanged (live-verified 3/4,326).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter,
                    b.total_liabilities, b.operating_lease_liability
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.operating_lease_liability IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_liabilities, operating_lease_liability = (
                    float(row["total_liabilities"]),
                    float(row["operating_lease_liability"]),
                )
                residual = operating_lease_liability - total_liabilities
                tolerance = abs(total_liabilities) * _OPERATING_LEASE_LIABILITY_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_liabilities": total_liabilities,
                            "operating_lease_liability": operating_lease_liability,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_operating_lease_liability_le_total_liabilities",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail operating_lease_liability <= "
                    f"total_liabilities beyond {_OPERATING_LEASE_LIABILITY_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(
                f"[TieOutChecker] quarterly_operating_lease_liability_le_total_liabilities failed: {e}", exc_info=True
            )
            self.log(
                "quarterly_operating_lease_liability_le_total_liabilities",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_finance_lease_liability_le_total_liabilities(self, cur: Any) -> None:
        """finance_lease_liability <= total_liabilities (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_finance_lease_liability_le_total_liabilities - reuses the annual
        _FINANCE_LEASE_LIABILITY_TOLERANCE_PCT unchanged (live-verified 3/1,652).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter,
                    b.total_liabilities, b.finance_lease_liability
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.finance_lease_liability IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_liabilities, finance_lease_liability = (
                    float(row["total_liabilities"]),
                    float(row["finance_lease_liability"]),
                )
                residual = finance_lease_liability - total_liabilities
                tolerance = abs(total_liabilities) * _FINANCE_LEASE_LIABILITY_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_liabilities": total_liabilities,
                            "finance_lease_liability": finance_lease_liability,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_finance_lease_liability_le_total_liabilities",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail finance_lease_liability <= "
                    f"total_liabilities beyond {_FINANCE_LEASE_LIABILITY_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(
                f"[TieOutChecker] quarterly_finance_lease_liability_le_total_liabilities failed: {e}", exc_info=True
            )
            self.log(
                "quarterly_finance_lease_liability_le_total_liabilities",
                ERROR,
                "quarterly_balance_sheet",
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

    def check_short_term_debt_le_current_liabilities(self, cur: Any) -> None:
        """short_term_debt <= current_liabilities (both from annual_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Same subset/category structural inequality as
        long_term_debt_le_total_liabilities above, applied to the current-liability side -
        short_term_debt is one liability line item, never the whole current-liability side.
        See _SHORT_TERM_DEBT_TOLERANCE_PCT's own comment for the live-feasibility numbers
        (64/2,012 annual).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.current_liabilities, b.short_term_debt
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_liabilities IS NOT NULL
                  AND b.short_term_debt IS NOT NULL
                  AND b.current_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                current_liabilities, short_term_debt = (
                    float(row["current_liabilities"]),
                    float(row["short_term_debt"]),
                )
                residual = short_term_debt - current_liabilities
                tolerance = abs(current_liabilities) * _SHORT_TERM_DEBT_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "current_liabilities": current_liabilities,
                            "short_term_debt": short_term_debt,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "short_term_debt_le_current_liabilities",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail short_term_debt <= current_liabilities "
                    f"beyond {_SHORT_TERM_DEBT_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] short_term_debt_le_current_liabilities failed: {e}", exc_info=True)
            self.log(
                "short_term_debt_le_current_liabilities",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_operating_lease_liability_le_total_liabilities(self, cur: Any) -> None:
        """operating_lease_liability <= total_liabilities (both from annual_balance_sheet,
        same row).

        ADDED 2026-09-07 (Round 3). Same subset/category structural inequality as
        long_term_debt_le_total_liabilities above - operating_lease_liability is one
        liability line item, never the whole liability side. See
        _OPERATING_LEASE_LIABILITY_TOLERANCE_PCT's own comment for the live-feasibility
        numbers (7/4,471).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.total_liabilities, b.operating_lease_liability
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.operating_lease_liability IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_liabilities, operating_lease_liability = (
                    float(row["total_liabilities"]),
                    float(row["operating_lease_liability"]),
                )
                residual = operating_lease_liability - total_liabilities
                tolerance = abs(total_liabilities) * _OPERATING_LEASE_LIABILITY_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "total_liabilities": total_liabilities,
                            "operating_lease_liability": operating_lease_liability,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "operating_lease_liability_le_total_liabilities",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail operating_lease_liability <= "
                    f"total_liabilities beyond {_OPERATING_LEASE_LIABILITY_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] operating_lease_liability_le_total_liabilities failed: {e}", exc_info=True)
            self.log(
                "operating_lease_liability_le_total_liabilities",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_finance_lease_liability_le_total_liabilities(self, cur: Any) -> None:
        """finance_lease_liability <= total_liabilities (both from annual_balance_sheet,
        same row).

        ADDED 2026-09-07 (Round 3). Same subset/category structural inequality as
        operating_lease_liability_le_total_liabilities above. See
        _FINANCE_LEASE_LIABILITY_TOLERANCE_PCT's own comment for the live-feasibility
        numbers (1/1,663).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.total_liabilities, b.finance_lease_liability
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.finance_lease_liability IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_liabilities, finance_lease_liability = (
                    float(row["total_liabilities"]),
                    float(row["finance_lease_liability"]),
                )
                residual = finance_lease_liability - total_liabilities
                tolerance = abs(total_liabilities) * _FINANCE_LEASE_LIABILITY_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "total_liabilities": total_liabilities,
                            "finance_lease_liability": finance_lease_liability,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "finance_lease_liability_le_total_liabilities",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail finance_lease_liability <= "
                    f"total_liabilities beyond {_FINANCE_LEASE_LIABILITY_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] finance_lease_liability_le_total_liabilities failed: {e}", exc_info=True)
            self.log(
                "finance_lease_liability_le_total_liabilities",
                ERROR,
                "annual_balance_sheet",
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

    def check_quarterly_current_assets_le_total_assets(self, cur: Any) -> None:
        """current_assets <= total_assets (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of check_current_assets_le_total_assets -
        reuses the annual _CURRENT_VS_TOTAL_TOLERANCE_PCT unchanged (live-verified 1/4,634,
        the same SSL magnitude-swap bug the annual check also catches).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter, b.total_assets, b.current_assets
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_assets IS NOT NULL
                  AND b.current_assets IS NOT NULL
                  AND b.total_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
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
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_assets": total_assets,
                            "current_assets": current_assets,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_current_assets_le_total_assets",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail current_assets <= total_assets "
                    f"beyond {_CURRENT_VS_TOTAL_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_current_assets_le_total_assets failed: {e}", exc_info=True)
            self.log(
                "quarterly_current_assets_le_total_assets",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_current_liabilities_le_total_liabilities(self, cur: Any) -> None:
        """current_liabilities <= total_liabilities (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_current_liabilities_le_total_liabilities - reuses the annual
        _CURRENT_VS_TOTAL_TOLERANCE_PCT unchanged (live-verified 4/4,596).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter,
                    b.total_liabilities, b.current_liabilities
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.current_liabilities IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
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
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_liabilities": total_liabilities,
                            "current_liabilities": current_liabilities,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_current_liabilities_le_total_liabilities",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail current_liabilities <= "
                    f"total_liabilities beyond {_CURRENT_VS_TOTAL_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(
                f"[TieOutChecker] quarterly_current_liabilities_le_total_liabilities failed: {e}", exc_info=True
            )
            self.log(
                "quarterly_current_liabilities_le_total_liabilities",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_long_term_debt_le_total_liabilities(self, cur: Any) -> None:
        """long_term_debt <= total_liabilities (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_long_term_debt_le_total_liabilities - reuses the annual
        _LONG_TERM_DEBT_TOLERANCE_PCT unchanged (live-verified 38/4,331, comparable to
        annual's own 64/4,244).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter, b.total_liabilities, b.long_term_debt
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.long_term_debt IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
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
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_liabilities": total_liabilities,
                            "long_term_debt": long_term_debt,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_long_term_debt_le_total_liabilities",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail long_term_debt <= "
                    f"total_liabilities beyond {_LONG_TERM_DEBT_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_long_term_debt_le_total_liabilities failed: {e}", exc_info=True)
            self.log(
                "quarterly_long_term_debt_le_total_liabilities",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

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
