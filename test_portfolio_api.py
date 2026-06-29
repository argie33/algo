#!/usr/bin/env python3
"""Test portfolio API endpoint directly."""
import json
import boto3
import sys

client = boto3.client("lambda", region_name="us-east-1")

payload = {
    "rawPath": "/api/algo/portfolio",
    "httpMethod": "GET",
    "headers": {}
}

response = client.invoke(
    FunctionName="algo-api-dev",
    InvocationType="RequestResponse",
    Payload=json.dumps(payload)
)

# Read the response body
payload_bytes = response["Payload"].read()
print(f"Raw Payload (first 200 chars): {payload_bytes[:200]}")

response_body = json.loads(payload_bytes)
print("Lambda Response Status Code:", response.get("StatusCode"))
print("Executed Version:", response.get("ExecutedVersion"))
print(f"\nResponse Body Type: {type(response_body)}")
print(f"Response Body Keys: {response_body.keys() if isinstance(response_body, dict) else 'N/A'}")

# Parse the response body
if isinstance(response_body, dict) and "body" in response_body:
    body_str = response_body["body"]
    outer_response = json.loads(body_str)
    data = outer_response.get("data", {})
    print("\n=== Portfolio Data ===")
    print(f"Data Age Seconds: {data.get('data_age_seconds', 'N/A')}")
    print(f"Has debug_code_version: {'debug_code_version' in data}")
    if 'debug_code_version' in data:
        print(f"Debug Code Version: {data['debug_code_version']}")
    print(f"Total Portfolio Value: {data.get('total_portfolio_value', 'N/A')}")
    print(f"Total Cash: {data.get('total_cash', 'N/A')}")
else:
    print("ERROR: Unexpected response format")
    print(f"Full response:\n{json.dumps(response_body, indent=2)}")
