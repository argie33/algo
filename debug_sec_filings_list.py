#!/usr/bin/env python3
"""List recent SEC filings for a symbol."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.external.sec_edgar_client import SecEdgarClient

def list_filings(symbol: str):
    """List all recent SEC filings."""
    print(f"\n{'='*100}")
    print(f"RECENT FILINGS FOR: {symbol}")
    print(f"{'='*100}\n")

    try:
        sec_client = SecEdgarClient()
        cik = sec_client.symbol_to_cik(symbol)

        # Get submissions for the company
        submissions = sec_client.get_submissions(cik)

        if 'filings' in submissions:
            filings = submissions['filings']

            # Show first 30 filings
            accessions = filings.get('accessions', [])[:30]
            forms = filings.get('forms', [])[:30]
            dates = filings.get('filingDates', [])[:30]

            print(f"{'Filing Date':<12} {'Form':<8} {'Accession':<20}")
            print("-" * 50)

            for date, form, acc in zip(dates, forms, accessions):
                print(f"{date:<12} {form:<8} {acc:<20}")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    for symbol in ['AAPL']:
        list_filings(symbol)
