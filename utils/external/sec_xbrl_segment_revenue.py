"""Segment-revenue extraction fallbacks (cross-tab, component-sum, alt-asset-manager) for
XBRLSegmentParser, extracted from utils/external/sec_xbrl_segments.py (2026-09-05, file-size
ratchet: it's a Tier-2 bloater flagged for decomposition; split further into two files - see
sec_xbrl_segment_revenue_2.py for the remaining fallbacks - to stay under the 800-line
new-file cap). Bodies are verbatim, no logic changed - only converted from staticmethods to
plain module functions (they never used `self`/`cls`) and moved file. Called by
XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml, which stays in the main file and
tries each of these in sequence.

`XBRLSegmentParser._dedupe_member_facts`/`._extract_segment_member_values` are accessed via
the sec_xbrl_segments module object at call time (not a direct class import) because moving
just this cluster out - while those two helpers stay on the class, still used by other
methods there too - would otherwise require importing XBRLSegmentParser itself, which
creates a circular import (that class is defined in the very module importing these
functions). `utils.external.sec_xbrl_segments` imports this module at load time, so the
reference below is resolved lazily (inside the function bodies, not at import time).
"""

import logging
import xml.etree.ElementTree as ET
from datetime import date

import utils.external.sec_xbrl_segments as _sxs
from utils.external.sec_xbrl_segments import (
    _ALT_ASSET_MANAGER_REVENUE_COMPONENT_CONCEPTS,
    _BANK_REVENUE_COMPONENT_CONCEPTS,
    _CONSOLIDATION_ITEMS_AXIS_NAMES,
    _CROSS_TAB_ONLY_EXTRA_REVENUE_CONCEPTS,
    _CROSS_TAB_RECONCILIATION_TOLERANCE,
    _NON_ADDITIVE_CONSOLIDATION_MEMBERS,
    _OPERATING_SEGMENTS_AGGREGATE_DIMENSION,
    _OPERATING_SEGMENTS_AGGREGATE_MEMBER,
    _OPERATING_SEGMENTS_MEMBER,
    _REVENUE_CONCEPT_LOCAL_NAMES,
    _local_name,
    _qname_local,
)

logger = logging.getLogger(__name__)


