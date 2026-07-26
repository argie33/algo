#!/usr/bin/env python3
"""Debug primaryDocument field in submissions."""

from utils.external.sec_edgar_client import SecEdgarClient

client = SecEdgarClient()
cik = client.symbol_to_cik("AAPL")

submissions = client.get_submissions(cik)
filings = submissions.get('filings', {}).get('recent', {})

forms = filings.get('form', [])
accessions = filings.get('accessionNumber', [])
primary_docs = filings.get('primaryDocument', [])

print("First 5 10-K filings:")
count = 0
for i, form in enumerate(forms):
    if form == '10-K' and count < 5:
        print(f"\n{count}: {accessions[i]}")
        print(f"   Primary doc: {primary_docs[i] if i < len(primary_docs) else 'N/A'}")
        count += 1
