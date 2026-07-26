#!/usr/bin/env python3
"""Test the full segment extraction flow end-to-end."""

import logging
from datetime import date
from utils.external.sec_edgar_client import SecEdgarClient
from utils.external.sec_xbrl_segments import XBRLSegmentParser

logging.basicConfig(level=logging.DEBUG, format='%(name)s: %(message)s')
logger = logging.getLogger(__name__)

def find_latest_10k(submissions):
    """Find most recent 10-K filing."""
    try:
        recent = submissions.get('filings', {}).get('recent', {})
        forms = recent.get('form', [])
        accessions = recent.get('accessionNumber', [])  # Note: accessionNumber, not accession
        dates = recent.get('filingDate', [])

        for i, form in enumerate(forms):
            if form == '10-K':
                return {
                    'form': form,
                    'accession': accessions[i],
                    'date': dates[i]
                }
    except Exception as e:
        logger.error(f"Failed to find 10-K: {e}")
    return None

client = SecEdgarClient()
symbol = 'JBLU'

print(f"Testing full segment extraction for {symbol}")
print("=" * 70)

try:
    # Step 1: Get CIK
    cik = client.symbol_to_cik(symbol)
    print(f"✓ CIK: {cik}")

    # Step 2: Try companyfacts first (will likely have no segment revenue)
    print("\n1. Trying companyfacts API...")
    facts = client.get_company_facts(cik)
    result = XBRLSegmentParser.parse_companyfacts(facts, symbol)
    print(f"   Result: data_available={result['data_available']}, reason={result['reason']}")

    if not result['data_available']:
        print("\n2. Companyfacts failed, trying raw XBRL XML from 10-K...")

        # Step 3: Get submissions to find 10-K
        submissions = client.get_submissions(cik)
        latest_10k = find_latest_10k(submissions)

        if latest_10k:
            print(f"   Found 10-K: {latest_10k['form']} on {latest_10k['date']}")

            # Step 4: Fetch the 10-K XML
            print(f"   Fetching filing XML...")
            try:
                xml_content = client.get_filing_xml(cik, latest_10k['accession'], '10-K')
                print(f"   ✓ Fetched {len(xml_content)} bytes of XBRL XML")

                # Step 5: Parse segment revenue from XML
                print(f"   Parsing segment revenue from XBRL...")
                xml_result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml_content, symbol)
                print(f"   Result: data_available={xml_result['data_available']}")
                print(f"           segment_count={xml_result['segment_count']}")
                print(f"           segments_found={len(xml_result['segments'])}")

                if xml_result['data_available'] and xml_result['segments']:
                    print(f"\n   ✓✓✓ SUCCESS! Found segment data!")
                    for seg in xml_result['segments'][:3]:
                        print(f"        {seg.get('name', 'Unknown')}: ${seg.get('revenue', 0):,.0f}")
                else:
                    print(f"\n   ✗ No segment data found in XML either")
                    print(f"     Reason: {xml_result['reason']}")

            except Exception as e:
                print(f"   ✗ Failed to fetch/parse XML: {type(e).__name__}: {e}")
        else:
            print("   ✗ No 10-K filing found")

except Exception as e:
    print(f"✗ ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("RESULT: If segment data is found, the full flow works correctly.")
print("If not, we've identified where the extraction is failing.")
