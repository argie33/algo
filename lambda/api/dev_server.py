#!/usr/bin/env python3
"""Local development server for Lambda API.

Runs the Lambda function locally on port 3001 for frontend development.
Usage: python dev_server.py
"""

import sys
import os
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import psycopg2
import psycopg2.extras

# DEVELOPMENT MODE: Enable dev token authentication
# Allows frontend to authenticate with Bearer dev-admin tokens without Cognito
os.environ['DEV_BYPASS_AUTH'] = 'true'
os.environ['ENVIRONMENT'] = 'development'

# Configure database connection for local development
os.environ['DB_HOST'] = os.getenv('DB_HOST', 'localhost')
os.environ['DB_PORT'] = os.getenv('DB_PORT', '5432')
os.environ['DB_NAME'] = os.getenv('DB_NAME', 'stocks')
os.environ['DB_USER'] = os.getenv('DB_USER', 'stocks')
os.environ['DB_PASSWORD'] = os.getenv('DB_PASSWORD', 'stocks')

# Add lambda/api and parent directories to path so we can import all modules
# NOTE: For dev_server, we prioritize root_dir so that utils.timezone_utils resolves correctly
# (In production Lambda, api_router.py handles the ordering differently)
api_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.dirname(api_dir)
root_dir = os.path.dirname(lambda_dir)
# Add root_dir first so imports like "from utils.timezone_utils" find /root/utils
sys.path.insert(0, root_dir)
sys.path.insert(1, lambda_dir)
sys.path.insert(2, api_dir)

print(f"[DEV_SERVER_INIT] DEV_BYPASS_AUTH={os.environ.get('DEV_BYPASS_AUTH')}", flush=True)

import lambda_function

import tempfile
log_file = os.path.join(os.environ.get('TEMP', '/tmp'), 'dev_server.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, mode='w')
    ]
)
logger = logging.getLogger(__name__)

# Also write a marker to show the script started
try:
    with open(log_file, 'a') as f:
        f.write("[DEV_SERVER_INIT] Script started\n")
        f.flush()
except (IOError, OSError):
    pass

class APIHandler(BaseHTTPRequestHandler):
    """HTTP request handler that routes to Lambda function."""

    def do_GET(self):
        msg = f"[HTTP] GET {self.path}"
        print(msg, flush=True)
        logger.info(f'[HTTP_GET] {self.path}')
        try:
            with open(log_file, 'a') as f:
                f.write(f"{msg}\n")
                f.flush()
        except (IOError, OSError):
            pass
        self._handle_request('GET')

    def do_POST(self):
        print(f"[HTTP] POST {self.path}", flush=True)
        logger.info(f'[HTTP_POST] {self.path}')
        self._handle_request('POST')

    def do_PUT(self):
        print(f"[HTTP] PUT {self.path}", flush=True)
        logger.info(f'[HTTP_PUT] {self.path}')
        self._handle_request('PUT')

    def do_DELETE(self):
        print(f"[HTTP] DELETE {self.path}", flush=True)
        logger.info(f'[HTTP_DELETE] {self.path}')
        self._handle_request('DELETE')

    def do_PATCH(self):
        print(f"[HTTP] PATCH {self.path}", flush=True)
        logger.info(f'[HTTP_PATCH] {self.path}')
        self._handle_request('PATCH')

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        print(f"[HTTP] OPTIONS {self.path}", flush=True)
        logger.info(f'[HTTP_OPTIONS] {self.path}')
        self.send_response(200)
        self._set_cors_headers()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _set_cors_headers(self):
        """Set CORS headers - accept any localhost origin in dev."""
        origin = self.headers.get('Origin', '')
        # In development, accept any localhost origin (5173, 5176, 5177, etc.)
        if origin and (origin.startswith('http://localhost:') or origin.startswith('http://127.0.0.1:')):
            self.send_header('Access-Control-Allow-Origin', origin)
        elif not origin:
            self.send_header('Access-Control-Allow-Origin', 'http://localhost:5173')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, PATCH, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With')
        self.send_header('Access-Control-Max-Age', '3600')

    def _handle_request(self, method):
        """Route request to Lambda handler."""
        try:
            # Parse URL
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            query_string = parsed_url.query

            # Very early logging
            print(f"[DEV_SERVER] Handling {method} {path}", flush=True)

            # Get body
            content_length = int(self.headers.get('Content-Length', 0))
            body_raw = self.rfile.read(content_length) if content_length > 0 else b''

            try:
                body = json.loads(body_raw.decode('utf-8')) if body_raw else None
            except (json.JSONDecodeError, UnicodeDecodeError):
                body = None

            # Parse query params
            params = parse_qs(query_string) if query_string else {}

            # Get Authorization header
            auth_header = self.headers.get('Authorization', '')

            # Simulate Lambda event (API Gateway v2 HTTP API format)
            event = {
                'httpMethod': method,
                'rawPath': path,
                'path': path,
                'queryStringParameters': {k: v[0] if v else '' for k, v in params.items()} if params else None,
                'rawQueryString': query_string,
                'headers': dict(self.headers),
                'body': json.dumps(body) if body else None,
                'requestContext': {
                    'http': {
                        'method': method,
                        'path': path,
                    },
                    'identity': {
                        'sourceIp': self.client_address[0] if self.client_address else '127.0.0.1',
                    },
                },
            }

            # Add Authorization to headers if present
            if auth_header:
                event['headers']['Authorization'] = auth_header

            # Call Lambda handler with timing info
            logger.info(f'[REQ_START] {method} {path}')
            import time
            start = time.time()
            response = lambda_function.lambda_handler(event, None)
            elapsed = time.time() - start
            logger.info(f'[REQ_END] {method} {path} in {elapsed:.2f}s')

            # Parse response
            status_code = response.get('statusCode', 200)
            response_body = response.get('body', '{}')
            response_headers = response.get('headers', {})

            # Encode response body
            if isinstance(response_body, str):
                response_body_bytes = response_body.encode('utf-8')
            else:
                response_body_bytes = response_body

            # Send response
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_body_bytes)))

            # CORS headers come from lambda_function; don't double-send them
            cors_keys = {'access-control-allow-origin', 'access-control-allow-credentials',
                         'access-control-allow-methods', 'access-control-allow-headers'}
            has_cors = any(k.lower() in cors_keys for k in response_headers)
            if not has_cors:
                self._set_cors_headers()

            # Add response headers (skip Content-Length if already in response_headers)
            for k, v in response_headers.items():
                if k.lower() != 'content-length':
                    self.send_header(k, v)

            self.end_headers()
            self.wfile.write(response_body_bytes)

        except Exception as e:
            logger.error(f'Error handling {method} {path}: {e}', exc_info=True)
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self._set_cors_headers()
            self.end_headers()
            error_response = json.dumps({'statusCode': 500, 'message': 'Internal server error'})
            self.wfile.write(error_response.encode('utf-8'))

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass

def run_dev_server(port=3001):
    """Run the development server."""
    server_address = ('', port)
    httpd = HTTPServer(server_address, APIHandler)
    logger.info(f'Starting API dev server on http://localhost:{port}')
    logger.info('Press Ctrl+C to stop')

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info('Shutting down...')
        httpd.shutdown()

if __name__ == '__main__':
    port = int(os.getenv('API_PORT', 3001))
    run_dev_server(port)
