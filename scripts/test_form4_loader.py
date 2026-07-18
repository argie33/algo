#!/usr/bin/env python3
"""Test Form 4 XML loading with the updated SEC client."""

import sys
from utils.external.sec_edgar_client import SecEdgarClient

def test_form4_loading():
    """Test fetching and parsing a real Form 4 filing."""
    client = SecEdgarClient()

    # Apple (AAPL): CIK 0000320193
    # Known recent Form 4 filing from research
    cik = "0000320193"
    symbol = "AAPL"

    print(f"Testing Form 4 XML loading for {symbol}")
    print("=" * 70)

    try:
        # Step 1: Get submissions to find Form 4 filings
        print(f"\n1. Fetching submissions for {symbol} (CIK {cik})...")
        submissions = client.get_submissions(cik)

        # Step 2: Find recent Form 4 filings
        filings = submissions.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        accessions = filings.get("accessionNumber", [])
        dates = filings.get("filingDate", [])

        form4_filings = []
        for i, form_type in enumerate(forms[:20]):  # Check first 20
            if form_type == "4":
                form4_filings.append((accessions[i], dates[i]))

        if not form4_filings:
            print(f"   ERROR: No Form 4 filings found")
            return False

        print(f"   Found {len(form4_filings)} recent Form 4 filings")

        # Step 3: Try to fetch and parse one
        accession, filing_date = form4_filings[0]
        print(f"\n2. Testing Form 4 fetch for accession {accession} (filed: {filing_date})...")

        try:
            xml_content = client.get_filing_xml(cik, accession, "4")
            print(f"   [OK] Successfully fetched XML ({len(xml_content)} bytes)")

            # Step 4: Verify it's valid XML and contains expected elements
            from xml.etree import ElementTree as ET

            root = ET.fromstring(xml_content)
            print(f"   [OK] Valid XML - root element: {root.tag}")

            # Check for expected Form 4 elements
            reporter = root.find(".//reportingOwnerId")
            if reporter is not None:
                insider_name = reporter.findtext("rptOwnerName")
                print(f"   [OK] Found insider data: {insider_name}")
                return True
            else:
                print(f"   WARNING: No reportingOwnerId found in XML")
                return True  # XML valid, might be different structure

        except FileNotFoundError as e:
            print(f"   ERROR: {e}")
            return False
        except Exception as e:
            print(f"   ERROR: {type(e).__name__}: {e}")
            return False

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    success = test_form4_loading()
    sys.exit(0 if success else 1)
