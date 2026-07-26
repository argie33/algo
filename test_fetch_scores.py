#!/usr/bin/env python3
"""Test the fetch_scores function to see if it properly transforms the API response."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from dashboard.fetchers_signals import fetch_scores

# Call the fetcher (simulates what the dashboard does)
result = fetch_scores(None)

print("Fetcher result:")
print(f"  Keys: {result.keys()}")
print(f"  Has 'top': {'top' in result}")
print(f"  Top items count: {len(result.get('top', []))}")

if result.get('top'):
    first = result['top'][0]
    print(f"\nFirst item in 'top':")
    print(f"  symbol: {first.get('symbol')}")
    print(f"  composite_score: {first.get('composite_score')}")
    print(f"  Has quality_inputs: {'quality_inputs' in first}")
else:
    print("\nNo items in 'top' - this would cause 'No Data' to display!")
    if result.get('_error'):
        print(f"Error: {result['_error']}")
    elif result.get('data_unavailable'):
        print(f"Unavailable: {result.get('reason')}")
