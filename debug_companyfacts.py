#!/usr/bin/env python3
"""Debug companyfacts API structure to understand segment parsing."""

import json
from utils.external.sec_edgar_client import SecEdgarClient

# Test with AAPL
client = SecEdgarClient()
cik = client.symbol_to_cik('AAPL')
print(f'AAPL CIK: {cik}')

# Get companyfacts
facts = client.get_company_facts(cik)

us_gaap = facts.get('facts', {}).get('us-gaap', {})
print(f'Total us-gaap concepts: {len(us_gaap)}')

# List all segment-related concepts
segment_concepts = sorted([k for k in us_gaap.keys() if 'segment' in k.lower() or 'revenue' in k.lower()])
print(f'\n=== Segment/Revenue Concepts ({len(segment_concepts)}) ===')
for concept in segment_concepts[:30]:
    print(f'  {concept}')

# Look for specific ones the parser needs
needed = [
    'SegmentReportingInformationRevenue',
    'SegmentReportingInformationRevenueFromExternalCustomers',
    'SegmentRevenue',
    'SegmentNumber',
    'NumberOfReportableSegments',
    'SegmentIdentificationCode',
    'SegmentName',
]

print(f'\n=== Parser-Required Concepts ===')
for concept in needed:
    exists = concept in us_gaap
    print(f'  {concept}: {"✓ EXISTS" if exists else "✗ MISSING"}')

# If SegmentRevenue exists, show its structure
if 'SegmentRevenue' in us_gaap:
    concept_data = us_gaap['SegmentRevenue']
    print(f'\n=== SegmentRevenue Structure ===')
    print(f'  Keys: {list(concept_data.keys())}')
    if 'units' in concept_data:
        units = concept_data['units']
        print(f'  Unit types: {list(units.keys())}')
        for unit, facts_list in list(units.items())[:2]:
            print(f'\n  Samples from {unit}:')
            for fact in facts_list[:2]:
                print(f'    {json.dumps(fact, indent=6)[:200]}...')
