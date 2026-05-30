#!/usr/bin/env python3
"""Test orchestrator Lambda status and readiness."""
import json
import boto3

# Create session explicitly with profile
session = boto3.Session(profile_name='algo-developer', region_name='us-east-1')
lambda_client = session.client('lambda')

print("=" * 60)
print("ORCHESTRATOR LAMBDA STATUS")
print("=" * 60)

try:
    # Get function info
    response = lambda_client.get_function(FunctionName='algo-algo-dev')
    config = response['Configuration']

    print(f"\nFunction Name: {config['FunctionName']}")
    print(f"Function ARN: {config['FunctionArn']}")
    print(f"Runtime: {config['Runtime']}")
    print(f"Last Modified: {config['LastModified']}")
    print(f"CodeSize: {config['CodeSize']:,} bytes")
    print(f"MemorySize: {config['MemorySize']} MB")
    print(f"Timeout: {config['Timeout']} seconds")
    print(f"Handler: {config['Handler']}")

    print("\n[✓] Lambda function is deployed and ready")

except Exception as e:
    print(f"[✗] ERROR: {e}")
    import traceback
    traceback.print_exc()
