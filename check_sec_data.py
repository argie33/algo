#!/usr/bin/env python3
"""Check if SEC data exists in the database for a sample stock."""

import json
import urllib.request
import sys

# Get score for BAR from API first
try:
    url = "http://127.0.0.1:3001/api/scores/stockscores?symbol=BAR&limit=1"
    response = urllib.request.urlopen(url, timeout=10)
    data = json.loads(response.read().decode())
    score = data.get('data', {}).get('items', [{}])[0]

    print(f"Stock: {score.get('symbol')}")
    print(f"Composite Score: {score.get('composite_score')}")
    print(f"Data Completeness: {score.get('data_completeness')}%")
    print(f"Quality Score: {score.get('quality_score')}")
    print(f"Quality Score Unavailable: {score.get('_financial_data_unavailable')}")
    print()

    # Check which metrics are missing for quality_inputs
    qi = score.get('quality_inputs', {})
    print("Quality Inputs (showing only ones with unavailable_reason):")
    for key, val in qi.items():
        if key.endswith('_unavailable_reason') and val:
            field_name = key.replace('_unavailable_reason', '')
            field_val = qi.get(field_name)
            print(f"  {field_name:30} = {field_val} ({val})")

    print()
    print("This shows which SEC data fields are marked as unavailable.")
    print("If 'missing_sec_data' appears, it means the loader didn't find/load the data.")
    print()
    print("To fix: Check why the data loaders aren't fetching SEC data for this stock.")

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
