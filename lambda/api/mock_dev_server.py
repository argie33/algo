#!/usr/bin/env python3
"""Simple mock API server for frontend development - no DB needed."""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import random

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MockAPIHandler(BaseHTTPRequestHandler):
    """Mock API handler that returns realistic test data."""

    def do_GET(self):
        self._handle_request('GET')

    def do_POST(self):
        self._handle_request('POST')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', self._get_allowed_origin())
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def _handle_request(self, method):
        try:
            path = urlparse(self.path).path
            logger.info(f'{method} {path}')

            # Health check
            if path == '/api/health':
                self._respond(200, {'status': 'ok'})
                return

            # Mock sectors list
            if path == '/api/sectors':
                self._respond(200, {
                    'success': True,
                    'data': {
                        'items': [
                            {'id': 'XLK', 'name': 'Technology', 'price': 100 + random.randint(-5, 5)},
                            {'id': 'XLV', 'name': 'Healthcare', 'price': 95 + random.randint(-5, 5)},
                            {'id': 'XLF', 'name': 'Financials', 'price': 90 + random.randint(-5, 5)},
                        ],
                        'pagination': {'page': 1, 'total': 3, 'totalPages': 1}
                    }
                })
                return

            # Mock scores
            if path == '/api/scores/stockscores':
                self._respond(200, {
                    'success': True,
                    'data': {
                        'items': [
                            {'symbol': 'AAPL', 'score': 85},
                            {'symbol': 'MSFT', 'score': 82},
                            {'symbol': 'GOOGL', 'score': 78},
                        ],
                        'pagination': {'page': 1, 'total': 3, 'totalPages': 1}
                    }
                })
                return

            # Mock signals
            if path == '/api/signals/stocks':
                self._respond(200, {
                    'success': True,
                    'data': {
                        'items': [
                            {'symbol': 'AAPL', 'signal': 'BUY'},
                            {'symbol': 'MSFT', 'signal': 'HOLD'},
                        ],
                        'pagination': {'page': 1, 'total': 2, 'totalPages': 1}
                    }
                })
                return

            # Mock sentiment
            if path == '/api/sentiment/data':
                self._respond(200, {
                    'success': True,
                    'data': {
                        'sentiment_indices': [
                            {'name': 'Fear & Greed', 'value': 65},
                            {'name': 'NAAIM', 'value': 55},
                        ]
                    }
                })
                return

            # Mock sector rotation
            if '/api/algo/sector-rotation' in path:
                self._respond(200, {
                    'success': True,
                    'data': [
                        {'date': '2026-05-23', 'sector': 'Technology', 'score': 75},
                        {'date': '2026-05-23', 'sector': 'Healthcare', 'score': 68},
                    ]
                })
                return

            # Default 404
            self._respond(404, {'error': 'Not found'})

        except Exception as e:
            logger.error(f'Error: {e}')
            self._respond(500, {'error': str(e)})

    def _get_allowed_origin(self):
        """Get allowed origin from request or default - accept any localhost in dev."""
        origin = self.headers.get('Origin', '')
        # In development, accept any localhost origin (any port)
        if origin and (origin.startswith('http://localhost:') or origin.startswith('http://127.0.0.1:')):
            return origin
        return 'http://localhost:5173'

    def _respond(self, status_code, data):
        """Send JSON response with CORS headers."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', self._get_allowed_origin())
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def log_message(self, format, *args):
        pass  # Suppress default logging

def run_server(port=3001):
    """Run mock API server."""
    server_address = ('', port)
    httpd = HTTPServer(server_address, MockAPIHandler)
    logger.info(f'Starting mock API dev server on http://localhost:{port}')
    logger.info('Press Ctrl+C to stop')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info('Shutting down...')
        httpd.shutdown()

if __name__ == '__main__':
    run_server()
