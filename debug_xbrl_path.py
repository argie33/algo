#!/usr/bin/env python3
"""Debug finding XBRL XML file path from SEC EDGAR."""

import requests

from utils.external.sec_edgar_client import SecEdgarClient
from utils.infrastructure.url_validator import validate_url

client = SecEdgarClient()
cik = client.symbol_to_cik("AAPL")

submissions = client.get_submissions(cik)
filings = submissions.get('filings', {}).get('recent', {})

forms = filings.get('form', [])
accessions = filings.get('accessionNumber', [])
primary_docs = filings.get('primaryDocument', [])

# Get latest 10-K
for i, form in enumerate(forms):
    if form == '10-K':
        accession = accessions[i]
        primary_doc = primary_docs[i] if i < len(primary_docs) else None

        print(f"Latest 10-K: {accession}")
        print(f"Primary document: {primary_doc}\n")

        # Build filing directory URL
        path_accession = accession.replace('-', '')
        cik_padded = str(cik).zfill(10)
        base_url = f"https://www.sec.gov/Archives/edgar/{cik_padded}/{path_accession}"

        print(f"Filing directory: {base_url}\n")

        # Try different XBRL XML naming patterns
        patterns = [
            primary_doc.replace('.htm', '.xml') if primary_doc else None,
            f"aapl-{primary_doc.split('-')[1]}.xml" if primary_doc else None,
            f"c{cik}-{accession.split('-')[1]}.xml",
            f"{accession.replace('-', '')}.xml",
        ]

        for pattern in patterns:
            if not pattern:
                continue
            url = f"{base_url}/{pattern}"
            is_valid, _ = validate_url(url, allowed_domains=["sec.gov"])
            if not is_valid:
                print(f"[SKIP] {pattern} - SSRF blocked")
                continue

            try:
                resp = requests.head(url, timeout=5)
                print(f"[{resp.status_code}] {pattern}")
                if resp.status_code == 200:
                    print(f"      ^^^ FOUND: {url}\n")
                    # Try to fetch it
                    resp = requests.get(url, timeout=10)
                    xml_sample = resp.text[:500]
                    print(f"      Content preview:\n{xml_sample[:200]}\n")
            except Exception as e:
                print(f"[ERR] {pattern} - {type(e).__name__}")

        break