def _extract_cross_tab_segment_revenue(  # noqa: C901
    root: ET.Element, symbol: str, axis_to_use: str
) -> tuple[dict[str, float], str, int] | None:
    """Fallback for filers that tag EVERY segment revenue fact with an additional
    axis alongside the segment axis - no plain single-dimension (or
    OperatingSegmentsMember-paired) segment-total context exists anywhere in the
    filing for any revenue concept, so the primary path in
    extract_segment_revenue_from_xbrl_xml finds nothing.

    Confirmed live against Exxon Mobil's real FY2023/2024/2025 10-K instance
    documents (CIK 34088): segment revenue is tagged three ways per (segment,
    geography) pair - "sales and other operating revenue", "income from equity
    affiliates", and "other revenue" (all ProductOrServiceAxis members, paired
    with StatementGeographicalAxis=US/NonUs) - plus a separate "intersegment sales
    elimination" line tagged via
    ConsolidationItemsAxis=IntersegmentEliminationMember alongside the same
    geography axis. The eliminations line is a reconciling adjustment, not a
    component of the segment's own reportable revenue (same ASC 280 convention
    already applied to the plain "Corporate and Eliminations" sign-based exclusion
    in the caller) - excluding it and summing the three ProductOrServiceAxis
    members across both geography members reproduces Exxon's real consolidated
    revenue to within 0.3-0.5% for all three years.

    XOM also tags a SEPARATE, plain (segment + geography only, no product-type
    axis) breakdown that is NOT the same figure - it's gross of intersegment
    sales rather than net, overstating the real total by ~36%. A filer can tag
    more than one complete-looking breakdown of the same segment revenue, and
    picking the wrong one silently produces a plausible but wrong number - exactly
    the JNJ/KO double-counting bug this parser already had to fix twice (see
    [[sec_xbrl_companyfacts_limitation]]). Rather than guess which axis
    combination is "the" real segment total by member-name pattern matching,
    every candidate combination found in the filing is reconciled against the
    filer's own plain (non-dimensioned) consolidated revenue fact for the
    identical period and only accepted if within
    _CROSS_TAB_RECONCILIATION_TOLERANCE - otherwise this returns None and the
    caller reports data_unavailable, the correct, honest outcome per
    GOVERNANCE's fail-fast principle when no candidate can be trusted.

    Returns (member -> revenue, target_end_date, target_duration_days) for the
    best-reconciled candidate, or None if no candidate reconciles.
    """
    all_contexts: dict[str, tuple[dict[str, str], str | None, str | None]] = {}
    for ctx in root.iter():
        if _local_name(ctx.tag) != "context":
            continue
        ctx_id = ctx.get("id")
        if not ctx_id:
            continue
        dims: dict[str, str] = {}
        start_str = end_str = None
        for child in ctx.iter():
            loc = _local_name(child.tag)
            if loc == "explicitMember":
                dims[_qname_local(child.get("dimension"))] = _qname_local(child.text)
            elif loc == "startDate":
                start_str = (child.text or "").strip() or None
            elif loc == "endDate":
                end_str = (child.text or "").strip() or None
            elif loc == "instant":
                end_str = (child.text or "").strip() or None
        all_contexts[ctx_id] = (dims, start_str, end_str)

    # (segment_member, other_axes_combo, end_date, duration_days, revenue)
    candidates: list[tuple[str, frozenset[str], str, int, float]] = []
    matched_concept: str | None = None
    for concept in _REVENUE_CONCEPT_LOCAL_NAMES + _CROSS_TAB_ONLY_EXTRA_REVENUE_CONCEPTS:
        for elem in root.iter():
            if _local_name(elem.tag) != concept:
                continue
            info = all_contexts.get(elem.get("contextRef", ""))
            if not info:
                continue
            dims, start_str, end_str = info
            if axis_to_use not in dims or not end_str:
                continue

            other_dims = {k: v for k, v in dims.items() if k != axis_to_use}
            consol_axis = next((a for a in _CONSOLIDATION_ITEMS_AXIS_NAMES if a in other_dims), None)
            consol_member = other_dims.get(consol_axis, "") if consol_axis else ""
            if consol_axis and consol_member == _OPERATING_SEGMENTS_MEMBER:
                other_dims.pop(consol_axis)
            elif consol_member in _NON_ADDITIVE_CONSOLIDATION_MEMBERS:
                continue
            if not other_dims:
                continue  # single-dimension after stripping boilerplate - primary path already tried this

            value = elem.text
            if value is None:
                continue
            try:
                revenue = float(value.strip())
            except ValueError:
                continue
            duration_days = 0
            if start_str:
                try:
                    duration_days = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
                except ValueError:
                    duration_days = 0
            candidates.append((dims[axis_to_use], frozenset(other_dims.keys()), end_str, duration_days, revenue))
        if candidates:
            matched_concept = concept
            break

    if not candidates:
        return None

    max_end = max(c[2] for c in candidates)
    same_end = [c for c in candidates if c[2] == max_end]
    max_duration = max(c[3] for c in same_end)
    period_candidates = [c for c in same_end if c[3] == max_duration]

    by_combo: dict[frozenset[str], dict[str, float]] = {}
    for member, other_axes, _end, _duration, revenue_value in period_candidates:
        combo_segments = by_combo.setdefault(other_axes, {})
        combo_segments[member] = combo_segments.get(member, 0.0) + revenue_value

    # Reconciliation ground truth: the filer's own plain, non-dimensioned
    # consolidated revenue fact for the identical period. Try the SAME
    # concept that produced the segment-level candidates first - comparing
    # like-for-like (e.g. summed segment PremiumsEarnedNet against the
    # filer's own plain PremiumsEarnedNet total) rather than against
    # whichever concept happens to be earliest in the general preference
    # order. Confirmed live this matters: Progressive's (PGR) 3 segments
    # sum to its own plain PremiumsEarnedNet total ($81.661B) almost
    # exactly, but always fail reconciliation against plain "Revenues"
    # ($87.671B, ~6.9% higher) because Revenues also includes net
    # investment income and realized gains - real dollars, but not
    # segment-allocated, so segment premium revenue structurally can never
    # foot to total company revenue for an insurer with a large investment
    # portfolio (unlike AIG's ~0.3% residual, where investment income is
    # proportionally small). Falls back to the full preference-order scan
    # if the matched concept itself has no plain fact.
    concept_search_order = list(_REVENUE_CONCEPT_LOCAL_NAMES + _CROSS_TAB_ONLY_EXTRA_REVENUE_CONCEPTS)
    if matched_concept is not None:
        concept_search_order = [matched_concept] + [c for c in concept_search_order if c != matched_concept]

    anchor: float | None = None
    for concept in concept_search_order:
        for elem in root.iter():
            if _local_name(elem.tag) != concept:
                continue
            info = all_contexts.get(elem.get("contextRef", ""))
            if not info:
                continue
            dims, start_str, end_str = info
            if dims or end_str != max_end:
                continue
            if start_str:
                try:
                    d = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
                except ValueError:
                    continue
                if d != max_duration:
                    continue
            value = elem.text
            if value is None:
                continue
            try:
                anchor = float(value.strip())
            except ValueError:
                continue
            break
        if anchor is not None:
            break

    if anchor is None or anchor == 0:
        logger.info(
            f"[{symbol}] Cross-tab segment revenue found candidates but no consolidated anchor to reconcile against - not trusting any candidate."
        )
        return None

    best_combo: frozenset[str] | None = None
    best_segments: dict[str, float] | None = None
    best_error: float | None = None
    for combo, combo_segments in by_combo.items():
        total = sum(combo_segments.values())
        error = abs(total - anchor) / abs(anchor)
        if best_error is None or error < best_error:
            best_error, best_combo, best_segments = error, combo, combo_segments

    if best_error is None or best_error > _CROSS_TAB_RECONCILIATION_TOLERANCE or best_segments is None:
        logger.info(
            f"[{symbol}] Cross-tab segment revenue reconciliation failed: best candidate "
            f"(axes={sorted(best_combo) if best_combo else None}) off by "
            f"{best_error * 100 if best_error is not None else float('nan'):.1f}% vs consolidated "
            f"revenue {anchor:,.0f} - not trusting any candidate."
        )
        return None

    return best_segments, max_end, max_duration


