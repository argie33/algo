#!/usr/bin/env python3
"""Debug SEC companyfacts API to see ALL available concepts."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.external.sec_edgar_client import SecEdgarClient

def show_all_segment_concepts(symbol: str):
    """Show all available segment-related concepts."""
    print(f"\n{'='*100}")
    print(f"ALL SEGMENT CONCEPTS FOR: {symbol}")
    print(f"{'='*100}")

    try:
        sec_client = SecEdgarClient()
        cik = sec_client.symbol_to_cik(symbol)

        # Fetch companyfacts
        facts = sec_client.get_company_facts(cik)

        if 'facts' not in facts or 'us-gaap' not in facts['facts']:
            print("No us-gaap facts found")
            return

        us_gaap = facts['facts']['us-gaap']

        # Get ALL segment-related concepts
        segment_concepts = sorted([k for k in us_gaap.keys() if 'segment' in k.lower()])
        print(f"\nTotal segment concepts: {len(segment_concepts)}\n")

        for i, concept in enumerate(segment_concepts, 1):
            print(f"{i:2}. {concept}")

        # For MSFT which has NumberOfReportableSegments, let's see what data is there
        if symbol == 'MSFT' and 'NumberOfReportableSegments' in us_gaap:
            print(f"\n{'='*100}")
            print(f"SEGMENT COUNT DATA FOR {symbol}:")
            print(f"{'='*100}")
            concept_data = us_gaap['NumberOfReportableSegments']
            if 'units' in concept_data:
                units = concept_data['units']
                for unit_name, facts_list in units.items():
                    print(f"\nUnit: {unit_name}")
                    if isinstance(facts_list, list):
                        for fact in facts_list[:5]:
                            print(f"  {fact}")

        # Try to find revenue-like concepts
        print(f"\n{'='*100}")
        print(f"REVENUE-RELATED CONCEPTS FOR {symbol}:")
        print(f"{'='*100}")
        revenue_concepts = sorted([k for k in us_gaap.keys() if 'revenue' in k.lower()])
        for i, concept in enumerate(revenue_concepts[:30], 1):
            print(f"{i:2}. {concept}")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    for symbol in ['AAPL', 'MSFT']:
        show_all_segment_concepts(symbol)
