#!/usr/bin/env python3
"""
Local API server for development.
Wraps the Lambda handler and serves it on localhost:3001
"""

import os
import json
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

# Set up logging FIRST (before any logger calls)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# All credentials must come from environment variables (set before running)
logger.info("Starting local API server - credentials from environment variables")

# Add lambda directory to path so we can import the handler

# Import the Lambda handler
from lambda_function import APIHandler

app = Flask(__name__)
CORS(app)

# Ensure database configuration is set
if not os.getenv('DB_HOST'):
    os.environ['DB_HOST'] = 'localhost'
if not os.getenv('DB_PORT'):
    os.environ['DB_PORT'] = '5432'
if not os.getenv('DB_USER'):
    os.environ['DB_USER'] = 'postgres'
if not os.getenv('DB_NAME'):
    os.environ['DB_NAME'] = 'stocks'
if not os.getenv('DB_PASSWORD'):
    os.environ['DB_PASSWORD'] = ''

logger.info(f"Database configuration: {os.environ.get('DB_HOST')}:{os.environ.get('DB_PORT')}/{os.environ.get('DB_NAME')}")
logger.info(f"DB User: {os.environ.get('DB_USER')}")


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
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.debug("Failed to parse request body as JSON, treating as empty")
            body = {}

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
                except json.JSONDecodeError:
                    logger.debug("Response body was not valid JSON, returning as raw string")
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
    port = int(os.getenv('LOCAL_API_PORT', 3001))
    host = os.getenv('LOCAL_API_HOST', '127.0.0.1')
    logger.info(f"Starting local API server on http://{host}:{port}")
    logger.info("Press Ctrl+C to stop the server")
    app.run(host=host, port=port, debug=True, use_reloader=False)
