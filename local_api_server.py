#!/usr/bin/env python3
"""Local API dev server for testing Lambda functions."""
import sys
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import logging

# Add lambda/api to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambda', 'api'))

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the Lambda handler
from lambda_function import lambda_handler


class LocalAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler that wraps the Lambda function."""

    def do_GET(self):
        self._handle_request('GET')

    def do_POST(self):
        self._handle_request('POST')

    def do_PATCH(self):
        self._handle_request('PATCH')

    def do_DELETE(self):
        self._handle_request('DELETE')

    def do_OPTIONS(self):
        self._handle_request('OPTIONS')

    def _handle_request(self, method):
        """Handle HTTP request by converting to Lambda event and calling handler."""
        try:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            query_string = parsed_url.query

            # Read body if present
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else None

            # Build API Gateway v2 event
            event = {
                'rawPath': path,
                'requestContext': {
                    'http': {
                        'method': method
                    }
                },
                'headers': dict(self.headers),
                'rawQueryString': query_string or '',
                'body': body,
            }

            logger.info(f'{method} {path}')

            # Call the Lambda handler
            response = lambda_handler(event, None)

            # Extract response components
            status_code = response.get('statusCode', 200)
            headers = response.get('headers', {'Content-Type': 'application/json'})
            response_body = response.get('body', '{}')

            # Send HTTP response
            self.send_response(status_code)
            for header_name, header_value in headers.items():
                self.send_header(header_name, header_value)
            self.end_headers()

            # Send body
            if isinstance(response_body, str):
                self.wfile.write(response_body.encode('utf-8'))
            else:
                self.wfile.write(json.dumps(response_body).encode('utf-8'))

        except Exception as e:
            logger.error(f'Error handling request: {e}', exc_info=True)
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'internal_server_error'}).encode('utf-8'))

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


if __name__ == '__main__':
    port = int(os.getenv('API_PORT', 3001))
    server_address = ('localhost', port)
    httpd = HTTPServer(server_address, LocalAPIHandler)
    logger.info(f'Starting local API server on http://localhost:{port}')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info('Shutting down...')
        httpd.shutdown()
