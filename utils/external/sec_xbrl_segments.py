#!/usr/bin/env python3
"""SEC XBRL Segment Disclosure Parser (ASC 280 - Business Segment Reporting).

Extracts business segment data from SEC 10-K filings in XBRL format.

Two data sources, in order of preference:

1. companyfacts API (fetch_incremental's first attempt) - fast, single request,
   but can ONLY ever answer "how many segments does this company report"
   (NumberOfReportableSegments and similar simple concepts). It can NEVER answer
   "what did each segment earn" - confirmed against SEC's own companyfacts
   response shape (each fact is {val, fy, fp, accn, form, filed, frame, ...},
   with no field identifying which XBRL dimension/segment-member it belongs to).
   SEC's companyfacts/companyconcept/frames APIs only surface facts tied to a
   non-dimensional ("default") context; segment-dimensioned facts are excluded
   from these endpoints entirely, by design of the API, not as a bug in this
   parser. So parse_companyfacts() never attempts per-segment revenue and always
   reports it unavailable, honestly, up front.

2. Raw XBRL instance XML (fetch_incremental's fallback via
   SecEdgarClient.get_filing_xml, which resolves the real standalone instance
   document rather than the inline-XBRL .htm) - the only place per-segment
   revenue actually lives. Segment identity is expressed as a dimensional
   context: <xbrli:context> elements carry an <xbrldi:explicitMember
   dimension="...StatementBusinessSegmentsAxis">...SegmentMember</xbrldi:explicitMember>,
   and a plain revenue concept (RevenueFromContractWithCustomerExcludingAssessedTax
   in modern (post-ASC 606) filings, occasionally the older Revenues/SalesRevenueNet
   concepts) is tagged with a contextRef pointing at that dimensional context -
   there is no distinct "SegmentRevenue"-named concept. Verified against a real
   filing (Microsoft's FY2025 10-K instance document): matches the company's
   actual reported segment revenue exactly ($120.81B/$106.27B/$54.65B for
   Productivity and Business Processes / Intelligent Cloud / More Personal
   Computing). Falls back to the geographic axis (StatementGeographicalAxis) for
   filers that report segments by geography rather than business line.

ASC 280 requires disclosure of:
- Operating segments (reportable if >10% of consolidated revenue)
- Segment revenue, operating income, assets
- Geographic segments (if material)
- Major customer concentrations (>10% revenue)
"""

import logging
import re
from datetime import date
from decimal import Decimal
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# Standard us-gaap axes used for ASC 280 segment reporting. Axis *names* are
# stable across taxonomy years (unlike concept namespaces, which are versioned
# per year) - business-line segments take priority; geographic is the fallback
# for filers whose only reportable segments are geographic.
_BUSINESS_SEGMENT_AXIS = "StatementBusinessSegmentsAxis"
_GEOGRAPHIC_SEGMENT_AXIS = "StatementGeographicalAxis"
_SEGMENT_AXIS_LOCAL_NAMES = (_BUSINESS_SEGMENT_AXIS, _GEOGRAPHIC_SEGMENT_AXIS)

# Standard (non-filer-specific) us-gaap companion axis some filers pair with a
# segment axis purely to mark "this is a real reportable-operating-segment
# figure" as opposed to the corporate/elimination reconciling line
# (ConsolidationItemsAxis=MaterialReconcilingItemsMember) - confirmed live
# against Coca-Cola's FY2025 10-K, where segment revenue is ONLY ever tagged as
# (ConsolidationItemsAxis=OperatingSegmentsMember, StatementBusinessSegmentsAxis=
# <segment>), never as a plain single-dimension segment context. This is not a
# further breakdown of the segment total (unlike a geography or product-line
# axis paired with the segment axis - see _index_segment_contexts), so a
# context carrying exactly this companion dimension alongside the segment axis
# still counts as "single dimension" for that purpose.
_CONSOLIDATION_ITEMS_AXIS = "ConsolidationItemsAxis"
_OPERATING_SEGMENTS_MEMBER = "OperatingSegmentsMember"

