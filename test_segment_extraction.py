#!/usr/bin/env python3
"""Quick test of aggressive segment extraction."""

import sys

from utils.external.sec_edgar_client import SecEdgarClient
from utils.external.sec_xbrl_segments import XBRLSegmentParser


def test_segment_extraction(symbol: str) -> None:
    """Test companyfacts vs raw XBRL extraction."""
    client = SecEdgarClient()

    print(f"\n{'='*60}")
    print(f"Testing segment extraction for {symbol}")
    print(f"{'='*60}\n")

    try:
        cik = client.symbol_to_cik(symbol)
        print(f"[1] Got CIK: {cik}")
    except Exception as e:
        print(f"[FAIL] Failed to get CIK: {e}")
        return

    # Test 1: companyfacts API
    print("\n[TEST 1] Trying companyfacts API...")
    try:
        facts = client.get_company_facts(cik)
        result = XBRLSegmentParser.parse_companyfacts(facts, symbol)
        print(f"  Result: data_available={result.get('data_available')}")
        if result.get('data_available'):
            print(f"  Segments: {len(result.get('segments', []))} found")
            print(f"  HHI: {result.get('revenue_concentration_hhi')}")
        else:
            print(f"  Reason: {result.get('reason')}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test 2: Raw XBRL extraction
    print("\n[TEST 2] Trying raw XBRL XML extraction...")
    try:
        submissions = client.get_submissions(cik)
        filings = submissions.get('filings', {}).get('recent', {})

        # SEC filings format is columnar
        forms = filings.get('form', [])
        accessions = filings.get('accessionNumber', [])

        latest_10k = None
        for i, form in enumerate(forms):
            if form == '10-K':
                latest_10k = accessions[i]
                break

        if not latest_10k:
            print("  No 10-K filing found")
        else:
            accession = latest_10k
            print(f"  Latest 10-K: {accession}")
            try:
                xml = client.get_filing_xml(cik, accession, '10-K')
                print(f"  XML fetched: {len(xml)} bytes")
                result = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(xml, symbol)
                print(f"  Result: data_available={result.get('data_available')}")
                if result.get('data_available'):
                    print(f"  Segments: {len(result.get('segments', []))} found")
                    for seg in result.get('segments', []):
                        print(f"    - {seg.get('name')}: ${seg.get('revenue'):,.0f}")
                    print(f"  HHI: {result.get('revenue_concentration_hhi')}")
                else:
                    print(f"  Reason: {result.get('reason')}")
            except Exception as e:
                print(f"  Failed to fetch/parse XML: {e}")

    except Exception as e:
        print(f"  ERROR: {e}")

if __name__ == "__main__":
    symbols = sys.argv[1:] if len(sys.argv) > 1 else ["AAPL", "MSFT"]
    for symbol in symbols:
        test_segment_extraction(symbol)
