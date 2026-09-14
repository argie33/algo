"""Magnitude/priority resolution among SEC XBRL revenue-total candidate concepts,
extracted from sec_base.py (2026-09-13, file-size ratchet: that file sits at the
2000-line hard ceiling, zero growth tolerance - see check_file_size_ratchet.py).

See loaders.helpers.sec_base._REVENUE_TOTAL_CANDIDATE_FIELDS for the full history of why
these specific concepts (revenues/insurance_revenue/revenues_net_of_interest_expense/
interest_revenue_expense/sales_revenue_net/sales_revenue_goods_net/
regulated_operating_revenue/regulated_and_unregulated_operating_revenue) need
magnitude-based resolution instead of the general first-populated-wins/fallback-only rule
the rest of that loop uses: for most pairs, "a real consolidated total is never smaller
than a genuine sub-line of itself" holds, so the largest real positive candidate wins.
"""

from decimal import Decimal
from typing import Any


def resolve_revenue_total_candidate(
    sec_field: str,
    value: Any,
    db_field: str,
    row: dict[str, Any],
    revenue_total_best: dict[str, float],
    revenue_total_source: dict[str, str],
) -> None:
    """Update `row[db_field]`/`revenue_total_best`/`revenue_total_source` in place for one
    revenue-total candidate concept's value.

    Seed step: if this db_field already holds a value from a prior (non-magnitude) write
    - e.g. a mortgage REIT's interest_income_operating - seed revenue_total_best from it so
    this group only ever OVERWRITES with a larger positive candidate, never blind to what's
    already there.

    AMP/SF FIX (2026-09-13, /goal scoring-accuracy audit): "revenues_net_of_interest_expense"
    is a NET-DOWN of "revenues" for filers reporting both, not an alternative/larger total -
    live-confirmed via AMP's own FY2025 10-K calculation linkbase declaring
    RevenuesNetOfInterestExpense = Revenues - InterestExpenseDeposits ($18.480B =
    $18.911B - $431M), independently reconfirmed via SF/Stifel Financial's real SEC
    companyfacts ($5.530B vs $6.348B). The general "biggest real positive wins" rule this
    function otherwise applies is backwards for this one pair - "revenues" is the gross
    sub-line here, so give revenues_net_of_interest_expense priority over it regardless of
    magnitude, independent of which one this loop happens to process first. Every other pair
    in the candidate group (sales_revenue_net/regulated_operating_revenue/etc.) is untouched
    by this special case - see
    tests/unit/test_sec_revenues_net_of_interest_expense_beats_gross_revenues.py and
    tests/unit/test_sec_sales_revenue_net_magnitude_resolves_over_small_revenues.py.

    PLAUSIBILITY-GATED (2026-09-13, /goal quarantine-backlog audit): the override above was
    unconditional, and that's too broad - live-confirmed via AMZE's real SEC companyfacts
    JSON: FY2022 real "Revenues" = $2,860,001 (exactly equal to the sum of AMZE's own
    correctly-extracted quarterly revenue facts, $929,125+$1,019,377+$535,584+$375,915), but
    the filer ALSO tags "RevenuesNetOfInterestExpense" = $13,750 for the same period - not a
    genuine net-of-interest-expense total (AMZE has no banking/deposit business at all), but
    a filer-side XBRL tagging error: several unrelated concepts in AMZE's own companyfacts
    (DeferredRevenueRevenueRecognized1, IncreaseDecreaseInDeferredRevenue,
    ContractWithCustomerLiabilityRevenueRecognized) share this exact same $13,750 value,
    the signature of one stray number reused across mistagged elements, not a real
    consolidated total. The unconditional override let this ~208x-too-small garbage value
    permanently clobber the correct annual revenue, then fed the
    quarterly_revenue_sum_vs_annual_extreme DataPatrol check's "annual figure is the broken
    one" quarantine for AMZE (and, by the same mechanism, other symbols in that 81-symbol
    backlog). A genuine net-of-interest-expense relationship (AMP: 97.7% of gross; SF: 87.1%
    of gross) never approaches this kind of falloff, so the override now only fires when the
    net candidate is at least `_NET_OF_INTEREST_PLAUSIBLE_RATIO` of the gross one - otherwise
    the pair falls through to the normal magnitude rule (largest real positive wins), which
    correctly keeps AMZE's real, larger "revenues" figure. See
    tests/unit/test_sec_revenues_net_of_interest_expense_implausible_ratio_rejected.py.
    """
    if db_field not in revenue_total_best and db_field in row:
        existing = row[db_field]
        if isinstance(existing, (int, float, Decimal)):
            revenue_total_best[db_field] = float(existing)

    # WIDENED 2026-09-13 (goal session: quarantine-backlog empirical verification, FENC
    # live-confirmed via real SEC companyfacts JSON): this used to reject ANY value <= 0,
    # including a genuinely correct revenue of exactly $0 (FENC, a pre-revenue biotech,
    # FY2020 Q1-Q3: real reported revenue is $0). Because 0 never reached `row[db_field]`,
    # a stale, wrong, non-zero value already sitting in the DB from an earlier bad
    # extraction could never be corrected by ANY later reload - the correct value was
    # filtered out before it ever had a chance to overwrite anything, permanently masking
    # the bug instead of fixing it. Now accepts 0 (a real, valid revenue total) while still
    # rejecting negative values (revenue is never negative in this schema's convention).
    # Safe for every existing candidate in this group: the seed step above and the
    # net-of-interest override below both already require a POSITIVE existing/candidate
    # value before acting, so a 0 candidate can only ever win when nothing better (no
    # larger positive candidate) is present for that fiscal year - it can never silently
    # clobber a real, larger, already-correct total, only fill a genuine zero-revenue gap
    # that used to be permanently unfixable. See
    # tests/unit/test_sec_revenue_total_candidate_accepts_genuine_zero_20260913.py.
    if not isinstance(value, (int, float, Decimal)):
        return
    if float(value) < 0:
        # BENF FIX (2026-09-14, quarantine-backlog continuation): mark that a REAL total-
        # revenue concept was seen but rejected for being negative (revenue is never negative
        # in this schema's convention, per the comment above) - so sec_base.py's fallback-only
        # single-line concepts (InterestIncomeOperating/InterestAndDividendIncomeOperating)
        # know a genuine total already exists for this filer/year and must not silently
        # substitute their own much-smaller positive sub-line as if it were the total.
        # Live-confirmed via Beneficient (BENF), a trust-structure filer whose real annual
        # "Revenues" legitimately goes negative from fair-value losses (-$98.696M FY2024): that
        # negative fact was silently discarded here before this fix, and
        # InterestIncomeOperating's tiny, unrelated $457,000 interest-income sub-line won
        # "revenue" by default instead, understating a real ~$99M loss as if BENF had almost no
        # revenue at all. This string is a private contract with sec_base.py's fallback-only
        # check - see that file's own comment at the read site for the other half of this fix.
        revenue_total_source[db_field] = "negative_total_rejected"
        return

    fvalue = float(value)
    current_best = revenue_total_best.get(db_field)
    current_source = revenue_total_source.get(db_field)

    if sec_field == "revenues" and current_source == "revenues_net_of_interest_expense":
        net_val = current_best
        if net_val is not None and net_val >= _NET_OF_INTEREST_PLAUSIBLE_RATIO * fvalue:
            return  # a genuine net-of-interest-expense total - never let the gross sub-line overwrite it
        # net_val is implausibly small relative to this incoming gross figure (filer tagging
        # error, not a real net-down) - fall through to the normal magnitude rule below.

    is_net_of_interest_override = False
    if sec_field == "revenues_net_of_interest_expense" and current_source == "revenues":
        gross_val = current_best
        if gross_val is not None and gross_val > 0 and fvalue >= _NET_OF_INTEREST_PLAUSIBLE_RATIO * gross_val:
            is_net_of_interest_override = True
        # else: this net value is implausibly small relative to the gross total already on
        # file (filer tagging error) - don't override; the normal magnitude rule below will
        # correctly leave the larger, real gross figure in place.

    if is_net_of_interest_override or current_best is None or fvalue > current_best:
        revenue_total_best[db_field] = fvalue
        revenue_total_source[db_field] = sec_field
        row[db_field] = value