def _extract_component_sum_segment_revenue(  # noqa: C901 -- same reconciliation-discipline shape as the two sibling fallbacks above (_extract_cross_tab_segment_revenue, _extract_single_segment_revenue), both already carry this same suppression for the same reason: real fail-fast discipline (discover candidates, then verify against a plain consolidated anchor) is inherently a few linear steps, not deeply nested logic.
    root: ET.Element,
    context_segment: dict[str, tuple[str, str, str, str | None, bool]],
    axis_to_use: str,
    symbol: str,
) -> tuple[dict[str, float], str, int] | None:
    """Fallback for filers (confirmed live: BOK Financial, Ameris Bancorp, Arbor
    Realty Trust FY2025 10-Ks) that tag segment-level revenue as two SEPARATE
    concepts - see _BANK_REVENUE_COMPONENT_CONCEPTS's module-level comment for why
    this is a distinct, real pattern from every other revenue concept already
    covered, not a duplicate of the cross-tab or single-concept paths.

    The anchor concept (InterestIncomeExpenseNet) is used first to discover which
    segment members exist and which fiscal period to use - the same
    latest-period-wins logic as the primary path in
    extract_segment_revenue_from_xbrl_xml. The secondary concept
    (NoninterestIncome) is then looked up ONLY for that period via the existing
    _extract_segment_member_values helper and added in - a member missing the
    secondary concept is treated as 0 for it (a real segment can legitimately have
    no noninterest income), not excluded outright.

    Reconciled the same way as _extract_cross_tab_segment_revenue: the summed
    segment-level total is compared against the filer's own plain, non-dimensioned
    consolidated total for the SAME two concepts and period, only trusted within
    _CROSS_TAB_RECONCILIATION_TOLERANCE. Confirmed live this correctly separates a
    clean case from a messy one: Ameris Bancorp and Arbor Realty Trust both
    reconcile to within 0.01%, while BOK Financial's real segment total is
    genuinely ~9.5% short of its consolidated total (a "Corporate allocations"
    reconciling adjustment BOKF doesn't tag as its own addable segment member) -
    correctly rejected rather than silently reporting an incomplete total.

    Returns (member -> combined revenue, end_date, duration_days), or None if the
    anchor concept isn't tagged under axis_to_use at all, or the combined total
    doesn't reconcile.
    """
    anchor_concept, secondary_concept = _BANK_REVENUE_COMPONENT_CONCEPTS

    candidate_facts: list[tuple[str, str, int, float, bool]] = []
    for elem in root.iter():
        if _local_name(elem.tag) != anchor_concept:
            continue
        info = context_segment.get(elem.get("contextRef", ""))
        if not info or info[0] != axis_to_use:
            continue
        _axis, member, end_str, start_str, is_boilerplate = info
        value = elem.text
        if value is None:
            continue
        try:
            revenue = float(value.strip())
        except ValueError:
            continue
        duration_days = 0
        if start_str and end_str:
            try:
                duration_days = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
            except ValueError:
                duration_days = 0
        candidate_facts.append((member, end_str, duration_days, revenue, is_boilerplate))

    if not candidate_facts:
        return None

    max_end = max(f[1] for f in candidate_facts)
    same_end = [f for f in candidate_facts if f[1] == max_end]
    max_duration = max(f[2] for f in same_end)
    latest_facts = [f for f in same_end if f[2] == max_duration]

    # FIXED 2026-09-02: was blindly summing every matching context per member (see
    # _dedupe_member_facts' docstring for the live TFC evidence) - dedupe the same
    # way _extract_segment_member_values below now does.
    nii_by_member = _sxs.XBRLSegmentParser._dedupe_member_facts(
        [(member, nii_value, is_boilerplate) for member, _end, _duration, nii_value, is_boilerplate in latest_facts],
        symbol,
        anchor_concept,
    )

    noninterest_by_member = _sxs.XBRLSegmentParser._extract_segment_member_values(
        root, context_segment, axis_to_use, (secondary_concept,), max_end, max_duration, symbol
    )

    combined = {member: nii_by_member[member] + noninterest_by_member.get(member, 0.0) for member in nii_by_member}

    # Reconciliation anchor: the filer's own plain (non-dimensioned) consolidated
    # facts for the same two concepts and period - built the same minimal way
    # _extract_single_segment_revenue does (has_dims/start/end per context id),
    # since context_segment only indexes segment-DIMENSIONED contexts.
    plain_contexts: dict[str, tuple[bool, str | None, str | None]] = {}
    for ctx in root.iter():
        if _local_name(ctx.tag) != "context":
            continue
        ctx_id = ctx.get("id")
        if not ctx_id:
            continue
        has_dims = False
        plain_start_str: str | None = None
        plain_end_str: str | None = None
        for child in ctx.iter():
            loc = _local_name(child.tag)
            if loc == "explicitMember":
                has_dims = True
            elif loc == "startDate":
                plain_start_str = (child.text or "").strip() or None
            elif loc in ("endDate", "instant"):
                plain_end_str = (child.text or "").strip() or None
        plain_contexts[ctx_id] = (has_dims, plain_start_str, plain_end_str)

    def _plain_value(concept: str) -> float | None:
        for elem in root.iter():
            if _local_name(elem.tag) != concept:
                continue
            info = plain_contexts.get(elem.get("contextRef", ""))
            if not info:
                continue
            has_dims, start_str, end_str = info
            if has_dims or end_str != max_end or elem.text is None:
                continue
            if start_str:
                try:
                    duration = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
                except ValueError:
                    continue
                if duration != max_duration:
                    continue
            try:
                return float(elem.text.strip())
            except ValueError:
                continue
        return None

    anchor_plain = _plain_value(anchor_concept)
    secondary_plain = _plain_value(secondary_concept)
    if anchor_plain is None or secondary_plain is None:
        logger.info(
            f"[{symbol}] Component-sum segment revenue found candidates but no plain "
            f"consolidated {anchor_concept}/{secondary_concept} to reconcile against - not trusting."
        )
        return None
    anchor = anchor_plain + secondary_plain
    if anchor == 0:
        return None

    total = sum(combined.values())
    error = abs(total - anchor) / abs(anchor)
    if error > _CROSS_TAB_RECONCILIATION_TOLERANCE:
        logger.info(
            f"[{symbol}] Component-sum segment revenue reconciliation failed: segment total "
            f"{total:,.0f} off by {error * 100:.1f}% vs consolidated {anchor:,.0f} - not trusting."
        )
        return None

    return combined, max_end, max_duration


