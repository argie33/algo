#!/usr/bin/env python3
"""Analyze scores to identify 'no data' patterns."""

import json
import sys
from collections import defaultdict
import urllib.request

try:
    # Fetch scores from API
    url = "http://127.0.0.1:3001/api/scores/stockscores?limit=1000&offset=0"
    response = urllib.request.urlopen(url, timeout=10)
    data = json.loads(response.read().decode())

    items = data.get('data', {}).get('items', [])
    print(f"Analyzing {len(items)} scores...\n")

    # Track missing reasons
    missing_reasons = defaultdict(int)
    missing_by_field = defaultdict(lambda: defaultdict(int))

    scores_with_all_data = 0
    scores_with_some_missing = 0
    most_missing_scores = []

    for item in items:
        missing_count = 0
        missing_fields = []

        # Check all fields for null values with unavailable_reason
        for key, value in item.items():
            if key.endswith('_unavailable_reason') and value:
                missing_count += 1
                field_name = key.replace('_unavailable_reason', '')
                missing_fields.append((field_name, value))
                missing_by_field[field_name][value] += 1
                missing_reasons[value] += 1

        if missing_count == 0:
            scores_with_all_data += 1
        else:
            scores_with_some_missing += 1
            most_missing_scores.append((item.get('symbol'), missing_count, missing_fields[:5]))

    # Sort by missing count
    most_missing_scores.sort(key=lambda x: x[1], reverse=True)

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Scores with all data:     {scores_with_all_data}")
    print(f"Scores with some missing: {scores_with_some_missing}")
    print(f"Percentage complete:      {100*scores_with_all_data/len(items):.1f}%\n")

    print("=" * 70)
    print("MISSING DATA REASONS (Top 10)")
    print("=" * 70)
    for reason, count in sorted(missing_reasons.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"{reason:50} {count:5} occurrences")

    print("\n" + "=" * 70)
    print("STOCKS WITH MOST MISSING DATA (Top 15)")
    print("=" * 70)
    for symbol, count, fields in most_missing_scores[:15]:
        print(f"\n{symbol:8} - {count:2} missing fields")
        for field, reason in fields:
            print(f"  • {field:35} {reason}")

    print("\n" + "=" * 70)
    print("FIELDS WITH MOST MISSING DATA (Top 20)")
    print("=" * 70)
    field_totals = {field: sum(reasons.values()) for field, reasons in missing_by_field.items()}
    for field, total in sorted(field_totals.items(), key=lambda x: x[1], reverse=True)[:20]:
        reasons = missing_by_field[field]
        top_reason = max(reasons.items(), key=lambda x: x[1])
        print(f"{field:35} {total:4} missing - mostly: {top_reason[0]}")

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
