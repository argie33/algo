"""Remaining segment-revenue extraction fallbacks (Ares-style, single-segment) for
XBRLSegmentParser, extracted from utils/external/sec_xbrl_segments.py (2026-09-05, file-size
ratchet: it's a Tier-2 bloater flagged for decomposition; split from
sec_xbrl_segment_revenue.py to stay under the 800-line new-file cap). Bodies are verbatim, no
logic changed - only converted from staticmethods to plain module functions and moved file.
Called by XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml, which stays in the main
file and tries each of these in sequence.

`XBRLSegmentParser._dedupe_member_facts`/`._extract_segment_member_values` are accessed via
the sec_xbrl_segments module object at call time - see sec_xbrl_segment_revenue.py's module
docstring for the full circular-import rationale, identical here.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

from utils.external.sec_xbrl_segments import (
    _ARES_STYLE_ADDITIVE_CONCEPT,
    _ARES_STYLE_ENTITIES_DIMENSION,
    _ARES_STYLE_ENTITIES_MEMBER,
    _ARES_STYLE_REVENUE_CONCEPT,
    _CROSS_TAB_RECONCILIATION_TOLERANCE,
    _OPERATING_SEGMENTS_AGGREGATE_DIMENSION,
    _OPERATING_SEGMENTS_AGGREGATE_MEMBER,
    _REVENUE_CONCEPT_LOCAL_NAMES,
    _SEGMENT_AXIS_LOCAL_NAMES,
    _SEGMENT_COUNT_CONCEPT_LOCAL_NAMES,
    _local_name,
    _qname_local,
)

logger = logging.getLogger(__name__)


def _extract_ares_style_segment_revenue(  # noqa: C901 -- same discover-then-reconcile shape as the sibling fallbacks above, deliberately narrow rather than deeply nested
    root: ET.Element, symbol: str
) -> tuple[dict[str, float], str, int] | None:
    """Fallback for Ares Management's specific segment-revenue shape - see
    _ARES_STYLE_ENTITIES_DIMENSION's module-level comment for the live evidence and
    exact-dollar verification, and why this is a narrow, filer-specific extractor
    rather than a shared boilerplate-list change.

    Sums the standard RevenueFromContractWithCustomerExcludingAssessedTax concept
    across ProductOrServiceAxis members for each business-segment member (Ares's 3
    fee types), plus the separately-tagged PerformanceFeesRealizedRevenue additive
    component, reconciling the per-segment sum against the SAME two concepts summed
    at the coarser Operating-Segments-aggregate level (no business-segment axis) -
    no plain/undimensioned fact exists for either concept, same reconciliation
    shape as _extract_alt_asset_manager_segment_revenue's Blackstone case.

    Every match requires ConsolidatedEntitiesAxis=ParentCompanyMember AND
    ConsolidationItemsAxis=OperatingSegmentsMember AND an exact dimension-set match
    (no unrecognized extra axis) - this cannot misfire for a filer that merely
    shares one of these dimensions for an unrelated reason.

    Returns (member -> combined revenue, end_date, duration_days), or None if no
    candidate is found or the reconciliation fails.
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
            elif loc in ("endDate", "instant"):
                end_str = (child.text or "").strip() or None
        all_contexts[ctx_id] = (dims, start_str, end_str)

    def _matched_segment_member(dims: dict[str, str], extra_axes: set[str]) -> str | None:
        if dims.get(_ARES_STYLE_ENTITIES_DIMENSION) != _ARES_STYLE_ENTITIES_MEMBER:
            return None
        if dims.get(_OPERATING_SEGMENTS_AGGREGATE_DIMENSION) != _OPERATING_SEGMENTS_AGGREGATE_MEMBER:
            return None
        segment_axis = next((a for a in _SEGMENT_AXIS_LOCAL_NAMES if a in dims), None)
        if segment_axis is None:
            return None
        expected = extra_axes | {
            _ARES_STYLE_ENTITIES_DIMENSION,
            _OPERATING_SEGMENTS_AGGREGATE_DIMENSION,
            segment_axis,
        }
        if set(dims.keys()) != expected:
            return None
        return dims[segment_axis]

    revenue_candidates: list[tuple[str, str, int, float]] = []
    for elem in root.iter():
        if _local_name(elem.tag) != _ARES_STYLE_REVENUE_CONCEPT:
            continue
        info = all_contexts.get(elem.get("contextRef", ""))
        if not info:
            continue
        dims, start_str, end_str = info
        if not end_str:
            continue
        member = _matched_segment_member(dims, {"ProductOrServiceAxis"})
        if member is None:
            continue
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
        revenue_candidates.append((member, end_str, duration_days, revenue))

    if not revenue_candidates:
        return None

    max_end = max(c[1] for c in revenue_candidates)
    same_end = [c for c in revenue_candidates if c[1] == max_end]
    max_duration = max(c[2] for c in same_end)
    period_candidates = [c for c in same_end if c[2] == max_duration]

    per_segment: dict[str, float] = {}
    for member, _end, _duration, revenue in period_candidates:
        per_segment[member] = per_segment.get(member, 0.0) + revenue

    # Additive component - a member missing it defaults to 0 (a real segment can
    # legitimately have no realized performance income that period).
    for elem in root.iter():
        if _local_name(elem.tag) != _ARES_STYLE_ADDITIVE_CONCEPT:
            continue
        info = all_contexts.get(elem.get("contextRef", ""))
        if not info:
            continue
        dims, start_str, end_str = info
        if end_str != max_end:
            continue
        member = _matched_segment_member(dims, set())
        if member is None or member not in per_segment:
            continue
        if start_str:
            try:
                duration = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
            except ValueError:
                continue
            if duration != max_duration:
                continue
        value = elem.text
        if value is None:
            continue
        try:
            per_segment[member] += float(value.strip())
        except ValueError:
            continue

    # FIXED before shipping (live-caught against Ares's real filing): checking only
    # the axis NAME set (not the actual member values) let this wrongly match
    # Ares's own "ReportableLegalEntitiesMember"-consolidated facts too - a
    # DIFFERENT reporting basis under the same ConsolidationItemsAxis name (Ares
    # discloses the same fee lines both at the "Ares Management L.P." consolidated-
    # entity level and at the Operating-Segments level; only the latter is the
    # right reconciliation anchor). Also live-caught the filing tagging the exact
    # same (concept, contextRef) fact twice (a real, common inline-XBRL rendering
    # duplicate) - deduping by contextRef here (last value wins, same as every
    # other dedupe in this file) instead of blindly `+=`-accumulating avoids
    # silently doubling the aggregate.
    aggregate = 0.0
    found_any = False
    for concept, needs_product_axis in (
        (_ARES_STYLE_REVENUE_CONCEPT, True),
        (_ARES_STYLE_ADDITIVE_CONCEPT, False),
    ):
        expected_dims = {_ARES_STYLE_ENTITIES_DIMENSION, _OPERATING_SEGMENTS_AGGREGATE_DIMENSION}
        if needs_product_axis:
            expected_dims = expected_dims | {"ProductOrServiceAxis"}
        by_context: dict[str, float] = {}
        for elem in root.iter():
            if _local_name(elem.tag) != concept:
                continue
            ctx_ref = elem.get("contextRef", "")
            info = all_contexts.get(ctx_ref)
            if not info:
                continue
            dims, start_str, end_str = info
            if end_str != max_end or set(dims.keys()) != expected_dims:
                continue
            if dims.get(_ARES_STYLE_ENTITIES_DIMENSION) != _ARES_STYLE_ENTITIES_MEMBER:
                continue
            if dims.get(_OPERATING_SEGMENTS_AGGREGATE_DIMENSION) != _OPERATING_SEGMENTS_AGGREGATE_MEMBER:
                continue
            if start_str:
                try:
                    duration = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
                except ValueError:
                    continue
                if duration != max_duration:
                    continue
            value = elem.text
            if value is None:
                continue
            try:
                by_context[ctx_ref] = float(value.strip())
            except ValueError:
                continue
        aggregate += sum(by_context.values())
        found_any = found_any or bool(by_context)

    if not found_any or aggregate == 0:
        logger.info(
            f"[{symbol}] Ares-style segment revenue found candidates but no Operating "
            "Segments aggregate to reconcile against - not trusting."
        )
        return None

    total = sum(per_segment.values())
    error = abs(total - aggregate) / abs(aggregate)
    if error > _CROSS_TAB_RECONCILIATION_TOLERANCE:
        logger.info(
            f"[{symbol}] Ares-style segment revenue reconciliation failed: segment total "
            f"{total:,.0f} off by {error * 100:.1f}% vs Operating Segments aggregate "
            f"{aggregate:,.0f} - not trusting."
        )
        return None

    return per_segment, max_end, max_duration