# Combined parent+subsidiary co-registrant filings (e.g. NextEra Energy/Florida
# Power & Light, both SEC registrants sharing one 10-K) tag facts belonging to
# the subsidiary registrant with dei:LegalEntityAxis, in addition to whatever
# segment axis identifies the same business line. Confirmed live against NEE's
# FY2025 10-K: FPL's segment-revenue context carries BOTH
# StatementBusinessSegmentsAxis=FloridaPowerLightCompanyMember AND
# LegalEntityAxis=FloridaPowerLightCompanyMember (identical member on both) -
# this is entity identity, not a further breakdown of the segment (unlike a
# geography or product-line axis paired with the segment axis), so it's
# stripped in _index_segment_contexts when its member matches the segment
# axis's own member in the same context.
_LEGAL_ENTITY_AXIS = "LegalEntityAxis"

# Standard us-gaap StatementBusinessSegmentsAxis member (part of the ASU 2023-07
# segment-reporting taxonomy) marking a SUBTOTAL of all reportable segments before
# adding "All Other" - not a real segment itself. Confirmed live against
# Caterpillar's FY2025 10-K: this member's tagged value ($73.955B) exactly equals
# the sum of CAT's 4 real reportable segments (Construction Industries $25.060B +
# Resource Industries $12.474B + Power Energy $32.201B + Financial Products
# $4.220B) - counting it as a peer "segment" alongside its own components would
# roughly double the true total and corrupt every HHI/concentration figure.
_NON_SEGMENT_SUBTOTAL_MEMBERS = ("ReportableSegmentAggregationBeforeOtherOperatingSegmentMember",)

# Revenue concepts to try, in preference order. Segment revenue is tagged using
# the SAME concept as consolidated revenue - just against a dimensioned context -
# so this list is really "which revenue concept does this filer use at all",
# checked most-specific (post-ASC-606 contract revenue) to least.
#
# RevenuesNetOfInterestExpense: banks/financial institutions (verified live
# against JPMorgan Chase's FY2025 10-K) don't tag plain Revenues at the
# per-segment level - they tag this concept instead (NoninterestIncome +
# InterestIncomeExpenseNet, the standard bank-holding-company income-statement
# framing). Confirmed the extracted per-segment values match JPM's real
# reported segment revenue: Consumer & Community Banking $76.0B, Commercial &
# Investment Bank $78.5B, Asset & Wealth Management $24.1B (FY2025). Tried
# last since it's specific to this one sector, not a general fallback.
_REVENUE_CONCEPT_LOCAL_NAMES = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",
    # RegulatedAndUnregulatedOperatingRevenue: regulated utilities (verified live
    # against NextEra Energy's FY2025 10-K) tag segment revenue under this
    # concept rather than Revenues - FPL (regulated) $18.262B, NEER (unregulated)
    # $8.760B, matching the real reported segment split.
    "RegulatedAndUnregulatedOperatingRevenue",
    # RevenuesNetOfInterestExpenseFullTaxEquivalentBasis: a company-specific
    # extension concept (bac: namespace, not us-gaap:) - Bank of America's own
    # FY2025 10-K tags segment revenue this way rather than the standard
    # RevenuesNetOfInterestExpense JPMorgan uses. Matching is by local name only
    # (see _local_name usage below), so a custom-namespace concept works the
    # same as a standard one. Verified: Consumer Banking $43.673B, GWIM
    # $24.883B, Global Banking $24.108B, Global Markets $24.096B, Corporate/
    # Eliminations -$3.054B (excluded by the existing negative-value filter)
    # sum to exactly BAC's real $113.706B consolidated revenue. Tried last -
    # a custom extension name is inherently filer-specific, not a candidate
    # any other filer would plausibly also use.
    "RevenuesNetOfInterestExpenseFullTaxEquivalentBasis",
    # PremiumsEarnedNet: insurers (verified live against AIG's FY2025 10-K) tag
    # segment-level revenue as net earned premiums, not Revenues - AIG's own
    # SupplementaryInsuranceInformationPremiumRevenue concept carries the
    # identical value at the same contexts, confirming this is the real
    # segment-level revenue figure, not a coincidence. North America $8.626B,
    # International $8.580B, Global Personal Travel Insurance $6.472B sum to
    # within 0.3% of AIG's real $23.751B consolidated revenue (a small
    # unallocated-corporate residual, same shape as NEE's). Tried last -
    # sector-specific, like the two revenue concepts above it.
    "PremiumsEarnedNet",
)

