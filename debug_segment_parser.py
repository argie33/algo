#!/usr/bin/env python3
"""Debug segment parser to see what data is actually available."""

from utils.external.sec_edgar_client import SecEdgarClient
from utils.external.sec_xbrl_segments import XBRLSegmentParser

client = SecEdgarClient()

# Test companies with known/expected segments
test_symbols = {
    'JBLU': 'JetBlue - airlines (HAS segments)',
    'CI': 'Cigna - insurance (HAS segments)',
    'BRK': 'Berkshire - conglomerate (HAS segments)',
    'AAPL': 'Apple - reference (single segment)',
}

print("Checking companyfacts for segment data...")
print("=" * 70)

for symbol, description in test_symbols.items():
    print(f"\n{symbol}: {description}")
    try:
        # Get CIK
        cik = client.symbol_to_cik(symbol)

        # Fetch companyfacts
        facts = client.get_company_facts(cik)
        us_gaap = facts.get('facts', {}).get('us-gaap', {})

        # Check for segment concepts
        segment_concepts = [k for k in us_gaap.keys() if 'segment' in k.lower() or 'revenue' in k.lower()]

        print(f"  CIK: {cik}")
        print(f"  Total concepts: {len(us_gaap)}")
        print(f"  Segment-related concepts: {len(segment_concepts)}")

        if segment_concepts:
            print("  Segment concepts found:")
            for concept in sorted(segment_concepts)[:10]:
                concept_data = us_gaap[concept]
                if isinstance(concept_data, dict) and 'units' in concept_data:
                    fact_count = sum(len(v) if isinstance(v, list) else 0
                                    for v in concept_data['units'].values())
                    print(f"    - {concept}: {fact_count} facts")

        # Try parsing
        segment_data = XBRLSegmentParser.parse_companyfacts(facts, symbol)
        print("  Parser result:")
        print(f"    - data_available: {segment_data.get('data_available')}")
        print(f"    - reason: {segment_data.get('reason')}")
        print(f"    - segment_count: {segment_data.get('segment_count')}")
        print(f"    - segments found: {len(segment_data.get('segments', []))}")

    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")

print("\n" + "=" * 70)
print("CONCLUSION:")
print("If segment data is available, parser should extract it.")
print("If all return 'no segment revenue data', then companyfacts doesn't")
print("have the segment revenue concepts for ANY of our test companies.")