def _extract_alt_asset_manager_segment_revenue(
    root: ET.Element,
    context_segment: dict[str, tuple[str, str, str, str | None, bool]],
    axis_to_use: str,
    symbol: str,
) -> tuple[dict[str, float], str, int] | None:
    """Fallback for alternative asset managers (confirmed live: Blackstone, CIK
    1393818) that tag segment revenue as multiple custom-namespace fee-line
    concepts instead of any us-gaap Revenues-family concept - see
    _ALT_ASSET_MANAGER_REVENUE_COMPONENT_CONCEPTS's module-level comment for the
    live evidence and exact-dollar reconciliation this fix was built from.

    Same discover-then-reconcile discipline as _extract_component_sum_segment_revenue,
    generalized to N components - a member missing one of the secondary concepts
    defaults to 0 for it (e.g. Blackstone's Multi-Asset Investing segment reports
    FeeRelatedPerformanceRevenues=0 every year, a real fact, not a gap), not
    excluded outright. Reconciles against the filer's OWN "Operating Segments"
    aggregate context (dimensioned only on ConsolidationItemsAxis=
    OperatingSegmentsMember, without the business-segment axis) rather than a
    truly plain/undimensioned fact, since no such plain fact exists for any of
    these concepts - _extract_component_sum_segment_revenue's `_plain_value`
    helper can't be reused here for that reason.

    Returns (member -> combined revenue, end_date, duration_days), or None if the
    anchor concept isn't tagged under axis_to_use at all, or the combined total
    doesn't reconcile against the Operating Segments aggregate.
    """
    anchor_concept, *secondary_concepts = _ALT_ASSET_MANAGER_REVENUE_COMPONENT_CONCEPTS

    candidate_facts: list[tuple[str, str, int, float, bool]] = []
    for elem in root.iter():
        if _local_name(elem.tag) != anchor_concept:
            continue
        info = context_segment.get(elem.get("contextRef", ""))
        if not info or info[0] != axis_to_use:
            continue
        _axis, member, end_str, start_str, is_boilerplate = info
        value = elem.text
        if value is None:
            continue
        try:
            revenue = float(value.strip())
        except ValueError:
            continue
        duration_days = 0
        if start_str and end_str:
            try:
                duration_days = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
            except ValueError:
                duration_days = 0
        candidate_facts.append((member, end_str, duration_days, revenue, is_boilerplate))

    if not candidate_facts:
        return None

    max_end = max(f[1] for f in candidate_facts)
    same_end = [f for f in candidate_facts if f[1] == max_end]
    max_duration = max(f[2] for f in same_end)
    latest_facts = [f for f in same_end if f[2] == max_duration]

    combined = dict(
        _sxs.XBRLSegmentParser._dedupe_member_facts(
            [(member, value, is_boilerplate) for member, _end, _duration, value, is_boilerplate in latest_facts],
            symbol,
            anchor_concept,
        )
    )

    for concept in secondary_concepts:
        by_member = _sxs.XBRLSegmentParser._extract_segment_member_values(
            root, context_segment, axis_to_use, (concept,), max_end, max_duration, symbol
        )
        for member in combined:
            combined[member] += by_member.get(member, 0.0)

    aggregate = _operating_segments_aggregate_value(
        root, _ALT_ASSET_MANAGER_REVENUE_COMPONENT_CONCEPTS, max_end, max_duration
    )
    if aggregate is None:
        logger.info(
            f"[{symbol}] Alt-asset-manager component-sum segment revenue found candidates "
            "but no Operating Segments aggregate to reconcile against - not trusting."
        )
        return None
    if aggregate == 0:
        return None

    total = sum(combined.values())
    error = abs(total - aggregate) / abs(aggregate)
    if error > _CROSS_TAB_RECONCILIATION_TOLERANCE:
        logger.info(
            f"[{symbol}] Alt-asset-manager component-sum segment revenue reconciliation "
            f"failed: segment total {total:,.0f} off by {error * 100:.1f}% vs Operating "
            f"Segments aggregate {aggregate:,.0f} - not trusting."
        )
        return None

    return combined, max_end, max_duration


