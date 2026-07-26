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

# Revenue concepts to try, in preference order. Segment revenue is tagged using
# the SAME concept as consolidated revenue - just against a dimensioned context -
# so this list is really "which revenue concept does this filer use at all",
# checked most-specific (post-ASC-606 contract revenue) to least.
_REVENUE_CONCEPT_LOCAL_NAMES = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)


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

        Only contexts carrying an explicitMember on a recognized segment axis are
        included; non-segment-dimensioned contexts (the consolidated totals) and
        contexts dimensioned on unrelated axes (product line, tax jurisdiction,
        equity component, etc. - a real 10-K instance has dozens) are excluded.
        """
        context_segment: dict[str, tuple[str, str, str, str | None]] = {}
        for ctx in root.iter():
            if _local_name(ctx.tag) != "context":
                continue
            ctx_id = ctx.get("id")
            if not ctx_id:
                continue

            axis = member = None
            start_str = end_str = None
            for child in ctx.iter():
                loc = _local_name(child.tag)
                if loc == "explicitMember":
                    dim_local = _qname_local(child.get("dimension"))
                    if dim_local in _SEGMENT_AXIS_LOCAL_NAMES:
                        axis = dim_local
                        member = _qname_local(child.text)
                elif loc == "startDate":
                    start_str = (child.text or "").strip() or None
                elif loc == "endDate":
                    end_str = (child.text or "").strip() or None
                elif loc == "instant":
                    end_str = (child.text or "").strip() or None

            if axis and member and end_str:
                context_segment[ctx_id] = (axis, member, end_str, start_str)

        return context_segment

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

        candidate_facts: list[tuple[str, str, int, float]] = []  # (member, end_date, duration_days, revenue)
        matched_concept = None
        for concept in _REVENUE_CONCEPT_LOCAL_NAMES:
            candidate_facts = []
            for elem in root.iter():
                if _local_name(elem.tag) != concept:
                    continue
                info = context_segment.get(elem.get("contextRef", ""))
                if not info or info[0] != axis_to_use:
                    continue
                _axis, member, end_str, start_str = info
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
                candidate_facts.append((member, end_str, duration_days, revenue))
            if candidate_facts:
                matched_concept = concept
                break

        if not candidate_facts:
            return {
                "segment_count": None,
                "largest_segment_revenue_pct": None,
                "revenue_concentration_hhi": None,
                "segments": [],
                "segment_type": None,
                "data_available": False,
                "reason": "no_segment_revenue_in_xbrl_xml",
            }
        logger.debug(f"[{symbol}] Segment revenue matched via {matched_concept} on {axis_to_use}")

        # A 10-K instance carries multiple fiscal years side by side for
        # comparison tables - keep only the most recent period (max end date;
        # among ties, the longest duration, to prefer an annual figure over a
        # stray quarterly context sharing the fiscal year-end date).
        max_end = max(f[1] for f in candidate_facts)
        same_end = [f for f in candidate_facts if f[1] == max_end]
        max_duration = max(f[2] for f in same_end)
        latest_facts = [f for f in same_end if f[2] == max_duration]

        segments: dict[str, float] = {}
        for member, _end, _duration, revenue in latest_facts:
            segments[member] = segments.get(member, 0.0) + revenue

        total_revenue = sum(segments.values())
        if not segments or total_revenue == 0:
            return {
                "segment_count": len(segments) or None,
                "largest_segment_revenue_pct": None,
                "revenue_concentration_hhi": None,
                "segments": [],
                "segment_type": None,
                "data_available": False,
                "reason": "zero_total_segment_revenue",
            }

        segment_list = sorted(
            (
                {
                    "segment_id": member,
                    "name": XBRLSegmentParser._prettify_segment_name(member),
                    "revenue": revenue,
                    "operating_income": None,
                    "assets": None,
                }
                for member, revenue in segments.items()
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
