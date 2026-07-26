#!/usr/bin/env python3
"""Debug SEC companyfacts API to understand XBRL segment data availability."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.external.sec_edgar_client import SecEdgarClient
from utils.external.sec_xbrl_segments import XBRLSegmentParser

def debug_companyfacts(symbol: str):
    """Fetch and analyze companyfacts for a symbol."""
    print(f"\n{'='*80}")
    print(f"DEBUG: {symbol}")
    print(f"{'='*80}")

    try:
        sec_client = SecEdgarClient()
        cik = sec_client.symbol_to_cik(symbol)
        print(f"CIK: {cik}")

        # Fetch companyfacts
        facts = sec_client.get_company_facts(cik)
        print(f"\nCompanyfacts structure:")
        print(f"  - Has 'facts' key: {'facts' in facts}")

        if 'facts' in facts:
            fact_keys = list(facts['facts'].keys())
            print(f"  - Fact taxonomies: {fact_keys}")

            if 'us-gaap' in facts['facts']:
                us_gaap = facts['facts']['us-gaap']
                print(f"\n  - Total us-gaap concepts: {len(us_gaap)}")

                # Search for segment-related concepts
                segment_concepts = [k for k in us_gaap.keys() if 'segment' in k.lower()]
                print(f"\n  - Segment-related concepts found: {len(segment_concepts)}")
                for concept in sorted(segment_concepts)[:20]:  # First 20
                    print(f"      - {concept}")

                # Check if specific expected concepts exist
                expected_concepts = [
                    'SegmentReportingInformationRevenue',
                    'SegmentRevenue',
                    'SegmentNumber',
                    'NumberOfReportableSegments',
                    'Revenues',
                ]
                print(f"\n  - Expected concept availability:")
                for concept in expected_concepts:
                    exists = concept in us_gaap
                    print(f"      {concept}: {exists}")

                # If segment revenue exists, show sample data
                if 'SegmentReportingInformationRevenue' in us_gaap:
                    print(f"\n  SegmentReportingInformationRevenue data sample:")
                    concept_data = us_gaap['SegmentReportingInformationRevenue']
                    if 'units' in concept_data:
                        units = concept_data['units']
                        for unit_name, facts_list in list(units.items())[:2]:
                            print(f"    Unit: {unit_name}")
                            if isinstance(facts_list, list):
                                for fact in facts_list[:2]:
                                    print(f"      {fact}")

                # Try the parser
                print(f"\n  - Parser Result:")
                segment_data = XBRLSegmentParser.parse_companyfacts(facts, symbol)
                print(f"      data_available: {segment_data.get('data_available')}")
                print(f"      reason: {segment_data.get('reason')}")
                print(f"      segment_count: {segment_data.get('segment_count')}")
                print(f"      segments: {segment_data.get('segments')}")

        else:
            print("  - No 'facts' key in response")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    for symbol in ['AAPL', 'MSFT']:
        debug_companyfacts(symbol)
