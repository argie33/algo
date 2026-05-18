#!/usr/bin/env python3
"""Local development API server - wraps Lambda routes with local database."""

import os
import sys
import json
import logging
from pathlib import Path

# Add lambda API to path
lambda_api = Path(__file__).parent.parent / 'lambda' / 'api'
sys.path.insert(0, str(lambda_api))

from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

# Import Lambda API router
import api_router

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
_db_conn = None

def get_db_connection():
    """Get database connection from local env."""
    global _db_conn

    if _db_conn and not _db_conn.closed:
        return _db_conn

    try:
        # Use local database credentials
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = os.getenv('DB_PORT', '5432')
        db_name = os.getenv('DB_NAME', 'stocks')
        db_user = os.getenv('DB_USER', 'stocks')
        db_password = os.getenv('DB_PASSWORD', '')

        _db_conn = psycopg2.connect(
            host=db_host,
            port=int(db_port),
            database=db_name,
            user=db_user,
            password=db_password,
            cursor_factory=RealDictCursor,
            connect_timeout=10
        )
        logger.info(f'Connected to {db_host}:{db_port}/{db_name}')
        return _db_conn
    except Exception as e:
        logger.error(f'DB connection failed: {e}')
        return None

@app.route('/health', methods=['GET'])
def health():
    """Health check."""
    conn = get_db_connection()
    if conn:
        return jsonify({'status': 'healthy', 'db': 'connected'})
    return jsonify({'status': 'degraded', 'db': 'disconnected'}), 503

@app.route('/api/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def api(subpath):
    """Route all /api/* requests to Lambda API handlers."""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 503

        cur = conn.cursor()

        # Build path and method
        path = f'/api/{subpath}'
        method = request.method

        # Parse query parameters
        params = {}
        if request.args:
            for key, value in request.args.items():
                params[key] = [value] if isinstance(value, str) else value

        # Parse body for POST/PUT
        body = None
        if method in ['POST', 'PUT']:
            body = request.get_json() or {}

        # Call router
        result = api_router.route_request(cur, path, method, params, body)

        # Handle response
        status_code = result.get('statusCode', 200)
        headers = result.get('headers', {'Content-Type': 'application/json'})
        body_data = result.get('body')

        if isinstance(body_data, str):
            try:
                body_data = json.loads(body_data)
            except:
                pass

        response = app.response_class(
            response=json.dumps(body_data or result),
            status=status_code,
            headers=headers
        )
        return response

    except Exception as e:
        logger.error(f'API error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3001, debug=True)
