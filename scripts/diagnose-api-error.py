#!/usr/bin/env python3
"""Test API error details."""

import subprocess
import json
import os
import sys
import requests

os.environ['AWS_PROFILE'] = 'algo-developer'

# Get config
api_url = subprocess.check_output(
    ['terraform', 'output', '-raw', 'api_url'],
    cwd='terraform',
    stderr=subprocess.DEVNULL
).decode().strip()
pool_id = subprocess.check_output(
    ['terraform', 'output', '-raw', 'cognito_user_pool_id'],
    cwd='terraform',
    stderr=subprocess.DEVNULL
).decode().strip()
client_id = subprocess.check_output(
    ['terraform', 'output', '-raw', 'cognito_user_pool_client_id'],
    cwd='terraform',
    stderr=subprocess.DEVNULL
).decode().strip()

# Authenticate
cognito = __import__('boto3').client('cognito-idp', region_name='us-east-1')
auth = cognito.initiate_auth(
    ClientId=client_id,
    AuthFlow='USER_PASSWORD_AUTH',
    AuthParameters={'USERNAME': 'edgebrookecapital@gmail.com', 'PASSWORD': 'TestPassword123!'}
)
token = auth['AuthenticationResult']['AccessToken']

# Test both endpoints
print("Testing API endpoints with Cognito token...\n")

# Test health (public)
print("[1] Public /api/health endpoint:")
response = requests.get(f'{api_url}/api/health', timeout=10)
print(f"    Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"    Status: {data.get('data', {}).get('status', 'unknown')}")

# Test protected endpoint
print("\n[2] Protected /api/algo/markets endpoint (with Cognito token):")
headers = {'Authorization': f'Bearer {token}'}
response = requests.get(f'{api_url}/api/algo/markets', headers=headers, timeout=10)
print(f"    Status: {response.status_code}")
if response.status_code >= 400:
    print(f"    Response: {response.text[:500]}")
else:
    data = response.json()
    print(f"    Data received: {str(data)[:200]}...")

print("\nAnalysis:")
if response.status_code == 503:
    print("  [503 Service Unavailable] indicates Lambda or database issue:")
    print("  - Lambda function may be failing on cold start")
    print("  - RDS database may not be accessible from Lambda")
    print("  - Check: AWS CloudWatch logs for Lambda errors")
elif response.status_code == 401 or response.status_code == 403:
    print("  [401/403 Unauthorized] Cognito token issue:")
    print("  - Token may be invalid or expired")
    print("  - Check: Lambda validating token correctly")
elif response.status_code == 200:
    print("  [200 OK] API working correctly!")
    print("  - Cognito authentication successful")
    print("  - Lambda processing requests")
    print("  - Data available for dashboard display")
