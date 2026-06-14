#!/usr/bin/env python3
"""Local API proxy server that forwards requests to the real AWS Lambda function."""

import json
import logging
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(__file__))

try:
    from lambda.api.lambda_wrapper import invoke_api
    USE_REAL_LAMBDA = True
except ImportError:
    USE_REAL_LAMBDA = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class LambdaProxyHandler(BaseHTTPRequestHandler):
    """HTTP handler that forwards requests to the real Lambda function."""

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_string = parsed_url.query

        # Set CORS headers for localhost development
        self.send_response(200)
        origin = self.headers.get('Origin')
        if origin and origin.startswith('http://localhost'):
            self.send_header('Access-Control-Allow-Origin', origin)
        else:
            self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        # Forward to real Lambda
        if USE_REAL_LAMBDA:
            try:
                # Parse query parameters
                query_params = parse_qs(query_string) if query_string else None
                # Flatten query_params (parse_qs returns lists)
                if query_params:
                    query_params = {k: v[0] if isinstance(v, list) else v for k, v in query_params.items()}

                # Invoke the real Lambda function
                result = invoke_api(path, method='GET', query_params=query_params)
                response = result.get('body', {})
                logger.info(f'GET {path} -> {result.get("statusCode", "?")}')
            except Exception as e:
                logger.error(f'Error invoking Lambda: {e}')
                response = {"success": False, "error": str(e)}
        else:
            logger.error('Lambda wrapper unavailable - boto3 not installed')
            response = {"success": False, "error": "Lambda wrapper not available - ensure boto3 is installed"}

        self.wfile.write(json.dumps(response).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        origin = self.headers.get('Origin')
        if origin and origin.startswith('http://localhost'):
            self.send_header('Access-Control-Allow-Origin', origin)
        else:
            self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass

if __name__ == '__main__':
    server_address = ('127.0.0.1', 3001)
    server = HTTPServer(server_address, LambdaProxyHandler)
    logger.info('API Proxy Server running on http://localhost:3001')
    logger.info('Forwarding requests to AWS Lambda function (algo-api-dev)')
    logger.info('Press Ctrl+C to stop')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info('Server stopped')
        server.server_close()