# Standard us-gaap ConsolidationItemsAxis members marking a reconciling/adjustment
# line rather than a real component of a segment's own reportable revenue - used by
# the cross-tab reconciliation fallback (see _extract_cross_tab_segment_revenue) to
# exclude these from the sum. Confirmed live against Exxon Mobil's FY2023-2025 10-Ks:
# "intersegment sales elimination" facts are tagged under
# ConsolidationItemsAxis=IntersegmentEliminationMember alongside the same geography
# axis used for real revenue breakdown facts - summing them in would silently corrupt
# the total.
_NON_ADDITIVE_CONSOLIDATION_MEMBERS = ("IntersegmentEliminationMember", "MaterialReconcilingItemsMember")

# Tolerance for validating a cross-tab reconciled segment-revenue candidate against
# the filer's own plain (non-dimensioned) consolidated revenue fact for the same
# period. 3% comfortably covers a small unallocated "Corporate/Financing" residual
# (confirmed live: Exxon's reconciliation lands within 0.3-0.5% every year) while
# still rejecting a wrong-axis-combo candidate, which is typically off by double
# digits or more (e.g. XOM's plain geography-only total, gross of intersegment
# sales, overstates the real total by ~36%).
_CROSS_TAB_RECONCILIATION_TOLERANCE = 0.03

# ASC 280 also requires segment operating income and assets "if regularly
# provided to the CODM" - unlike revenue, not every filer discloses these by
# segment (verified live: MSFT and AAPL tag OperatingIncomeLoss per segment but
# never Assets; AMZN tags both). OperatingIncomeLoss is a duration concept like
# revenue (matched on the same end date + duration); Assets is an instant
# (balance-sheet) concept, so it only has an end date, no duration.
_OPERATING_INCOME_CONCEPT_LOCAL_NAMES = ("OperatingIncomeLoss",)
_ASSETS_CONCEPT_LOCAL_NAMES = ("Assets",)


def _local_name(tag: str) -> str:
    """Strip the Clark-notation namespace from an ElementTree tag."""
    return tag.rsplit("}", 1)[-1]


def _qname_local(qname: str | None) -> str:
    """Strip the XML prefix from a QName-valued attribute/text (e.g. "us-gaap:FooAxis" -> "FooAxis").

    ElementTree only resolves namespaces for element/attribute *names*, not for
    QNames appearing as attribute values or text content - dimension/member
    references in XBRL contexts are exactly that case.
    """
    if not qname:
        return ""
    return qname.strip().rsplit(":", 1)[-1]


