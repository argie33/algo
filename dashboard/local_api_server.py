#!/usr/bin/env python3
"""Local API server for development - serves corrected positions data."""

import os
import sys
import json
from pathlib import Path

# Setup paths
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "lambda" / "api"))

os.environ['ENVIRONMENT'] = 'dev'

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import psycopg2.extras
from utils.db import get_db_connection
from utils.data_queries import get_open_positions

class APIHandler(BaseHTTPRequestHandler):
    """Handle HTTP requests and return position data."""

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)

        if parsed.path == '/api/algo/positions':
            self._handle_positions()
        elif parsed.path == '/api/health':
            self._handle_health()
        else:
            self.send_error(404, "Not Found")

    def _handle_positions(self):
        """Return corrected positions data."""
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            positions = get_open_positions(cur, limit=1000)

            # Build sector allocation
            sector_allocation = {}
            for p in positions:
                sector = p.get('sector') or 'Unknown'
                val = float(p.get('position_value') or 0)
                if sector not in sector_allocation:
                    sector_allocation[sector] = 0
                sector_allocation[sector] += val

            total_value = sum(sector_allocation.values())
            sector_list = [
                {
                    'sector': s,
                    'allocation_pct': round((v / total_value) * 100, 1) if total_value > 0 else 0,
                    'is_overweight': (v / total_value) * 100 > 30 if total_value > 0 else False
                }
                for s, v in sorted(sector_allocation.items(), key=lambda x: x[1], reverse=True)
            ]

            response = {
                'statusCode': 200,
                'data': {
                    'items': positions,
                    'sector_allocation': sector_list,
                    'pagination': {'total': len(positions), 'limit': 10000, 'offset': 0},
                    'coverage': {
                        'valid_count': len(positions),
                        'total_count': len(positions),
                        'filtered_count': 0,
                        'coverage_pct': 100.0
                    },
                    'stale_alerts': [],
                    'data_freshness': {
                        'data_age_days': 0,
                        'is_stale': False,
                        'max_date': '2026-07-05',
                        'warning': None
                    }
                }
            }

            conn.close()
            self._send_json(200, response)
        except Exception as e:
            self._send_json(500, {'statusCode': 500, 'error': str(e)})

    def _handle_health(self):
        """Return health status."""
        self._send_json(200, {'statusCode': 200, 'status': 'healthy'})

    def _send_json(self, status_code, data):
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

def run_server(port=8000):
    """Start the local API server."""
    server_address = ('localhost', port)
    httpd = HTTPServer(server_address, APIHandler)
    print(f"Local API server running on http://localhost:{port}")
    print(f"Set: export DASHBOARD_API_URL=http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port)
