#!/usr/bin/env python3
"""Research SEC EDGAR filing structure and Form 4 XML discovery.

This script:
1. Fetches actual recent Form 4 filings from SEC API
2. Tests the directory structure to understand XML file naming
3. Prototypes the filing index parser
"""

import requests
from typing import Optional

EDGAR_BASE = "https://data.sec.gov"
HEADERS = {
    "User-Agent": "algo-trading argeropolos@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}


def get_submissions(cik: str) -> dict:
    """Fetch submissions list (metadata about all filings)."""
    url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
    print(f"Fetching submissions from: {url}")
    resp = requests.get(url, timeout=10, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def find_recent_form4(cik: str) -> Optional[tuple[str, str]]:
    """Find a recent Form 4 filing for a company.

    Returns:
        (accession_number, filing_date) or None
    """
    try:
        data = get_submissions(cik)
    except Exception as e:
        print(f"Failed to fetch submissions: {e}")
        return None

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accessions = filings.get("accessionNumber", [])
    filing_dates = filings.get("filingDate", [])

    for i, form_type in enumerate(forms):
        if form_type == "4" and i < len(accessions):
            accession = accessions[i]
            filing_date = filing_dates[i] if i < len(filing_dates) else "unknown"
            return (accession, filing_date)

    return None


def test_filing_directory(cik: str, accession_number: str) -> None:
    """Test accessing a filing's directory structure."""
    path_accession = accession_number.replace("-", "")
    cik_padded = str(cik).zfill(10)

    # Try different index formats
    index_urls = [
        f"https://www.sec.gov/Archives/edgar/{cik_padded}/{path_accession}/index.html",
        f"https://www.sec.gov/Archives/edgar/{cik_padded}/{path_accession}/index.htm",
        f"https://www.sec.gov/Archives/edgar/{cik_padded}/{path_accession}/",
        f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={cik}&accession_number={accession_number}&xbrl_type=v",
    ]

    print(f"\nTesting filing directory for accession: {accession_number}")
    print(f"CIK: {cik_padded}, Path: {path_accession}\n")

    for url in index_urls:
        print(f"Trying: {url}")
        try:
            resp = requests.get(url, timeout=10, headers=HEADERS)
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                # Try to extract XML filenames from response
                content = resp.text
                if ".xml" in content:
                    print("  Contains XML references")
                    # Extract XML filenames (simple pattern match)
                    import re
                    xml_files = re.findall(r'([a-zA-Z0-9_-]+\.xml)', content)
                    if xml_files:
                        print(f"  XML files found:")
                        for xml_file in set(xml_files)[:5]:  # Show first 5 unique
                            print(f"    - {xml_file}")
                else:
                    print("  No XML references in response")
        except Exception as e:
            print(f"  Error: {type(e).__name__}")

    # Also try to directly access common XML filenames
    print(f"\nDirect XML access test:")
    common_names = ["form4.xml", "d*.xml", "sc13g.xml"]
    # Just test form4.xml since we don't know actual names yet
    xml_url = f"https://www.sec.gov/Archives/edgar/{cik_padded}/{path_accession}/form4.xml"
    print(f"Trying: {xml_url}")
    try:
        resp = requests.get(xml_url, timeout=10, headers=HEADERS)
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            print("  [OK] form4.xml exists!")
    except Exception as e:
        print(f"  Error: {e}")


def main():
    print("=" * 70)
    print("SEC EDGAR Filing Structure Research")
    print("=" * 70)
    print()

    # Test with Apple (well-known company with recent Form 4 filings)
    apple_cik = "0000320193"

    print("Step 1: Find recent Form 4 filing for Apple")
    print("-" * 70)
    result = find_recent_form4(apple_cik)
    if result:
        accession, filing_date = result
        print(f"Found: {accession} (filed: {filing_date})")
        test_filing_directory(apple_cik, accession)
    else:
        print("No Form 4 found")

    print("\n" + "=" * 70)
    print("Research complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
