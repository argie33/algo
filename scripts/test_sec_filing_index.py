#!/usr/bin/env python3
"""Test SEC EDGAR filing index discovery - research script for Phase 2 implementation.

This script tests the SEC EDGAR directory structure to understand how to properly
discover XML filenames in Form 4 and Schedule 13G filings.

SEC EDGAR directory structure:
- https://www.sec.gov/Archives/edgar/{cik}/{accession_nodash}/
- Contains index.html with file listings
- XML files have varying names based on form type
"""

import re
import requests
from html.parser import HTMLParser
from typing import Optional


class FilingIndexParser(HTMLParser):
    """Parse SEC EDGAR filing index HTML to extract XML file paths."""

    def __init__(self):
        super().__init__()
        self.files = []
        self.in_table = False
        self.current_row = []
        self.in_td = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
        elif tag == "tr" and self.in_table:
            self.current_row = []
        elif tag == "td" and self.in_table:
            self.in_td = True

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif tag == "tr" and self.in_table:
            if len(self.current_row) >= 2:
                # Each row has: filename, description, size, type, date
                self.files.append(self.current_row)
            self.current_row = []
        elif tag == "td" and self.in_table:
            self.in_td = False

    def handle_data(self, data):
        if self.in_td:
            self.current_row.append(data.strip())


def discover_filing_xml(cik: str, accession_number: str, form_type: str) -> Optional[str]:
    """Discover XML filename for a specific form type from SEC EDGAR filing index.

    Args:
        cik: Company CIK
        accession_number: Filing accession number (e.g., "0001193125-24-001234")
        form_type: Form type ("4", "13G", "13G/A")

    Returns:
        Filename of the XML document (e.g., "form4.xml", "d12345d4.xml") or None if not found
    """
    # Construct filing index URL
    path_accession = accession_number.replace("-", "")
    cik_padded = str(cik).zfill(10)
    index_url = f"https://www.sec.gov/Archives/edgar/{cik_padded}/{path_accession}/index.html"

    print(f"Fetching index from: {index_url}")

    try:
        headers = {
            "User-Agent": "algo-trading argeropolos@gmail.com",
            "Accept-Encoding": "gzip, deflate",
        }
        resp = requests.get(index_url, timeout=10, headers=headers)
        if resp.status_code == 404:
            print(f"  [Index not found (404)]")
            return None
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [Failed to fetch: {e}]")
        return None

    # Parse the index HTML
    parser = FilingIndexParser()
    try:
        parser.feed(resp.text)
    except Exception as e:
        print(f"  [Failed to parse index: {e}]")
        return None

    # Find XML files matching the form type
    print(f"  [Found {len(parser.files)} files in index]")

    xml_candidates = []
    for row in parser.files:
        if len(row) < 1:
            continue
        filename = row[0]

        # Look for XML files
        if not filename.endswith(".xml"):
            continue

        print(f"    - {filename}")

        # Match based on form type
        if form_type == "4":
            # Form 4 XML files typically contain "4.xml" or are named d*.xml
            if "4.xml" in filename or (filename.startswith("d") and filename.endswith(".xml")):
                xml_candidates.append(filename)
        elif form_type in ("13G", "13G/A"):
            # Schedule 13G XML files
            if "13g" in filename.lower() or "sc13g" in filename.lower():
                xml_candidates.append(filename)

    if xml_candidates:
        # Return first match (ideally there's only one)
        chosen = xml_candidates[0]
        print(f"  [OK] Selected: {chosen}")
        return chosen

    print(f"  [FAIL] No XML file found for form type {form_type}")
    return None


def test_form4_discovery():
    """Test discovering Form 4 XML files for a known filing."""
    print("=" * 70)
    print("TEST 1: Form 4 Discovery")
    print("=" * 70)

    # Apple (AAPL): CIK 0000320193
    # Known Form 4 filing: 0001193125-24-035460 (around March 2024)
    test_cases = [
        ("0000320193", "0001193125-24-035460", "4", "Apple Form 4"),
        ("0000320193", "0001193125-24-032887", "4", "Apple Form 4"),
    ]

    for cik, accession, form_type, label in test_cases:
        print(f"\n{label}:")
        result = discover_filing_xml(cik, accession, form_type)
        if result:
            print(f"  [OK] {result}\n")
        else:
            print(f"  [FAIL] Could not discover XML\n")


def test_schedule13g_discovery():
    """Test discovering Schedule 13G XML files."""
    print("=" * 70)
    print("TEST 2: Schedule 13G Discovery")
    print("=" * 70)

    # Microsoft (MSFT): CIK 0000789019
    # Known 13G filing: various institutional holdings
    test_cases = [
        ("0000789019", "0001193125-24-028462", "13G", "MSFT Schedule 13G"),
    ]

    for cik, accession, form_type, label in test_cases:
        print(f"\n{label}:")
        result = discover_filing_xml(cik, accession, form_type)
        if result:
            print(f"  [OK] {result}\n")
        else:
            print(f"  [FAIL] Could not discover XML\n")


if __name__ == "__main__":
    print("SEC EDGAR Filing Index Discovery Test")
    print("=" * 70)
    print()

    test_form4_discovery()
    test_schedule13g_discovery()

    print("=" * 70)
    print("Research complete. Results inform sec_edgar_client implementation.")
    print("=" * 70)
