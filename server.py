#!/usr/bin/env python3
"""Local development server wrapping the Lambda handler.

This Flask server provides a local development endpoint that wraps the Lambda
handler, allowing the frontend to be tested locally with real API responses.
Environment variables (DB_HOST, DB_PORT, etc.) can be set for local testing.
"""

import os
import sys
import json
from flask import Flask, request
from flask_cors import CORS

# Set local database environment variables (can be overridden by actual env vars)
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '5432')
os.environ.setdefault('DB_NAME', 'stocks')
os.environ.setdefault('DB_USER', 'stocks')
os.environ.setdefault('DB_PASSWORD', 'password')

# Add lambda/api to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambda', 'api'))

# Import the Lambda handler
from lambda_function import lambda_handler

app = Flask(__name__)
CORS(app)

@app.before_request
def log_request():
    """Log incoming requests."""
    print(f'{request.method} {request.path}', flush=True)

@app.route('/api/<path:route>', methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'])
def handle_api(route):
    """Route all /api/* requests to the Lambda handler."""
    # Build the path
    path = f'/api/{route}'

    # Build query string
    query_string = request.query_string.decode('utf-8') if request.query_string else ''

    # Build the Lambda event (API Gateway v2 format)
    event = {
        'rawPath': path,
        'rawQueryString': query_string,
        'requestContext': {
            'http': {
                'method': request.method
            }
        },
        'headers': dict(request.headers)
    }

    # Add body if present
    if request.data:
        try:
            event['body'] = request.data.decode('utf-8')
        except:
            event['body'] = str(request.data)

    # Call the Lambda handler
    try:
        response = lambda_handler(event, None)

        status_code = response.get('statusCode', 500)
        headers = response.get('headers', {})
        body = response.get('body', '{}')

        # Convert body to response
        if isinstance(body, str):
            try:
                body_data = json.loads(body)
            except:
                body_data = {'data': body}
        else:
            body_data = body

        return body_data, status_code, headers

    except Exception as e:
        print(f'Error: {e}', flush=True)
        import traceback
        traceback.print_exc()
        return {'error': 'internal_server_error', 'details': str(e)}, 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return {'status': 'healthy'}, 200

if __name__ == '__main__':
    print('Starting local API server on http://localhost:3001', flush=True)
    print('Configure frontend to use http://localhost:3001 for API calls', flush=True)
    app.run(host='localhost', port=3001, debug=False, use_reloader=False)
