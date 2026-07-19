#!/usr/bin/env python3
"""Test the positions API endpoint."""

import json
try:
    import requests
except ImportError:
    print("requests library not installed")
    exit(1)

try:
    response = requests.get("http://localhost:3001/api/algo/positions", timeout=3)
    data = response.json()

    if "items" in data and isinstance(data["items"], list):
        print(f"Positions API returned {len(data['items'])} items")
        for pos in data["items"][:5]:
            symbol = pos.get("symbol", "N/A")
            quantity = pos.get("quantity", "N/A")
            value = pos.get("position_value", "N/A")
            print(f"  {symbol}: {quantity} shares (${value})")
    elif isinstance(data, list):
        print(f"Positions API returned {len(data)} items (raw list)")
        for pos in data[:5]:
            symbol = pos.get("symbol", "N/A")
            quantity = pos.get("quantity", "N/A")
            print(f"  {symbol}: {quantity}")
    else:
        print(f"Unexpected response: {json.dumps(data, indent=2)[:500]}")
except Exception as e:
    print(f"Error testing API: {e}")