def _extract_single_segment_revenue(root: ET.Element, symbol: str) -> tuple[str, float, str, int] | None:  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
    """Fallback for filers that disclose exactly one reportable segment.

    A single-segment filer's segment revenue is trivially its consolidated
    total - ASU 2023-07 still requires tagging NumberOfReportableSegments/
    NumberOfOperatingSegments even then, but filers routinely skip
    re-tagging revenue under the segment axis at all (or, per Realty
    Income's FY2025 10-K, tag only per-segment EXPENSE items like
    DirectCostsOfLeasedAndRentedPropertyOrEquipment under
    StatementBusinessSegmentsAxis=ReportableSegmentMember, never revenue) -
    the primary and cross-tab paths both correctly find nothing to extract.
    Confirmed live this is a real, common pattern, not an edge case: Gilead
    Sciences, Regeneron, United Airlines Holdings, and Realty Income all
    tag their segment count as exactly 1 with zero/incomplete
    segment-dimensioned revenue anywhere in the filing.

    Only returns a value when the count concept says exactly 1 for the
    latest fiscal year - if a filer reports >1 segments through this
    concept but this parser still couldn't extract per-segment revenue
    (a real multi-segment gap), this correctly returns None so the caller
    stays honest with data_unavailable rather than fabricating a
    single-segment result for a company that isn't one.

    Returns (concept_name, revenue, end_date, duration_days) for the
    matched consolidated revenue fact, or None if no plain segment-count
    fact says exactly 1, or no plain consolidated revenue fact exists for
    that same period.
    """
    contexts: dict[str, tuple[bool, str | None, str | None]] = {}
    for ctx in root.iter():
        if _local_name(ctx.tag) != "context":
            continue
        ctx_id = ctx.get("id")
        if not ctx_id:
            continue
        has_dims = False
        start_str = end_str = None
        for child in ctx.iter():
            loc = _local_name(child.tag)
            if loc == "explicitMember":
                has_dims = True
            elif loc == "startDate":
                start_str = (child.text or "").strip() or None
            elif loc == "endDate":
                end_str = (child.text or "").strip() or None
            elif loc == "instant":
                end_str = (child.text or "").strip() or None
        contexts[ctx_id] = (has_dims, start_str, end_str)

    count_by_end: dict[str, int] = {}
    for concept in _SEGMENT_COUNT_CONCEPT_LOCAL_NAMES:
        for elem in root.iter():
            if _local_name(elem.tag) != concept:
                continue
            info = contexts.get(elem.get("contextRef", ""))
            if not info:
                continue
            has_dims, _start, end_str = info
            if has_dims or not end_str or elem.text is None:
                continue
            try:
                count_by_end[end_str] = int(elem.text.strip())
            except ValueError:
                continue
        if count_by_end:
            break

    if not count_by_end:
        return None
    max_end = max(count_by_end)
    if count_by_end[max_end] != 1:
        return None

    for concept in _REVENUE_CONCEPT_LOCAL_NAMES:
        for elem in root.iter():
            if _local_name(elem.tag) != concept:
                continue
            info = contexts.get(elem.get("contextRef", ""))
            if not info:
                continue
            has_dims, start_str, end_str = info
            if has_dims or end_str != max_end or elem.text is None:
                continue
            try:
                revenue = float(elem.text.strip())
            except ValueError:
                continue
            duration_days = 0
            if start_str:
                try:
                    duration_days = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
                except ValueError:
                    duration_days = 0
            logger.info(
                f"[{symbol}] Single reportable segment (count=1) - using consolidated "
                f"{concept} as the sole segment's revenue."
            )
            return concept, revenue, end_str, duration_days
    return None


def _single_segment_result(
    name: str,
    segment_id: str,
    segment_type: str,
    revenue: float,
    operating_income: float | None,
    assets: float | None,
) -> dict[str, Any]:
    """Build the standard success-shaped dict for the single-reportable-segment fallback."""
    return {
        "segment_count": 1,
        "largest_segment_revenue_pct": 100.0,
        "revenue_concentration_hhi": 10000.0,
        "segments": [
            {
                "segment_id": segment_id,
                "name": name,
                "revenue": revenue,
                "operating_income": operating_income,
                "assets": assets,
            }
        ],
        "segment_type": segment_type,
        "data_available": True,
        "reason": None,
    }
