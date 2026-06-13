#!/usr/bin/env python3
import sys
import os
from pathlib import Path

# Add Lambda paths
lambda_api_dir = str(Path('.') / 'lambda' / 'api')
root_dir = str(Path('.').absolute())

sys.path.insert(0, lambda_api_dir)
sys.path.insert(1, root_dir)

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

    print(f"Status: {response.get('statusCode')}")
    if response.get('statusCode') == 200:
        print("✅ SUCCESS!")
    else:
        body = eval(response.get('body', '{}'))
        print(f"Error: {body.get('errorType')}")
        print(f"Message: {body.get('message')}")

except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
