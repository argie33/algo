#!/usr/bin/env python3
"""Test the /api/scores endpoint directly."""

import json
import requests

# Test the endpoint
url = "http://localhost:3001/api/scores?limit=5&offset=0"
print(f"Calling {url}")

try:
    response = requests.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    data = response.json()

    print(f"Response keys: {data.keys()}")
    print(f"Items count: {len(data.get('items', []))}")

    if data.get("items"):
        first = data["items"][0]
        print(f"\nFirst item:")
        print(f"  symbol: {first.get('symbol')}")
        print(f"  composite_score: {first.get('composite_score')}")
        print(f"  company_name: {first.get('company_name')}")
        print(f"  Has quality_inputs: {'quality_inputs' in first}")
        if 'quality_inputs' in first and first['quality_inputs']:
            print(f"  quality_inputs keys: {list(first['quality_inputs'].keys())[:5]}")
    else:
        print("\nNo items returned")

        # Check if there's an error message
        if 'error' in data:
            print(f"Error: {data['error']}")
        if 'message' in data:
            print(f"Message: {data['message']}")

except requests.exceptions.ConnectionError:
    print("ERROR: Cannot connect to dev server at localhost:3001")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