# A genuine "net of interest expense" total is a modest deduction from its gross counterpart
# (AMP: 97.7%, SF: 87.1% of gross) - never a near-total wipeout. 0.5 comfortably separates
# both real cases from AMZE's 0.48% (garbage-tag) case with wide margin on both sides.
_NET_OF_INTEREST_PLAUSIBLE_RATIO = 0.5


def _is_reit_scale_tag_error(existing_val: Any, candidate_val: Any) -> bool:
    """MKZR shape (ADDED 2026-09-13, goal session: MKZR revenue investigation): MacKenzie
    Realty Capital (SIC 6798) has several OperatingLeaseLeaseIncome facts that are a
    filer-side 1,000,000x decimals-tag error, e.g. FY2026 Q3 OperatingLeaseLeaseIncome
    reports $5,441,504,000,000 for the IDENTICAL period where
    revenue_from_contract_with_customer_excluding_assessed_tax correctly reports $5,441,504.
    A clean power-of-10 ratio (delegated to
    sec_statements_entry_resolution._is_power_of_ten_scale_outlier, extended to also
    recognize 1,000,000x) distinguishes this shape from a real larger/smaller total without
    misfiring on CLDT (~5,801x), WAFDP (~23x), or CHTR/HTLD/ANDE (~7x-61x) - none of those
    are clean power-of-ten ratios.
    """
    from utils.external.sec_statements_entry_resolution import _is_power_of_ten_scale_outlier

    return _is_power_of_ten_scale_outlier(existing_val, candidate_val)


def asc606_existing_value_outranks_candidate(existing: Any, candidate: Any) -> bool:
    """True if `existing` (already in "revenue") is a genuinely larger, uncorrupted total that
    the CHTR/HTLD/ANDE guard (2026-08-31) should protect from an ASC-606 `candidate` -
    i.e. the sec_base.py transform() condition that used to just be
    `float(existing) > float(candidate)`. Extended 2026-09-13 for the MKZR shape (see
    _is_reit_scale_tag_error): existing being bigger doesn't make it the real total when
    existing/candidate are a clean power-of-ten decimals-tag-error pair (existing itself
    corrupted via a _reit_exclusive_fields concept processed earlier - see
    loaders/helpers/sec_reit_exclusive_scale_guard.py's should_skip_reit_only_fallback_field
    and reject_reit_exclusive_scale_mismatch for the full MKZR shape).
    """
    if not (isinstance(existing, (int, float, Decimal)) and isinstance(candidate, (int, float, Decimal))):
        return False
    e, c = float(existing), float(candidate)
    return e > c and not _is_reit_scale_tag_error(e, c)