class XBRLSegmentParser:
    """Parse segment disclosure data from SEC XBRL filings (10-K).

    See module docstring for the companyfacts-vs-raw-XML split and why
    per-segment revenue can only ever come from the raw XML path.
    """

    @staticmethod
    def parse_companyfacts(facts: dict[str, Any], symbol: str) -> dict[str, Any]:
        """Parse segment COUNT (only) from SEC companyfacts JSON API response.

        Args:
            facts: JSON facts dict from SEC companyfacts API (us/CIK/CIK_0000123456.json)
                   Structure: {cik, entityName, facts: {us-gaap: {concept_name: [{...}]}}}
            symbol: Stock ticker symbol (for logging)

        Returns:
            Dict with segment_count if a company-level count concept is tagged,
            and data_available=False always (per-segment revenue is not
            recoverable from this endpoint - see module docstring).
        """
        try:
            if "facts" not in facts or "us-gaap" not in facts.get("facts", {}):
                return {
                    "segment_count": None,
                    "largest_segment_revenue_pct": None,
                    "revenue_concentration_hhi": None,
                    "segments": [],
                    "segment_type": None,
                    "data_available": False,
                    "reason": "no_us_gaap_facts",
                }

            us_gaap = facts["facts"]["us-gaap"]
            segment_count = XBRLSegmentParser._extract_segment_count(us_gaap, symbol)

            return {
                "segment_count": segment_count,
                "largest_segment_revenue_pct": None,
                "revenue_concentration_hhi": None,
                "segments": [],
                "segment_type": None,
                "data_available": False,
                "reason": (
                    "no_segment_count_facts_in_companyfacts"
                    if segment_count is None
                    else "companyfacts_api_never_exposes_per_segment_revenue"
                ),
            }

        except Exception as e:
            logger.warning(f"[{symbol}] XBRL segment parse failed: {type(e).__name__}: {str(e)[:200]}")
            return {
                "segment_count": None,
                "largest_segment_revenue_pct": None,
                "revenue_concentration_hhi": None,
                "segments": [],
                "segment_type": None,
                "data_available": False,
                "reason": f"parse_error: {type(e).__name__}",
            }

    @staticmethod
    def _extract_segment_count(us_gaap: dict, symbol: str) -> int | None:
        """Extract number of reportable segments from us-gaap facts.

        SEC XBRL uses several concepts for segment count. We check them in order
        of reliability, preferring explicit count fields over implicit counts.
        """
        candidates = [
            "SegmentNumber",
            "NumberOfReportableSegments",
            "OperatingSegmentNumber",
            "NumberOfSegments",
        ]

        for concept_name in candidates:
            if concept_name in us_gaap:
                concept_data = us_gaap[concept_name]
                if isinstance(concept_data, dict) and "units" in concept_data:
                    # companyfacts structure: units[unit_name][facts_list]
                    units = concept_data.get("units", {})
                    for _unit, facts_list in units.items():
                        if isinstance(facts_list, list):
                            best_fact = None
                            best_fy = -1
                            for fact in facts_list:
                                if isinstance(fact, dict):
                                    val = fact.get("val") or fact.get("value")
                                    if val is not None:
                                        try:
                                            count = int(val)
                                            if count > 0:
                                                fy = fact.get("fy", -1)
                                                # Prefer FY periods over quarterly
                                                fp = fact.get("fp", "")
                                                if fp == "FY" and fy > best_fy:
                                                    best_fy = fy
                                                    best_fact = count
                                                elif best_fact is None:
                                                    best_fact = count
                                        except (ValueError, TypeError):
                                            pass
                            if best_fact:
                                return best_fact

        return None

    @staticmethod
    def _compute_herfindahl_index(revenues: list[float | Decimal], total: float | Decimal) -> float:
        """Compute Herfindahl-Hirschman Index (HHI) of revenue concentration.

        HHI = sum of (revenue_share ^ 2) scaled to 0-10000
        - HHI < 1500: competitive
        - 1500-2500: moderate concentration
        - > 2500: highly concentrated
        - 10000: perfect monopoly (single segment)
        """
        if not revenues or total == 0:
            return 0.0

        total = float(total)
        hhi = 0.0
        for revenue in revenues:
            share = float(revenue) / total
            hhi += share * share

        # Scale to 0-10000
        return hhi * 10000

    @staticmethod
    def _prettify_segment_name(member_local_name: str) -> str:
        """"AmericasSegmentMember" / "IntelligentCloudMember" -> "Americas Segment" / "Intelligent Cloud"."""
        name = member_local_name
        if name.endswith("Member"):
            name = name[: -len("Member")]
        name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
        return name.strip() or member_local_name

    @staticmethod
    def _index_segment_contexts(root: ET.Element) -> dict[str, tuple[str, str, str, str | None]]:
        """Map context id -> (axis_local_name, segment_member, period_end, period_start).

        Only contexts representing the segment's own total are included - a
        recognized segment axis alone, or paired only with the standard
        ConsolidationItemsAxis=OperatingSegmentsMember marker (see
        _CONSOLIDATION_ITEMS_AXIS above). Non-segment-dimensioned contexts (the
        consolidated totals) and contexts dimensioned on any OTHER additional axis
        (product line, sub-segment, tax jurisdiction, equity component, etc. - a
        real 10-K instance has dozens) are excluded.

        Many filers cross-tab segment revenue against a further axis in the same
        instance document - e.g. business segment x geography, or business segment
        x product sub-line (confirmed live against JNJ's FY2025 10-K: Innovative
        Medicine revenue is tagged once for the segment total, then again broken
        out by US/Non-US, then again by therapeutic-area sub-segment, all sharing
        the same StatementBusinessSegmentsAxis=InnovativeMedicineMember dimension).
        A context dimensioned on one of those extra axes is one of those finer
        breakdowns, not the segment-level total - counting it under the same
        member key as the plain segment total silently multiplies revenue several
        times over. Restricting to single-dimension-or-OperatingSegmentsMember-
        paired contexts keeps only the true segment-level (or geography-level)
        totals.
        """
        context_segment: dict[str, tuple[str, str, str, str | None, bool]] = {}
        for ctx in root.iter():
            if _local_name(ctx.tag) != "context":
                continue
            ctx_id = ctx.get("id")
            if not ctx_id:
                continue

            explicit_members: list[tuple[str, str]] = []
            start_str = end_str = None
            for child in ctx.iter():
                loc = _local_name(child.tag)
                if loc == "explicitMember":
                    dim_local = _qname_local(child.get("dimension"))
                    explicit_members.append((dim_local, _qname_local(child.text)))
                elif loc == "startDate":
                    start_str = (child.text or "").strip() or None
                elif loc == "endDate":
                    end_str = (child.text or "").strip() or None
                elif loc == "instant":
                    end_str = (child.text or "").strip() or None

            # Drop the boilerplate "this is a real operating segment, not the
            # eliminations line" marker before judging dimension count - it
            # doesn't narrow the fact to a sub-breakdown of the segment.
            is_boilerplate_paired = any(
                m[0] == _CONSOLIDATION_ITEMS_AXIS and m[1] == _OPERATING_SEGMENTS_MEMBER for m in explicit_members
            )
            non_boilerplate = [
                m
                for m in explicit_members
                if not (m[0] == _CONSOLIDATION_ITEMS_AXIS and m[1] == _OPERATING_SEGMENTS_MEMBER)
            ]
            # Also drop a co-registrant LegalEntityAxis dimension whose member is
            # IDENTICAL to a segment-axis member already present in this same
            # context - that's the subsidiary's own registrant identity, not a
            # further breakdown (see _LEGAL_ENTITY_AXIS docstring). Only strips
            # when the member matches exactly, so it can't hide a real
            # further-breakdown-by-entity case.
            segment_members = {m[1] for m in non_boilerplate if m[0] in _SEGMENT_AXIS_LOCAL_NAMES}
            non_boilerplate = [
                m for m in non_boilerplate if not (m[0] == _LEGAL_ENTITY_AXIS and m[1] in segment_members)
            ]
            if len(non_boilerplate) != 1:
                continue
            axis, member = non_boilerplate[0]
            if axis not in _SEGMENT_AXIS_LOCAL_NAMES:
                continue
            if member in _NON_SEGMENT_SUBTOTAL_MEMBERS:
                continue

            if axis and member and end_str:
                context_segment[ctx_id] = (axis, member, end_str, start_str, is_boilerplate_paired)

        return context_segment

    @staticmethod
    def _extract_segment_member_values(
        root: ET.Element,
        context_segment: dict[str, tuple[str, str, str, str | None, bool]],
        axis_to_use: str,
        concept_local_names: tuple[str, ...],
        target_end: str,
        match_duration_days: int | None,
    ) -> dict[str, float]:
        """Extract member -> value for a concept, restricted to the same fiscal
        period already selected for segment revenue (target_end, and for
        duration concepts, match_duration_days).

        match_duration_days=None means an instant (balance-sheet) concept
        (e.g. Assets) - matched on end date alone, since instant contexts have
        no startDate. A duration concept (e.g. OperatingIncomeLoss) must also
        match the same period length as the revenue figure it's paired with, so
        a stray quarterly fact sharing the fiscal year-end date can't leak in
        next to an annual revenue total.

        Unlike revenue, values are NOT filtered by sign - a segment can have a
        real, legitimate operating loss (confirmed live: Amazon's International
        segment reported a -$2.66B OperatingIncomeLoss in FY2023).
        """
        values: dict[str, float] = {}
        for concept in concept_local_names:
            found = False
            for elem in root.iter():
                if _local_name(elem.tag) != concept:
                    continue
                info = context_segment.get(elem.get("contextRef", ""))
                if not info or info[0] != axis_to_use:
                    continue
                _axis, member, end_str, start_str, _is_boilerplate = info
                if end_str != target_end:
                    continue
                if match_duration_days is not None:
                    if not start_str:
                        continue
                    try:
                        duration = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
                    except ValueError:
                        continue
                    if duration != match_duration_days:
                        continue
                elif start_str:
                    # An instant concept (no startDate expected) matched a
                    # duration context - not the balance-sheet fact we want.
                    continue
                value = elem.text
                if value is None:
                    continue
                try:
                    values[member] = values.get(member, 0.0) + float(value.strip())
                except ValueError:
                    continue
                found = True
            if found:
                break
        return values

    @staticmethod
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
        for concept in _REVENUE_CONCEPT_LOCAL_NAMES:
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
                consol_member = other_dims.get(_CONSOLIDATION_ITEMS_AXIS)
                if consol_member == _OPERATING_SEGMENTS_MEMBER:
                    other_dims.pop(_CONSOLIDATION_ITEMS_AXIS)
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
        # consolidated revenue fact for the identical period.
        anchor: float | None = None
        for concept in _REVENUE_CONCEPT_LOCAL_NAMES:
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
            logger.info(f"[{symbol}] Cross-tab segment revenue found candidates but no consolidated anchor to reconcile against - not trusting any candidate.")
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

    @staticmethod
    def extract_segment_revenue_from_xbrl_xml(xml_content: str, symbol: str) -> dict[str, Any]:  # noqa: C901
        """Extract per-segment revenue from a raw XBRL instance document.

        Reads the actual XBRL dimensional model (context -> explicitMember ->
        segment axis/member) instead of guessing segment identity from
        contextRef naming conventions, which are filer/tool-specific and not
        governed by any SEC-wide convention.

        Returns:
            Same structure as parse_companyfacts(), with real segment-level
            revenue when the filing tags any recognized segment axis.
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.warning(f"[{symbol}] Failed to parse XBRL XML: {e}")
            return {
                "segment_count": None,
                "largest_segment_revenue_pct": None,
                "revenue_concentration_hhi": None,
                "segments": [],
                "segment_type": None,
                "data_available": False,
                "reason": f"xml_parse_error: {str(e)[:100]}",
            }

        context_segment = XBRLSegmentParser._index_segment_contexts(root)
        if not context_segment:
            return {
                "segment_count": None,
                "largest_segment_revenue_pct": None,
                "revenue_concentration_hhi": None,
                "segments": [],
                "segment_type": None,
                "data_available": False,
                "reason": "no_segment_dimension_contexts_in_xbrl_xml",
            }

        # Prefer business-line segments (ASC 280's primary "operating segments");
        # fall back to geographic only when the filer doesn't tag business segments.
        available_axes = {info[0] for info in context_segment.values()}
        axis_to_use = _BUSINESS_SEGMENT_AXIS if _BUSINESS_SEGMENT_AXIS in available_axes else _GEOGRAPHIC_SEGMENT_AXIS

        candidate_facts: list[tuple[str, str, int, float, bool]] = []
        # (member, end_date, duration_days, revenue, is_boilerplate_paired)
        matched_concept = None
        for concept in _REVENUE_CONCEPT_LOCAL_NAMES:
            candidate_facts = []
            for elem in root.iter():
                if _local_name(elem.tag) != concept:
                    continue
                info = context_segment.get(elem.get("contextRef", ""))
                if not info or info[0] != axis_to_use:
                    continue
                _axis, member, end_str, start_str, is_boilerplate_paired = info
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
                candidate_facts.append((member, end_str, duration_days, revenue, is_boilerplate_paired))
            if candidate_facts:
                matched_concept = concept
                break

        if not candidate_facts:
            cross_tab = XBRLSegmentParser._extract_cross_tab_segment_revenue(root, symbol, axis_to_use)
            if cross_tab is None:
                return {
                    "segment_count": None,
                    "largest_segment_revenue_pct": None,
                    "revenue_concentration_hhi": None,
                    "segments": [],
                    "segment_type": None,
                    "data_available": False,
                    "reason": "no_segment_revenue_in_xbrl_xml",
                }
            segments, max_end, max_duration = cross_tab
            logger.debug(f"[{symbol}] Segment revenue matched via cross-tab reconciliation on {axis_to_use}")
        else:
            logger.debug(f"[{symbol}] Segment revenue matched via {matched_concept} on {axis_to_use}")

            # A 10-K instance carries multiple fiscal years side by side for
            # comparison tables - keep only the most recent period (max end date;
            # among ties, the longest duration, to prefer an annual figure over a
            # stray quarterly context sharing the fiscal year-end date).
            max_end = max(f[1] for f in candidate_facts)
            same_end = [f for f in candidate_facts if f[1] == max_end]
            max_duration = max(f[2] for f in same_end)
            latest_facts = [f for f in same_end if f[2] == max_duration]

            # A filer can tag the same segment's revenue via more than one qualifying
            # context for the same period - e.g. a plain single-axis context AND a
            # ConsolidationItemsAxis=OperatingSegmentsMember-paired one (confirmed
            # live: JNJ's FY2025 10-K tags Innovative Medicine revenue both ways,
            # both contexts carrying the identical value). These are usually
            # redundant taggings of ONE real fact, not two additive ones - summing
            # them would silently double the segment's revenue. Keep one value per
            # member.
            #
            # They can also genuinely disagree: confirmed live against Caterpillar's
            # FY2025 10-K, Power & Energy's OperatingSegmentsMember-paired context
            # tags $32.201B (gross, including intersegment sales) while its plain
            # context tags $27.143B (net, externally reported) - the two reconcile
            # exactly against CAT's own tagged IntersegmentEliminationMember fact
            # (-$5.058B). The plain, non-boilerplate-paired context is the filer's
            # actual externally-reported segment revenue; prefer it on disagreement
            # rather than picking whichever happened to be tagged first in document
            # order.
            segments: dict[str, float] = {}
            segment_is_boilerplate: dict[str, bool] = {}
            for member, _end, _duration, revenue, is_boilerplate_paired in latest_facts:
                if member not in segments:
                    segments[member] = revenue
                    segment_is_boilerplate[member] = is_boilerplate_paired
                    continue
                if abs(segments[member] - revenue) <= max(1.0, abs(segments[member]) * 0.001):
                    continue  # same fact tagged twice, nothing to reconcile
                if segment_is_boilerplate[member] and not is_boilerplate_paired:
                    logger.warning(
                        f"[{symbol}] Segment '{member}' tagged with disagreeing revenue values "
                        f"across contexts ({segments[member]} vs {revenue}) for the same period - "
                        "preferring the plain (non-OperatingSegmentsMember-paired) value."
                    )
                    segments[member] = revenue
                    segment_is_boilerplate[member] = is_boilerplate_paired
                else:
                    logger.warning(
                        f"[{symbol}] Segment '{member}' tagged with disagreeing revenue values "
                        f"across contexts ({segments[member]} vs {revenue}) for the same period - "
                        "keeping the first value seen."
                    )

        # Many filers tag a non-operating "Corporate and Eliminations" (or similarly
        # named) reconciling line under the same segment axis so segment totals foot
        # to the consolidated total - by ASC 280 convention that's an intercompany
        # elimination/unallocated-corporate line, not a real reportable operating
        # segment, and it's the only case revenue under this axis is ever negative.
        # Excluding negative entries (rather than matching on member name, which SEC
        # does not standardize) keeps HHI/largest_segment_revenue_pct meaningful -
        # without this, an elimination line can push total_revenue below any single
        # real segment's revenue, producing an impossible >100% largest_pct.
        reportable_segments = {member: revenue for member, revenue in segments.items() if revenue >= 0}

        total_revenue = sum(reportable_segments.values())
        if not reportable_segments or total_revenue == 0:
            return {
                "segment_count": len(reportable_segments) or None,
                "largest_segment_revenue_pct": None,
                "revenue_concentration_hhi": None,
                "segments": [],
                "segment_type": None,
                "data_available": False,
                "reason": "zero_total_segment_revenue",
            }

        operating_income_by_member = XBRLSegmentParser._extract_segment_member_values(
            root, context_segment, axis_to_use, _OPERATING_INCOME_CONCEPT_LOCAL_NAMES, max_end, max_duration
        )
        assets_by_member = XBRLSegmentParser._extract_segment_member_values(
            root, context_segment, axis_to_use, _ASSETS_CONCEPT_LOCAL_NAMES, max_end, None
        )

        segment_list = sorted(
            (
                {
                    "segment_id": member,
                    "name": XBRLSegmentParser._prettify_segment_name(member),
                    "revenue": revenue,
                    "operating_income": operating_income_by_member.get(member),
                    "assets": assets_by_member.get(member),
                }
                for member, revenue in reportable_segments.items()
            ),
            key=lambda s: s["revenue"],
            reverse=True,
        )
        revenues = [s["revenue"] for s in segment_list]
        hhi = XBRLSegmentParser._compute_herfindahl_index(revenues, total_revenue)
        largest_pct = revenues[0] / total_revenue * 100

        return {
            "segment_count": len(segment_list),
            "largest_segment_revenue_pct": round(largest_pct, 2),
            "revenue_concentration_hhi": round(hhi, 3),
            "segments": segment_list,
            "segment_type": "operating" if axis_to_use == _BUSINESS_SEGMENT_AXIS else "geographic",
            "data_available": True,
            "reason": None,
        }
