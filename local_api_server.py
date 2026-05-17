#!/usr/bin/env python3
"""
Local API server for development.
Wraps the Lambda handler and serves it on localhost:3001
"""

import os
import sys
import json
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from pathlib import Path

# Add lambda directory to path so we can import the handler
sys.path.insert(0, str(Path(__file__).parent / 'lambda' / 'api'))

# Import the Lambda handler
from lambda_function import APIHandler

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Set up environment variables for local development
if not os.getenv('DB_HOST'):
    os.environ['DB_HOST'] = 'localhost'
    os.environ['DB_PORT'] = '5432'
    os.environ['DB_USER'] = 'postgres'
    os.environ['DB_PASSWORD'] = os.getenv('DB_PASSWORD', '')  # Read from .env.local
    os.environ['DB_NAME'] = 'stocks'

logger.info(f"Database configuration: {os.environ.get('DB_HOST')}:{os.environ.get('DB_PORT')}/{os.environ.get('DB_NAME')}")


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    handler = APIHandler()
    try:
        handler.connect()
        result = handler.route('/api/health')
        handler.disconnect()
        return result
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({'error': 'Health check failed', 'message': str(e)}), 500


@app.route('/api/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def handle_api(path):
    """Handle all API requests"""
    path = f'/api/{path}'
    method = request.method

    # Extract query parameters
    query_params = request.args.to_dict(flat=False)

    # Extract body if present
    body = {}
    if request.is_json:
        body = request.get_json() or {}
    elif request.data:
        try:
            body = json.loads(request.data.decode('utf-8'))
        except:
            pass

    logger.info(f"{method} {path}")

    # Create handler and process request
    handler = APIHandler()
    try:
        handler.connect()
        result = handler.route(path, method, query_params, body)
        handler.disconnect()

        # Parse the Lambda response format
        if isinstance(result, dict):
            status_code = result.get('statusCode', 200)
            headers = result.get('headers', {})
            body_str = result.get('body', '{}')

            # Parse body if it's a string
            if isinstance(body_str, str):
                try:
                    body_obj = json.loads(body_str)
                except:
                    body_obj = {'raw': body_str}
            else:
                body_obj = body_str

            response = jsonify(body_obj)
            response.status_code = status_code
            for key, value in headers.items():
                response.headers[key] = value
            return response
        else:
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error handling request: {e}", exc_info=True)
        handler.disconnect()
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Not found', 'message': 'Endpoint does not exist'}), 404


@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors"""
    logger.error(f"Server error: {error}")
    return jsonify({'error': 'Internal server error', 'message': str(error)}), 500


if __name__ == '__main__':
    port = 3001
    logger.info(f"Starting local API server on http://localhost:{port}")
    logger.info("Press Ctrl+C to stop the server")
    app.run(host='127.0.0.1', port=port, debug=True, use_reloader=False)
