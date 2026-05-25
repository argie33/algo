#!/usr/bin/env python3
"""Test API Lambda to check for 500 errors."""

import json
import boto3
import sys

def test_api_lambda():
    """Invoke API Lambda with a simple health check request."""

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

    try:
        response = lambda_client.invoke(
            FunctionName='algo-api-dev',
            InvocationType='RequestResponse',
            LogType='Tail',
            Payload=json.dumps(test_event)
        )

        print(f"Lambda Invocation Status Code: {response['StatusCode']}")
        print(f"Execution Log:\n{response.get('LogResult', 'No logs')}\n")

        if 'Payload' in response:
            payload = json.loads(response['Payload'].read())
            print(f"Lambda Response:")
            print(json.dumps(payload, indent=2))

            status = payload.get('statusCode', 0)
            if status == 500:
                print("\n❌ ERROR: Lambda returned 500 error!")
                body = payload.get('body', {})
                if isinstance(body, str):
                    body = json.loads(body)
                print(f"Error details: {json.dumps(body, indent=2)}")
                return False
            elif status == 200:
                print(f"\n✅ SUCCESS: Lambda returned 200")
                return True
            else:
                print(f"\n⚠️ WARNING: Lambda returned {status}")
                return True
        else:
            print("No payload in response")
            return False

    except Exception as e:
        print(f"❌ ERROR invoking Lambda: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_api_lambda()
    sys.exit(0 if success else 1)
