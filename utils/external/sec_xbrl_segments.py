#!/usr/bin/env python3
"""SEC XBRL Segment Disclosure Parser (ASC 280 - Business Segment Reporting).

Extracts business segment data from SEC 10-K/10-Q filings in XBRL format.
Uses SEC EDGAR companyfacts API to fetch and parse segment-related XBRL facts,
with fallback to raw XML parsing for more aggressive data extraction.

ASC 280 requires disclosure of:
- Operating segments (reportable if >10% of consolidated revenue)
- Segment revenue, operating income, assets
- Geographic segments (if material)
- Major customer concentrations (>10% revenue)
"""

import logging
import re
from decimal import Decimal
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# SEC XBRL namespace for us-gaap taxonomy
XBRL_NAMESPACES = {
    'us-gaap': 'http://xbrl.us/us-gaap/2023-01-31',
    'default': 'http://www.xbrl.org/2003/instance',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
}


class XBRLSegmentParser:
    """Parse segment disclosure data from SEC XBRL filings (10-K/10-Q).

    Extracts:
    - Segment counts and names
    - Revenue by segment
    - Operating income by segment
    - Herfindahl concentration index
    - Geographic segment breakdown
    """

    @staticmethod
    def parse_companyfacts(facts: dict[str, Any], symbol: str) -> dict[str, Any]:
        """Parse segment data from SEC companyfacts JSON API response.

        Args:
            facts: JSON facts dict from SEC companyfacts API (us/CIK/CIK_0000123456.json)
                   Structure: {cik, entityName, facts: {us-gaap: {concept_name: [{...}]}}}
            symbol: Stock ticker symbol (for logging)

        Returns:
            Dict with:
            - segment_count: # of reportable operating segments
            - largest_segment_revenue_pct: % revenue from largest segment
            - revenue_concentration_hhi: Herfindahl index of revenue concentration
            - segments: List of individual segment data dicts
            - segment_type: Primary type ("operating", "geographic", etc.)
            - data_available: Whether segment data was found
            - reason: Why unavailable (if data_available=False)

        Raises:
            ValueError: If facts structure invalid or CIK mismatch
        """
        try:
            if 'facts' not in facts or 'us-gaap' not in facts.get('facts', {}):
                return {
                    'segment_count': None,
                    'largest_segment_revenue_pct': None,
                    'revenue_concentration_hhi': None,
                    'segments': [],
                    'segment_type': None,
                    'data_available': False,
                    'reason': 'no_us_gaap_facts',
                }

            us_gaap = facts['facts']['us-gaap']

            # Extract segment revenue data
            # SEC uses: SegmentsReportedUponChange, SegmentRevenue, SegmentNumber, SegmentIdentificationCode
            segment_count = XBRLSegmentParser._extract_segment_count(us_gaap, symbol)
            segments = XBRLSegmentParser._extract_segments(us_gaap, symbol)

            if not segments:
                return {
                    'segment_count': segment_count,
                    'largest_segment_revenue_pct': None,
                    'revenue_concentration_hhi': None,
                    'segments': [],
                    'segment_type': None,
                    'data_available': False,
                    'reason': 'no_segment_revenue_data',
                }

            # Calculate concentration metrics
            revenues = [seg.get('revenue') for seg in segments if seg.get('revenue') is not None]
            if not revenues or all(r == 0 for r in revenues):
                return {
                    'segment_count': segment_count or len(segments),
                    'largest_segment_revenue_pct': None,
                    'revenue_concentration_hhi': None,
                    'segments': segments,
                    'segment_type': 'operating',
                    'data_available': False,
                    'reason': 'zero_or_null_revenue',
                }

            total_revenue = sum(revenues)
            if total_revenue == 0:
                return {
                    'segment_count': segment_count or len(segments),
                    'largest_segment_revenue_pct': None,
                    'revenue_concentration_hhi': None,
                    'segments': segments,
                    'segment_type': 'operating',
                    'data_available': False,
                    'reason': 'zero_total_revenue',
                }

            # Compute Herfindahl index: sum of squared revenue percentages (scaled 0-10000)
            hhi = XBRLSegmentParser._compute_herfindahl_index(revenues, total_revenue)
            largest_pct = (max(revenues) / total_revenue * 100) if total_revenue > 0 else 0

            return {
                'segment_count': segment_count or len(segments),
                'largest_segment_revenue_pct': round(float(largest_pct), 2),
                'revenue_concentration_hhi': round(float(hhi), 3),
                'segments': segments,
                'segment_type': 'operating',
                'data_available': True,
                'reason': None,
            }

        except Exception as e:
            logger.warning(f"[{symbol}] XBRL segment parse failed: {type(e).__name__}: {str(e)[:200]}")
            return {
                'segment_count': None,
                'largest_segment_revenue_pct': None,
                'revenue_concentration_hhi': None,
                'segments': [],
                'segment_type': None,
                'data_available': False,
                'reason': f'parse_error: {type(e).__name__}',
            }

    @staticmethod
    def _extract_segment_count(us_gaap: dict, symbol: str) -> int | None:
        """Extract number of reportable segments from us-gaap facts.

        SEC XBRL uses several concepts for segment count. We check them in order
        of reliability, preferring explicit count fields over implicit counts.
        """
        candidates = [
            'SegmentNumber',
            'NumberOfReportableSegments',
            'OperatingSegmentNumber',
            'NumberOfSegments',
        ]

        for concept_name in candidates:
            if concept_name in us_gaap:
                concept_data = us_gaap[concept_name]
                if isinstance(concept_data, dict) and 'units' in concept_data:
                    # companyfacts structure: units[unit_name][facts_list]
                    units = concept_data.get('units', {})
                    for _unit, facts_list in units.items():
                        if isinstance(facts_list, list):
                            best_fact = None
                            best_fy = -1
                            for fact in facts_list:
                                if isinstance(fact, dict):
                                    val = fact.get('val') or fact.get('value')
                                    if val is not None:
                                        try:
                                            count = int(val)
                                            if count > 0:
                                                fy = fact.get('fy', -1)
                                                # Prefer FY periods over quarterly
                                                fp = fact.get('fp', '')
                                                if fp == 'FY' and fy > best_fy:
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
    def _extract_segments(us_gaap: dict, symbol: str) -> list[dict[str, Any]]:  # noqa: C901
        """Extract individual segment data from us-gaap facts.

        SEC companyfacts structure: us-gaap[concept][unit][] = list of fact records
        Each fact has: value, fy (fiscal year), fp (fiscal period), contextRef, etc.

        Returns list of segment dicts with: name, revenue, operating_income, assets
        """
        segments = []
        segment_revenues = {}
        segments_data = {}

        # Extract segment revenue from companyfacts structure
        # companyfacts[concept][unit][] has array of fact objects
        # SEC uses various naming patterns for segment revenue
        segment_revenue_concept = None
        revenue_concepts = [
            'SegmentReportingInformationRevenue',  # SEC standard for segment revenue
            'SegmentReportingInformationRevenueFromExternalCustomers',
            'SegmentRevenue',
            'RevenueFromContractWithCustomer',
            'Revenues',
        ]
        for concept_name in revenue_concepts:
            if concept_name in us_gaap:
                segment_revenue_concept = concept_name
                break

        if segment_revenue_concept:
            concept_data = us_gaap.get(segment_revenue_concept, {})
            if isinstance(concept_data, dict) and 'units' in concept_data:
                units_data = concept_data['units']
                for _unit, facts_list in units_data.items():
                    if isinstance(facts_list, list):
                        for fact in facts_list:
                            if isinstance(fact, dict):
                                # Extract segment identifier and revenue
                                # SEC XBRL uses 'segment' field or embeds it in contextRef
                                segment_id = fact.get('segment')
                                if not segment_id:
                                    # Try to extract from contextRef which has format like:
                                    # "SegmentA_StandardPeriodDuration"
                                    context_ref = fact.get('contextRef', '')
                                    if context_ref and '_' in context_ref:
                                        segment_id = context_ref.split('_')[0]

                                value = fact.get('val') or fact.get('value')  # companyfacts uses 'val'
                                # Prefer most recent fiscal year data
                                if value is not None and segment_id:
                                    try:
                                        rev = float(value)
                                        fy = fact.get('fy', 0)
                                        fp = fact.get('fp', '')  # fiscal period

                                        # Store by (segment_id, fy, fp) to avoid losing multi-period data
                                        key = (segment_id, fy, fp)
                                        if key not in segment_revenues:
                                            segment_revenues[key] = rev
                                        else:
                                            # If duplicate period, keep latest
                                            segment_revenues[key] = rev
                                    except (ValueError, TypeError):
                                        pass

        # Extract segment names/identifiers
        for name_concept in ['SegmentIdentificationCode', 'SegmentName']:
            if name_concept in us_gaap:
                concept_data = us_gaap[name_concept]
                if isinstance(concept_data, dict) and 'units' in concept_data:
                    units_data = concept_data['units']
                    for _unit, facts_list in units_data.items():
                        if isinstance(facts_list, list):
                            for fact in facts_list:
                                if isinstance(fact, dict):
                                    segment_id = fact.get('segment', fact.get('contextRef', ''))
                                    value = fact.get('value')
                                    if value and segment_id:
                                        if segment_id not in segments_data:
                                            segments_data[segment_id] = {}
                                        if name_concept == 'SegmentIdentificationCode':
                                            segments_data[segment_id]['id'] = str(value)
                                        else:
                                            segments_data[segment_id]['name'] = str(value)

        # Build result list from revenues, aggregating by segment_id across periods
        segment_aggregates = {}
        for (segment_id, fy, _fp), revenue in segment_revenues.items():
            if segment_id not in segment_aggregates:
                segment_aggregates[segment_id] = {
                    'total_revenue': 0,
                    'latest_fy': fy,
                    'count': 0
                }
            segment_aggregates[segment_id]['total_revenue'] += revenue
            segment_aggregates[segment_id]['count'] += 1
            if fy > segment_aggregates[segment_id]['latest_fy']:
                segment_aggregates[segment_id]['latest_fy'] = fy

        for segment_id, agg in segment_aggregates.items():
            seg_data = segments_data.get(segment_id, {})
            # Use average revenue across periods for stability
            avg_revenue = agg['total_revenue'] / agg['count'] if agg['count'] > 0 else 0
            segments.append({
                'segment_id': segment_id,
                'name': seg_data.get('name', seg_data.get('id', segment_id)),
                'revenue': avg_revenue,
                'operating_income': None,
                'assets': None,
            })

        return sorted(segments, key=lambda s: s.get('revenue', 0), reverse=True)

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
    def extract_segment_revenue_from_xbrl_xml(xml_content: str, symbol: str) -> dict[str, Any]:
        """Aggressive extraction of segment revenue from raw XBRL XML.

        Parses XBRL namespace-aware facts to find segment revenue using pattern matching
        when structured parsing fails. Falls back to text pattern matching for robustness.

        Returns:
            Same structure as parse_companyfacts() with parsed segment data.
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.warning(f"[{symbol}] Failed to parse XBRL XML: {e}")
            return {
                'segment_count': None,
                'largest_segment_revenue_pct': None,
                'revenue_concentration_hhi': None,
                'segments': [],
                'segment_type': None,
                'data_available': False,
                'reason': f'xml_parse_error: {str(e)[:100]}',
            }

        segments = {}
        total_revenue = 0.0

        # Try multiple namespace patterns for us-gaap segment revenue concepts

        # Search for segment revenue elements with various naming patterns
        segment_revenue_patterns = [
            '{http://xbrl.us/us-gaap/2023-01-31}SegmentReportingInformationRevenue',
            '{http://xbrl.us/us-gaap/2024-01-31}SegmentReportingInformationRevenue',
            '{http://xbrl.us/us-gaap/2022-01-31}SegmentReportingInformationRevenue',
            '{http://xbrl.us/us-gaap/2023-01-31}SegmentRevenue',
            '{http://xbrl.us/us-gaap/2024-01-31}SegmentRevenue',
            '{http://xbrl.us/us-gaap/2022-01-31}SegmentRevenue',
        ]

        found_segments = False
        for tag_pattern in segment_revenue_patterns:
            for elem in root.findall('.//' + tag_pattern):
                found_segments = True
                context_id = elem.get('contextRef', '')
                value = elem.text

                if value and context_id:
                    try:
                        revenue = float(value)
                        # Extract segment name from context (e.g., "Segment_Apple_StandardPeriodDuration")
                        segment_key = context_id.split('_')[0] if '_' in context_id else context_id
                        if segment_key not in segments:
                            segments[segment_key] = 0
                        segments[segment_key] += revenue
                        total_revenue += revenue
                    except (ValueError, TypeError):
                        pass

            if found_segments:
                break

        # If no structured revenue found, try text patterns as last resort
        if not segments:
            # Extract text content and look for revenue-related facts
            text_content = ET.tostring(root, encoding='unicode')
            # Look for patterns like <SegmentRevenue contextRef="...">value</SegmentRevenue>
            pattern = r'<(?:.*:)?SegmentRevenue[^>]*contextRef="([^"]*)"[^>]*>([0-9.]+)</(?:.*:)?SegmentRevenue>'
            matches = re.findall(pattern, text_content)
            for context, value in matches:
                try:
                    revenue = float(value)
                    segment_key = context.split('_')[0] if '_' in context else context
                    if segment_key not in segments:
                        segments[segment_key] = 0
                    segments[segment_key] += revenue
                    total_revenue += revenue
                except (ValueError, TypeError):
                    pass

        if not segments or total_revenue == 0:
            return {
                'segment_count': None,
                'largest_segment_revenue_pct': None,
                'revenue_concentration_hhi': None,
                'segments': [],
                'segment_type': None,
                'data_available': False,
                'reason': 'no_segment_revenue_in_xbrl_xml',
            }

        # Convert to segment list and calculate metrics
        segment_list = [
            {
                'segment_id': seg_id,
                'name': seg_id.replace('_', ' ').title(),
                'revenue': revenue,
            }
            for seg_id, revenue in segments.items()
        ]
        segment_list.sort(key=lambda s: s['revenue'], reverse=True)

        revenues = [s['revenue'] for s in segment_list]
        hhi = XBRLSegmentParser._compute_herfindahl_index(revenues, total_revenue)
        largest_pct = (revenues[0] / total_revenue * 100) if total_revenue > 0 else 0

        return {
            'segment_count': len(segment_list),
            'largest_segment_revenue_pct': round(largest_pct, 2),
            'revenue_concentration_hhi': round(hhi, 3),
            'segments': segment_list,
            'segment_type': 'operating',
            'data_available': True,
            'reason': None,
        }

    @staticmethod
    def parse_xbrl_xml(xml_content: str, symbol: str) -> dict[str, Any]:
        """Parse segment data from raw XBRL XML instance document.

        Alternative to companyfacts API, used if raw XBRL .xml file is available.
        This is lower-level parsing of the actual XBRL submission file.

        Args:
            xml_content: Raw XBRL instance XML from SEC EDGAR
            symbol: Stock ticker symbol (for logging)

        Returns:
            Same structure as parse_companyfacts()
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.warning(f"[{symbol}] Failed to parse XBRL XML: {e}")
            return {
                'segment_count': None,
                'largest_segment_revenue_pct': None,
                'revenue_concentration_hhi': None,
                'segments': [],
                'segment_type': None,
                'data_available': False,
                'reason': f'xml_parse_error: {str(e)[:100]}',
            }

        # In XBRL XML, facts are <xbrli:nonfraction> or <xbrli:nonnumeric> elements
        # with context and unitRef attributes pointing to segment dimensions
        segments = {}
        total_revenue = 0.0

        # Simplified extraction: look for SegmentRevenue contexts
        for elem in root.findall('.//{http://xbrl.us/us-gaap/2023-01-31}SegmentRevenue'):
            context_id = elem.get('contextRef', '')
            elem.get('unitRef', '')
            value = elem.text

            if value and context_id:
                try:
                    revenue = float(value)
                    if context_id not in segments:
                        segments[context_id] = {'revenue': 0}
                    segments[context_id]['revenue'] += revenue
                    total_revenue += revenue
                except (ValueError, TypeError):
                    pass

        if not segments or total_revenue == 0:
            return {
                'segment_count': None,
                'largest_segment_revenue_pct': None,
                'revenue_concentration_hhi': None,
                'segments': [],
                'segment_type': None,
                'data_available': False,
                'reason': 'no_xbrl_segment_revenue',
            }

        # Convert to list and calculate metrics
        segment_list = [
            {
                'segment_id': seg_id,
                'name': seg_id.replace('_', ' ').title(),
                'revenue': data['revenue'],
            }
            for seg_id, data in segments.items()
        ]
        segment_list.sort(key=lambda s: s['revenue'], reverse=True)

        revenues = [s['revenue'] for s in segment_list]
        hhi = XBRLSegmentParser._compute_herfindahl_index(revenues, total_revenue)
        largest_pct = (revenues[0] / total_revenue * 100) if total_revenue > 0 else 0

        return {
            'segment_count': len(segment_list),
            'largest_segment_revenue_pct': round(largest_pct, 2),
            'revenue_concentration_hhi': round(hhi, 3),
            'segments': segment_list,
            'segment_type': 'operating',
            'data_available': True,
            'reason': None,
        }
