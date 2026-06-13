#!/usr/bin/env python3
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, str(Path('.') / 'lambda' / 'api'))
sys.path.insert(0, str(Path('.').absolute()))

try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("lambda_function", "lambda/api/lambda_function.py")
    lambda_function = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lambda_function)

    test_event = {
        "rawPath": "/api/algo/markets",
        "requestContext": {"http": {"method": "GET"}},
        "headers": {"origin": "http://localhost:5173"}
    }

    print("Testing Lambda handler...")
    response = lambda_function.lambda_handler(test_event, None)

    status = response.get('statusCode')
    print(f"Response Status: {status}")

    if status == 200:
        print("SUCCESS: Lambda returned 200")
        body = json.loads(response.get('body', '{}'))
        if body.get('data'):
            print(f"Data keys: {list(body['data'].keys())[:10]}")
            if body['data'].get('success'):
                print("SUCCESS field: True")
            if body['data'].get('current'):
                print("Current market data: available")
            if body['data'].get('sectors'):
                print(f"Sectors data: {len(body['data']['sectors'])} sectors")
        else:
            print("No data field in response")
    else:
        body = json.loads(response.get('body', '{}'))
        print(f"Error: {body.get('errorType')}")
        print(f"Message: {body.get('message')}")

except Exception as e:
    print(f"Exception: {type(e).__name__}: {e}")
