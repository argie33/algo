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
from .tie_out_bounds_annual1 import TieOutBoundsAnnual1Mixin
from .tie_out_bounds_annual2_quarterly1 import TieOutBoundsAnnual2Quarterly1Mixin
from .tie_out_bounds_quarterly2_misc import TieOutBoundsQuarterly2MiscMixin
from .tie_out_identity_annual import TieOutIdentityAnnualMixin
from .tie_out_identity_quarterly import TieOutIdentityQuarterlyMixin
from .tie_out_nonnegative_magnitudes import TieOutNonnegativeMagnitudesMixin
from .tie_out_shared import TieOutSharedMixin

logger = logging.getLogger(__name__)


class TieOutChecker(
    TieOutIdentityAnnualMixin,
    TieOutIdentityQuarterlyMixin,
    TieOutBoundsAnnual1Mixin,
    TieOutBoundsAnnual2Quarterly1Mixin,
    TieOutBoundsQuarterly2MiscMixin,
    TieOutNonnegativeMagnitudesMixin,
    TieOutSharedMixin,
    BaseCheck,
):
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
        # Round 6 (2026-09-08, goal: "check the scores make sense" + tie-out gap sweep):
        # stock_scores has no prior guard that pillar/composite values stay within their
        # percentile-rank contract of [0, 100].
        self.check_stock_scores_bounds(cur)
        # Round 6 (same session): no prior check reconciled quarterly figures against their
        # own annual total at all - live-caught APA's genuine quarterly-revenue duplicate bug.
        self.check_quarterly_revenue_annual_duplicate(cur)
        # Round 7 (2026-09-10, goal: "full XBRL best-practices" review): DQC_0015/US1-style
        # "negative values" guard for balance-sheet magnitude fields that are non-negative by
        # GAAP definition - see tie_out_nonnegative_magnitudes.py's module docstring for why
        # this is a different check class from the X<=Y bound checks above.
        self.check_total_assets_nonnegative(cur)
        self.check_quarterly_total_assets_nonnegative(cur)
        self.check_current_assets_nonnegative(cur)
        self.check_quarterly_current_assets_nonnegative(cur)
        self.check_total_liabilities_nonnegative(cur)
        self.check_quarterly_total_liabilities_nonnegative(cur)
        self.check_current_liabilities_nonnegative(cur)
        self.check_quarterly_current_liabilities_nonnegative(cur)
        self.check_inventory_nonnegative(cur)
        self.check_quarterly_inventory_nonnegative(cur)
        self.check_cash_and_equivalents_nonnegative(cur)
        self.check_quarterly_cash_and_equivalents_nonnegative(cur)
        self.check_accounts_receivable_nonnegative(cur)
        self.check_quarterly_accounts_receivable_nonnegative(cur)
        self.check_ppe_net_nonnegative(cur)
        self.check_quarterly_ppe_net_nonnegative(cur)
        self.check_goodwill_nonnegative(cur)
        self.check_quarterly_goodwill_nonnegative(cur)
        self.check_long_term_debt_nonnegative(cur)
        self.check_quarterly_long_term_debt_nonnegative(cur)
        self.check_short_term_debt_nonnegative(cur)
        self.check_quarterly_short_term_debt_nonnegative(cur)
        self.check_operating_lease_liability_nonnegative(cur)
        self.check_quarterly_operating_lease_liability_nonnegative(cur)
        self.check_finance_lease_liability_nonnegative(cur)
        self.check_quarterly_finance_lease_liability_nonnegative(cur)
        self.check_accounts_payable_nonnegative(cur)
        self.check_quarterly_accounts_payable_nonnegative(cur)
        self.check_cash_and_restricted_cash_combined_nonnegative(cur)
        self.check_quarterly_cash_and_restricted_cash_combined_nonnegative(cur)
        return self.results
