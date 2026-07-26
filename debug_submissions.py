#!/usr/bin/env python3
"""Debug submissions response structure."""

from utils.external.sec_edgar_client import SecEdgarClient

client = SecEdgarClient()
cik = client.symbol_to_cik("AAPL")
print(f"CIK: {cik}")

submissions = client.get_submissions(cik)
print(f"\nType: {type(submissions)}")
print(f"Keys: {list(submissions.keys()) if isinstance(submissions, dict) else 'N/A'}")

if isinstance(submissions, dict):
    if 'filings' in submissions:
        print(f"\nFilings type: {type(submissions['filings'])}")
        print(f"Filings keys: {list(submissions['filings'].keys())}")
        if 'recent' in submissions['filings']:
            recent = submissions['filings']['recent']
            print(f"Recent type: {type(recent)}")
            if isinstance(recent, list):
                print(f"Recent entries: {len(recent)}")
                if recent:
                    print(f"First entry: {recent[0]}")
            elif isinstance(recent, dict):
                print(f"Recent keys: {list(recent.keys())}")
