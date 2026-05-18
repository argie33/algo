#!/usr/bin/env python3
"""Local development server with proper module reloading for API testing.

Forces fresh imports on each request to avoid Python's module caching issues
that plague development servers.
"""

import os
import sys
import json
import importlib
from flask import Flask, request
from flask_cors import CORS

# Set local database environment variables
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '5432')
os.environ.setdefault('DB_NAME', 'stocks')
os.environ.setdefault('DB_USER', 'stocks')
os.environ.setdefault('DB_PASSWORD', 'password')

# Add lambda/api to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lambda', 'api'))

app = Flask(__name__)
CORS(app)

def get_fresh_handler():
    """Get a fresh lambda_handler by reloading the module.

    This avoids Python's module caching which causes stale code to be used
    in development environments.
    """
    # Remove all lambda-related modules from cache
    modules_to_remove = [m for m in sys.modules.keys() if 'lambda' in m or 'routes' in m or 'api_router' in m or 'utils' in m]
    for m in modules_to_remove:
        del sys.modules[m]

    # Import fresh
    from lambda_function import lambda_handler
    return lambda_handler

@app.route('/api/<path:route>', methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'])
def handle_api(route):
    """Route all /api/* requests through the Lambda handler with fresh imports."""
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

    # Call the Lambda handler with fresh imports
    try:
        lambda_handler = get_fresh_handler()
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
    print('Starting local API server with fresh module reloading', flush=True)
    print('This server reloads all modules on each request to avoid caching issues', flush=True)
    print('API running on http://localhost:3001', flush=True)
    app.run(host='localhost', port=3001, debug=False, use_reloader=False, threaded=True)
