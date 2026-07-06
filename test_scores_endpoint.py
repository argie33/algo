#!/usr/bin/env python3
"""Test scores endpoint to diagnose the issue."""

import json
from dashboard.api_data_layer import api_call, _unwrap_api_response
from dashboard.response_validators import validate_response

print("=" * 80)
print("TEST 1: Raw API call")
print("=" * 80)

result = api_call("/api/algo/scores", params={"limit": 3})
print("\nAPI Response from api_call():")
print(f"Type: {type(result)}")
print(f"Keys: {list(result.keys())}")
print(f"statusCode: {result.get('statusCode')}")
print(f"Has 'data' field: {'data' in result}")
print(f"Has 'top' field: {'top' in result}")
print(f"Has 'items' field: {'items' in result}")
print(f"\nFirst 200 chars of JSON:")
print(json.dumps(result, indent=2, default=str)[:200])

print("\n" + "=" * 80)
print("TEST 2: Check if validation removes statusCode")
print("=" * 80)

try:
    validated = validate_response("/api/algo/scores", result)
    print("\nValidated Response from validate_response():")
    print(f"Type: {type(validated)}")
    print(f"Keys: {list(validated.keys())}")
    print(f"Has 'statusCode': {'statusCode' in validated}")
    print(f"Has 'top' field: {'top' in validated}")
    print(json.dumps({k: type(v).__name__ for k, v in validated.items()}, indent=2))
except Exception as e:
    print(f"\nValidation error: {e}")

print("\n" + "=" * 80)
print("TEST 3: Check fetcher behavior")
print("=" * 80)

from dashboard.fetchers_signals import fetch_scores

fetcher_result = fetch_scores(None)
print("\nFetcher Result from fetch_scores():")
print(f"Type: {type(fetcher_result)}")
print(f"Keys: {list(fetcher_result.keys())}")
print(f"Has 'top' field: {'top' in fetcher_result}")
if 'top' in fetcher_result and fetcher_result['top']:
    print(f"Number of scores: {len(fetcher_result['top'])}")
    if fetcher_result['top']:
        print(f"First score keys: {list(fetcher_result['top'][0].keys())}")
        print(f"First score has 'growth_score': {'growth_score' in fetcher_result['top'][0]}")
        if 'growth_score' in fetcher_result['top'][0]:
            print(f"First score growth_score value: {fetcher_result['top'][0]['growth_score']}")
