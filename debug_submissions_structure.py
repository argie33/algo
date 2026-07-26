#!/usr/bin/env python3
"""Debug the structure of SEC submissions API response."""

from utils.external.sec_edgar_client import SecEdgarClient

client = SecEdgarClient()
cik = client.symbol_to_cik('JBLU')

submissions = client.get_submissions(cik)

print("Submissions structure for JBLU:")
print("=" * 70)
print(f"Top-level keys: {list(submissions.keys())}")

if 'filings' in submissions:
    filings = submissions['filings']
    print(f"\nfilings keys: {list(filings.keys())}")

    if 'recent' in filings:
        recent = filings['recent']
        print(f"\nrecent keys: {list(recent.keys())}")
        print(f"Number of recent filings: {len(recent.get('form', []))}")

        # Show first few forms
        if 'form' in recent and 'accession' in recent:
            print("\nFirst 10 filings:")
            for i in range(min(10, len(recent['form']))):
                form = recent['form'][i]
                accession = recent['accession'][i]
                date = recent.get('filingDate', ['N/A'])[i] if i < len(recent.get('filingDate', [])) else 'N/A'
                print(f"  {i}: {form} on {date} ({accession})")

                # Find first 10-K
                if form == '10-K':
                    print(f"\n✓ Found 10-K at index {i}:")
                    print(f"  Accession: {accession}")
                    print(f"  Use this to fetch: get_filing_xml(cik, '{accession}', '10-K')")
                    break

print("\n" + "=" * 70)
