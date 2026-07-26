#!/usr/bin/env python3
"""Debug script: inspect SEC companyfacts API response to understand segment concepts."""

import sys

from utils.external.sec_edgar_client import SecEdgarClient


def debug_companyfacts(symbol: str) -> None:
    """Fetch and inspect companyfacts for a symbol."""
    client = SecEdgarClient()

    print(f"\n=== Debugging companyfacts for {symbol} ===\n")

    try:
        cik = client.symbol_to_cik(symbol)
        print(f"[OK] CIK: {cik}")
    except Exception as e:
        print(f"[FAIL] Failed to get CIK: {e}")
        return

    try:
        facts = client.get_company_facts(cik)
        print("[OK] Got companyfacts response")
    except Exception as e:
        print(f"[FAIL] Failed to get companyfacts: {e}")
        return

    # Check structure
    print(f"\nTop-level keys: {list(facts.keys())}")

    if 'facts' not in facts:
        print("ERROR: No 'facts' key in response")
        return

    us_gaap = facts.get('facts', {}).get('us-gaap', {})
    print(f"\nTotal us-gaap concepts: {len(us_gaap)}")

    # List all segment-related concepts
    print("\n=== Segment-related concepts ===")
    segment_concepts = [k for k in us_gaap.keys() if 'segment' in k.lower()]
    print(f"Found {len(segment_concepts)} segment-related concepts:")
    for concept in sorted(segment_concepts):
        concept_data = us_gaap[concept]
        if isinstance(concept_data, dict):
            units = concept_data.get('units', {})
            print(f"  {concept}")
            print(f"    Units: {list(units.keys())}")
            for unit, facts_list in list(units.items())[:1]:  # Show first unit
                if isinstance(facts_list, list):
                    print(f"      {unit}: {len(facts_list)} facts")
                    if facts_list:
                        sample = facts_list[0]
                        print(f"        Sample: {sample}")

    # Check for revenue concepts
    print("\n=== Revenue-related concepts ===")
    revenue_concepts = [k for k in us_gaap.keys() if 'revenue' in k.lower()]
    print(f"Found {len(revenue_concepts)} revenue-related concepts:")
    for concept in sorted(revenue_concepts)[:10]:  # First 10
        print(f"  {concept}")

    # Check what "Revenues" has
    if 'Revenues' in us_gaap:
        print("\n=== Checking 'Revenues' concept ===")
        revenues_data = us_gaap['Revenues']
        if isinstance(revenues_data, dict) and 'units' in revenues_data:
            units = revenues_data['units']
            print(f"Units: {list(units.keys())}")
            for unit, facts_list in units.items():
                if isinstance(facts_list, list):
                    print(f"  {unit}: {len(facts_list)} facts")
                    # Check for segment dimension
                    for fact in facts_list[:3]:
                        if isinstance(fact, dict):
                            print(f"    Fact keys: {list(fact.keys())}")
                            print(f"    Full fact: {fact}")
                            break

if __name__ == "__main__":
    symbols = sys.argv[1:] if len(sys.argv) > 1 else ["AAPL", "MSFT"]
    for symbol in symbols:
        debug_companyfacts(symbol)
