#!/usr/bin/env python3
"""Debug script: check if segments are encoded in contextRef or other fields."""

from utils.external.sec_edgar_client import SecEdgarClient


def debug_segments_in_context(symbol: str) -> None:
    """Check if segment info is in contextRef or other fact attributes."""
    client = SecEdgarClient()

    print(f"\n=== Checking segment context for {symbol} ===\n")

    try:
        cik = client.symbol_to_cik(symbol)
        facts = client.get_company_facts(cik)
    except Exception as e:
        print(f"Failed to fetch data: {e}")
        return

    us_gaap = facts.get('facts', {}).get('us-gaap', {})

    # Check SegmentReportingInformationOperatingIncomeLoss for context patterns
    if 'SegmentReportingInformationOperatingIncomeLoss' in us_gaap:
        print("=== SegmentReportingInformationOperatingIncomeLoss facts ===")
        concept_data = us_gaap['SegmentReportingInformationOperatingIncomeLoss']
        units = concept_data.get('units', {})
        for _unit, facts_list in units.items():
            for i, fact in enumerate(facts_list[:2]):  # First 2 facts
                print(f"\nFact {i}:")
                for k, v in fact.items():
                    print(f"  {k}: {v}")

    # Check if ANY fact has segment dimension
    print("\n\n=== Searching for facts with 'segment' or 'Segment' in any field ===")
    found_segment_facts = False
    for concept_name, concept_data in list(us_gaap.items())[:50]:  # First 50 concepts
        if isinstance(concept_data, dict) and 'units' in concept_data:
            units = concept_data.get('units', {})
            for _unit, facts_list in units.items():
                if isinstance(facts_list, list):
                    for fact in facts_list:
                        if isinstance(fact, dict):
                            # Check all fields for segment
                            for k, v in fact.items():
                                if isinstance(v, str) and 'segment' in v.lower():
                                    print(f"{concept_name}: {k}={v}")
                                    found_segment_facts = True
                                    break
                        if found_segment_facts:
                            break
                if found_segment_facts:
                    break

    if not found_segment_facts:
        print("No segment dimensions found in first 50 concepts")

    # Check what forms are in the filing data
    print("\n\n=== Forms available in companyfacts ===")
    forms_found = set()
    for concept_name, concept_data in us_gaap.items():
        if isinstance(concept_data, dict) and 'units' in concept_data:
            units = concept_data.get('units', {})
            for _unit, facts_list in units.items():
                if isinstance(facts_list, list):
                    for fact in facts_list:
                        if isinstance(fact, dict):
                            form = fact.get('form')
                            if form:
                                forms_found.add(form)

    print(f"Forms in data: {sorted(forms_found)}")

    # Check latest 10-K specifically
    print("\n\n=== Latest 10-K data ===")
    latest_10k_filings = {}
    for concept_name, concept_data in us_gaap.items():
        if isinstance(concept_data, dict) and 'units' in concept_data:
            units = concept_data.get('units', {})
            for _unit, facts_list in units.items():
                if isinstance(facts_list, list):
                    for fact in facts_list:
                        if isinstance(fact, dict) and fact.get('form') == '10-K':
                            filed_date = fact.get('filed', '')
                            if filed_date not in latest_10k_filings:
                                latest_10k_filings[filed_date] = []
                            latest_10k_filings[filed_date].append((concept_name, fact))

    if latest_10k_filings:
        latest_date = sorted(latest_10k_filings.keys())[-1]
        print(f"Latest 10-K: {latest_date}")
        concepts_in_latest = list({c[0] for c in latest_10k_filings[latest_date]})
        print(f"Concepts with data in latest 10-K: {len(concepts_in_latest)}")
        segment_concepts = [c for c in concepts_in_latest if 'segment' in c.lower()]
        print(f"  Segment-related: {segment_concepts}")

if __name__ == "__main__":
    debug_segments_in_context("AAPL")
