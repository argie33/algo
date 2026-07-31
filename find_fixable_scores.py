#!/usr/bin/env python3
"""Find scores that could be improved by fixing data issues."""

import json
import urllib.request
import sys
from collections import defaultdict

try:
    # Fetch all scores
    url = "http://127.0.0.1:3001/api/scores/stockscores?limit=1000&offset=0"
    response = urllib.request.urlopen(url, timeout=10)
    data = json.loads(response.read().decode())
    items = data.get('data', {}).get('items', [])

    print(f"Analyzing {len(items)} scores to find improvement opportunities...\n")

    # Find scores with high completeness but missing quality_score
    candidates = []

    for item in items:
        symbol = item.get('symbol')
        completeness = item.get('data_completeness', 0)
        quality_score = item.get('quality_score')
        quality_unavailable = item.get('_financial_data_unavailable', False)

        # Find scores where:
        # 1. Quality score is None (unavailable)
        # 2. But overall data completeness is relatively high (>=75%)
        # This suggests the underlying data might be loadable
        if quality_score is None and quality_unavailable and completeness >= 75:
            candidates.append({
                'symbol': symbol,
                'completeness': completeness,
                'composite_score': item.get('composite_score'),
                'missing_financial_reason': 'SEC financial data marked unavailable'
            })

    candidates.sort(key=lambda x: x['completeness'], reverse=True)

    print("=" * 70)
    print("CANDIDATES FOR DATA IMPROVEMENT")
    print("(High completeness but missing quality score due to SEC data issues)")
    print("=" * 70)
    print(f"\nFound {len(candidates)} stocks that could potentially be fixed\n")

    for item in candidates[:20]:
        print(f"{item['symbol']:8} completeness={item['completeness']:5.1f}%  " +
              f"composite={item['composite_score']:5.1f} " +
              f"[{item['missing_financial_reason']}]")

    if len(candidates) > 20:
        print(f"... and {len(candidates)-20} more")

    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    print(f"""
These {len(candidates)} stocks have high overall data completeness ({min(c['completeness'] for c in candidates):.0f}-100%)
but are missing SEC financial metrics (ROE, margins, debt ratios, etc.).

This suggests:
1. The stocks HAVE price/technical/positioning data
2. But SEC financial data is missing or not being loaded

ACTION ITEMS:
- Check why SEC data loaders aren't fetching data for these stocks
- Are they truly missing from SEC filings (unlikely for major stocks)?
- Is there a bug in the loader?
- Do we need to refresh/re-run the SEC data loader?
""")

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