def _operating_segments_aggregate_value(
    root: ET.Element, concepts: tuple[str, ...], target_end: str, match_duration_days: int
) -> float | None:
    """Sum `concepts` under the filer's own "Operating Segments" aggregate context -
    dimensioned ONLY on ConsolidationItemsAxis=OperatingSegmentsMember, without the
    business-segment axis - for the given period.

    Returns None if that context doesn't exist at all, or none of `concepts` has a
    fact under it - never 0.0 for "not found", so the caller's `aggregate == 0`
    no-op guard can't be fooled into treating "nothing to reconcile against" as a
    genuine zero-revenue result.
    """
    aggregate_context_ids: set[str] = set()
    for ctx in root.iter():
        if _local_name(ctx.tag) != "context":
            continue
        ctx_id = ctx.get("id")
        if not ctx_id:
            continue
        members: list[tuple[str, str]] = []
        start_str: str | None = None
        end_str: str | None = None
        for child in ctx.iter():
            loc = _local_name(child.tag)
            if loc == "explicitMember":
                members.append((_qname_local(child.get("dimension")), _qname_local(child.text)))
            elif loc == "startDate":
                start_str = (child.text or "").strip() or None
            elif loc in ("endDate", "instant"):
                end_str = (child.text or "").strip() or None
        if end_str != target_end or len(members) != 1:
            continue
        if members[0] != (_OPERATING_SEGMENTS_AGGREGATE_DIMENSION, _OPERATING_SEGMENTS_AGGREGATE_MEMBER):
            continue
        if start_str:
            try:
                duration = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
            except ValueError:
                continue
            if duration != match_duration_days:
                continue
        aggregate_context_ids.add(ctx_id)

    if not aggregate_context_ids:
        return None

    total = 0.0
    found_any = False
    for concept in concepts:
        for elem in root.iter():
            if _local_name(elem.tag) != concept or elem.get("contextRef") not in aggregate_context_ids:
                continue
            if elem.text is None:
                continue
            try:
                total += float(elem.text.strip())
            except ValueError:
                continue
            found_any = True
            break
    return total if found_any else None
