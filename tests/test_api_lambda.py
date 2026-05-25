#!/usr/bin/env python3
"""Test API Lambda to check for 500 errors."""

import json
import boto3
import sys
import os

def has_aws_credentials():
    """Check if AWS credentials are available."""
    try:
        sts = boto3.client('sts', region_name='us-east-1')
        sts.get_caller_identity()
        return True
    except Exception:
        return False

def test_api_lambda():
    """Invoke API Lambda with a simple health check request."""
    try:
        lambda_client = boto3.client('lambda', region_name='us-east-1')

        # API Gateway v2 (HTTP API) event format
        test_event = {
            "version": "2.0",
            "routeKey": "GET /api/health",
            "rawPath": "/api/health",
            "headers": {
                "origin": "http://localhost:3000"
            },
            "requestContext": {
                "http": {
                    "method": "GET",
                    "path": "/api/health"
                },
                "identity": {
                    "sourceIp": "127.0.0.1"
                }
            }
        }

        print("Testing API Lambda (algo-api-dev)...")
        print(f"Event: {json.dumps(test_event, indent=2)}\n")

        response = lambda_client.invoke(
            FunctionName='algo-api-dev',
            InvocationType='RequestResponse',
            LogType='Tail',
            Payload=json.dumps(test_event)
        )

        print(f"Lambda Invocation Status Code: {response['StatusCode']}")
        print(f"Execution Log:\n{response.get('LogResult', 'No logs')}\n")

        assert 'Payload' in response, "No payload in response"

        payload = json.loads(response['Payload'].read())
        print(f"Lambda Response:")
        print(json.dumps(payload, indent=2))

        status = payload.get('statusCode', 0)
        assert status != 500, f"Lambda returned 500 error: {payload.get('body', {})}"
        assert status in (200, 201, 202, 204), f"Lambda returned unexpected status {status}"

        print("\n✅ API Lambda test PASSED")
        return True
    except Exception as e:
        print(f"\n❌ API Lambda test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_api_lambda()
    sys.exit(0 if success else 1)
