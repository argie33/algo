#!/usr/bin/env python3
"""Research SEC XBRL API for Form 4 filings and data access patterns.

The SEC provides different ways to access filing data:
1. XBRL Submissions API: /submissions/CIK{cik}.json - metadata about filings
2. XBRL Company Facts API: /api/xbrl/companyfacts/CIK{cik}.json - all XBRL data
3. XBRL Filer API: /api/xbrl/filer-search - search for filings

For insider transactions (Form 4), we need to understand:
- What XBRL data is available for Form 4 filings
- How to extract insider transaction details
"""

import requests
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "algo-trading argeropolos@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}


def fetch_xbrl_filings_api():
    """Test accessing XBRL filings API directly."""
    print("Testing XBRL Filings API")
    print("=" * 70)

    # SEC provides a filings API that might have Form 4 metadata
    urls = [
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=4&dateb=&owner=exclude&count=10&search_text=",
        "https://data.sec.gov/api/xbrl/filer-search?query=Apple&ciks=320193&forms=4&limit=10",
    ]

    for url in urls:
        print(f"\nTrying: {url}")
        try:
            resp = requests.get(url, timeout=10, headers=HEADERS)
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                # Show first 500 chars of response
                content = resp.text
                if len(content) < 500:
                    print(f"  Response:\n{content}")
                else:
                    print(f"  Response (first 500 chars):\n{content[:500]}")
        except Exception as e:
            print(f"  Error: {e}")


def check_submissions_structure():
    """Examine the submissions API response structure."""
    print("\n\nExamining Submissions API Structure")
    print("=" * 70)

    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    print(f"Fetching: {url}\n")

    try:
        resp = requests.get(url, timeout=10, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

        # Show structure
        print("Top-level keys:")
        for key in data.keys():
            print(f"  - {key}")

        # Look at recent filings
        if "filings" in data:
            print("\nFilings structure:")
            filings = data["filings"]
            for key in filings.keys():
                print(f"  - {key}")

            recent = filings.get("recent", {})
            print(f"\nRecent filings fields:")
            for key in recent.keys():
                print(f"  - {key}")

            # Show first Form 4 filing details
            forms = recent.get("form", [])
            accessions = recent.get("accessionNumber", [])
            dates = recent.get("filingDate", [])

            for i, form_type in enumerate(forms[:5]):
                if form_type == "4":
                    print(f"\nExample Form 4 filing:")
                    print(f"  Accession: {accessions[i]}")
                    print(f"  Date: {dates[i]}")
                    # Check for filing details
                    if "primaryDocument" in recent:
                        print(f"  Primary Doc: {recent['primaryDocument'][i]}")
                    break

    except Exception as e:
        print(f"Error: {e}")


def check_accession_details():
    """Check what's available for a specific accession number."""
    print("\n\nChecking Accession Details")
    print("=" * 70)

    # First get an accession number
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    resp = requests.get(url, timeout=10, headers=HEADERS)
    data = resp.json()

    recent = data["filings"]["recent"]
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])

    # Find a Form 4
    for i, form_type in enumerate(forms):
        if form_type == "4":
            accession = accessions[i]
            path_accession = accession.replace("-", "")
            cik = "0000320193"
            cik_padded = str(cik).zfill(10)

            print(f"\nAccession: {accession}")
            print(f"Path: {path_accession}\n")

            # Try different ways to access the filing
            urls = [
                # Official SEC Archives (may be moved to newer system)
                f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={cik}&accession_number={accession}&xbrl_type=v",
                # Direct filing viewer
                f"https://www.sec.gov/Archives/edgar/{cik_padded}/{path_accession}/",
                # Try JSON API for this filing
                f"https://data.sec.gov/submissions/{accession}.json",
                # Check if there's a forms filing endpoint
                f"https://data.sec.gov/api/xbrl/submissions/CIK{cik}/{accession}",
            ]

            for test_url in urls:
                print(f"Trying: {test_url}")
                try:
                    resp = requests.get(test_url, timeout=10, headers=HEADERS)
                    print(f"  Status: {resp.status_code}")
                    if resp.status_code == 200 and "json" in test_url:
                        print(f"  [FOUND JSON API]")
                        data = resp.json()
                        print(f"  Keys: {list(data.keys())[:5]}")
                except Exception as e:
                    pass

            break


if __name__ == "__main__":
    fetch_xbrl_filings_api()
    check_submissions_structure()
    check_accession_details()
