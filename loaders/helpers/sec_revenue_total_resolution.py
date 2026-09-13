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
    sub-line here, so give revenues_net_of_interest_expense unconditional priority over it
    regardless of magnitude, independent of which one this loop happens to process first.
    Every other pair in the candidate group (sales_revenue_net/regulated_operating_revenue/
    etc.) is untouched by this special case - see
    tests/unit/test_sec_revenues_net_of_interest_expense_beats_gross_revenues.py and
    tests/unit/test_sec_sales_revenue_net_magnitude_resolves_over_small_revenues.py.
    """
    if db_field not in revenue_total_best and db_field in row:
        existing = row[db_field]
        if isinstance(existing, (int, float, Decimal)):
            revenue_total_best[db_field] = float(existing)

    if not (isinstance(value, (int, float, Decimal)) and float(value) > 0):
        return

    fvalue = float(value)
    current_best = revenue_total_best.get(db_field)
    current_source = revenue_total_source.get(db_field)

    if sec_field == "revenues" and current_source == "revenues_net_of_interest_expense":
        return  # never let the gross sub-line overwrite the real net total

    is_net_of_interest_override = sec_field == "revenues_net_of_interest_expense" and current_source == "revenues"
    if is_net_of_interest_override or current_best is None or fvalue > current_best:
        revenue_total_best[db_field] = fvalue
        revenue_total_source[db_field] = sec_field
        row[db_field] = value


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


def reit_fallback_existing_value_protected(existing: Any, candidate: Any) -> bool:
    """True if `existing` (already in "revenue") should be protected from the REIT/insurance/
    depository ASC-606 fallback concept's `candidate` value - i.e. the sec_base.py transform()
    condition that used to just be `float(existing) < float(candidate)` (the CLDT fix: only
    protect existing when it isn't already smaller). Extended 2026-09-13 for the MKZR shape
    (see _is_reit_scale_tag_error): existing being bigger doesn't protect it when existing/
    candidate are themselves a clean power-of-ten decimals-tag-error pair.
    """
    if not (isinstance(existing, (int, float, Decimal)) and isinstance(candidate, (int, float, Decimal))):
        return True
    e, c = float(existing), float(candidate)
    return not (e < c or _is_reit_scale_tag_error(e, c))


def asc606_existing_value_outranks_candidate(existing: Any, candidate: Any) -> bool:
    """True if `existing` (already in "revenue") is a genuinely larger, uncorrupted total that
    the CHTR/HTLD/ANDE guard (2026-08-31) should protect from an ASC-606 `candidate` -
    i.e. the sec_base.py transform() condition that used to just be
    `float(existing) > float(candidate)`. Extended 2026-09-13 for the MKZR shape (see
    _is_reit_scale_tag_error): existing being bigger doesn't make it the real total when
    existing/candidate are a clean power-of-ten decimals-tag-error pair (existing itself
    corrupted via a _reit_exclusive_fields concept processed earlier - see
    reit_fallback_existing_value_protected above for the full MKZR shape).
    """
    if not (isinstance(existing, (int, float, Decimal)) and isinstance(candidate, (int, float, Decimal))):
        return False
    e, c = float(existing), float(candidate)
    return e > c and not _is_reit_scale_tag_error(e, c)
