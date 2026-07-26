#!/usr/bin/env python3
"""Check if segment revenue is available in 10-K/10-Q filing text."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.external.sec_edgar_client import SecEdgarClient

def check_filing_for_segments(symbol: str):
    """Fetch most recent 10-K and check for segment revenue tables."""
    print(f"\n{'='*100}")
    print(f"CHECKING FILING TEXT FOR SEGMENTS: {symbol}")
    print(f"{'='*100}")

    try:
        sec_client = SecEdgarClient()
        cik = sec_client.symbol_to_cik(symbol)

        # Get submissions for the company
        submissions = sec_client.get_submissions(cik)
        print(f"Submissions received")

        if not submissions or 'filings' not in submissions:
            print("No filings found")
            return

        filings = submissions['filings']

        # Find most recent 10-K
        recent_10k = None
        for accession, form, filed_date in zip(
            filings.get('accessions', [])[:20],  # Last 20
            filings.get('forms', [])[:20],
            filings.get('filingDates', [])[:20]
        ):
            if form == '10-K':
                recent_10k = accession
                print(f"Found recent 10-K: {accession} filed {filed_date}")
                break

        if not recent_10k:
            print("No 10-K found in recent filings")
            return

        # Try to fetch the filing
        try:
            filing_text = sec_client.get_filing_plaintext(cik, recent_10k)
            if not filing_text:
                print("Could not fetch filing text")
                return

            # Search for segment revenue indicators
            text_upper = filing_text.upper()
            indicators = [
                'SEGMENT REVENUE',
                'REVENUE FROM SEGMENTS',
                'SEGMENT INFORMATION - REVENUE',
                'OPERATING SEGMENTS',
                'REPORTABLE SEGMENTS',
            ]

            print(f"\nSearching filing text ({len(filing_text)} chars) for segment revenue indicators:")
            found_any = False
            for indicator in indicators:
                if indicator in text_upper:
                    # Find context around it
                    pos = text_upper.find(indicator)
                    start = max(0, pos - 200)
                    end = min(len(filing_text), pos + 400)
                    context = filing_text[start:end].replace('\n', ' ')
                    print(f"\n  ✓ Found: {indicator}")
                    print(f"    Context: ...{context}...")
                    found_any = True

            if not found_any:
                print("  ✗ No segment revenue indicators found")

        except Exception as e:
            print(f"Error fetching filing text: {type(e).__name__}: {e}")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    for symbol in ['AAPL']:  # Just AAPL for now
        check_filing_for_segments(symbol)
