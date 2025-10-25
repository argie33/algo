#!/usr/bin/env python3
"""
Simple HTTP server serving mock economic data on port 3002
"""
import json
import http.server
import socketserver
from datetime import datetime, timedelta
import random
from urllib.parse import urlparse

PORT = 3003

def generate_indicator(name, category, value, unit, change, trend, signal, strength, importance):
    """Generate a single indicator with 30-day history"""
    history = []
    for i in range(30):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        history.append({
            'date': date,
            'value': value + random.uniform(-5, 5) if isinstance(value, (int, float)) else value
        })

    return {
        'name': name,
        'category': category,
        'value': f"{value}{unit}" if isinstance(value, str) else str(value) + unit,
        'rawValue': value,
        'unit': unit,
        'change': change,
        'trend': trend,
        'signal': signal,
        'description': f"{name} economic indicator",
        'strength': strength,
        'importance': importance,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'history': list(reversed(history))
    }

def get_economic_data():
    """Generate all 25 economic indicators"""
    indicators = [
        # LEI - 11 indicators
        generate_indicator('Unemployment Rate', 'LEI', 3.8, '%', -0.15, 'down', 'Positive', 96, 'high'),
        generate_indicator('Inflation (CPI)', 'LEI', 306.7, '', 0.32, 'up', 'Neutral', 45, 'high'),
        generate_indicator('Fed Funds Rate', 'LEI', 5.33, '%', 0.0, 'stable', 'Neutral', 45, 'high'),
        generate_indicator('GDP Growth', 'LEI', 5234.5, 'B', 2.15, 'up', 'Positive', 78, 'high'),
        generate_indicator('Payroll Employment', 'LEI', 156.3, 'M', 0.45, 'up', 'Positive', 85, 'high'),
        generate_indicator('Housing Starts', 'LEI', 1382, 'K', -1.23, 'down', 'Neutral', 72, 'medium'),
        generate_indicator('Initial Jobless Claims', 'LEI', 220, 'K', 2.27, 'up', 'Positive', 85, 'medium'),
        generate_indicator('Business Loans', 'LEI', 2100000, 'B', 1.85, 'up', 'Positive', 68, 'medium'),
        generate_indicator('S&P 500 Index', 'LEI', 5789, '', 8.45, 'up', 'Positive', 95, 'high'),
        generate_indicator('Market Volatility (VIX)', 'LEI', 13.2, '', -5.13, 'down', 'Positive', 92, 'high'),
        generate_indicator('Yield Curve (2Y-10Y Spread)', 'LEI', 0.85, '%', 5.88, 'up', 'Positive', 72, 'high'),

        # LAGGING - 7 indicators
        generate_indicator('Average Duration of Unemployment', 'LAGGING', 22.5, ' weeks', -1.76, 'down', 'Positive', 92, 'high'),
        generate_indicator('Prime Lending Rate', 'LAGGING', 8.50, '%', 0.0, 'stable', 'Neutral', 50, 'medium'),
        generate_indicator('Money Market Instruments Rate', 'LAGGING', 5.35, '%', -0.45, 'down', 'Positive', 70, 'medium'),
        generate_indicator('Inventory-Sales Ratio', 'LAGGING', 1.31, '', 0.76, 'up', 'Neutral', 55, 'medium'),
        generate_indicator('Total Nonfarm Payroll (Lagging)', 'LAGGING', 156.5, 'M', 0.32, 'up', 'Positive', 88, 'high'),
        generate_indicator('Imports of Goods and Services', 'LAGGING', 418.2, 'B', 2.45, 'up', 'Neutral', 60, 'medium'),
        generate_indicator('Labor Share of Income', 'LAGGING', 56.8, '%', -0.32, 'down', 'Positive', 62, 'medium'),

        # COINCIDENT - 3 indicators
        generate_indicator('Consumer Sentiment (University of Michigan)', 'COINCIDENT', 82.5, '', 3.14, 'up', 'Positive', 88, 'high'),
        generate_indicator('Retail Sales', 'COINCIDENT', 734.5, 'B', 1.23, 'up', 'Positive', 85, 'high'),
        generate_indicator('Employment-to-Population Ratio', 'COINCIDENT', 62.8, '%', 0.15, 'up', 'Positive', 91, 'high'),

        # SECONDARY - 4 indicators
        generate_indicator('Consumer Sentiment', 'SECONDARY', 82.5, '', 3.14, 'up', 'Positive', 88, 'high'),
        generate_indicator('Payroll Employment', 'SECONDARY', 156.3, 'M', 0.45, 'up', 'Positive', 85, 'high'),
        generate_indicator('Industrial Production', 'SECONDARY', 107.4, '', 1.42, 'up', 'Positive', 82, 'medium'),
        generate_indicator('Federal Funds Rate', 'SECONDARY', 5.33, '%', 0.0, 'stable', 'Neutral', 45, 'high'),
    ]

    return {
        'success': True,
        'data': {
            'gdpGrowth': 5234.5,
            'unemployment': 3.8,
            'inflation': 306.7,
            'employment': {
                'payroll_change': 156300,
                'unemployment_rate': 3.8
            },
            'yieldCurve': {
                'spread2y10y': 0.85,
                'spread3m10y': 1.20,
                'isInverted': False,
                'interpretation': 'Normal yield curve indicates healthy economic conditions',
                'historicalAccuracy': 65,
                'averageLeadTime': 0
            },
            'indicators': indicators,
            'creditSpreads': {
                'highYield': {'oas': 385, 'signal': 'Neutral', 'historicalContext': 'Elevated but manageable'},
                'investmentGrade': {'oas': 105, 'signal': 'Positive', 'historicalContext': 'Tight spreads indicate confidence'},
                'financialConditionsIndex': {'value': -0.45, 'level': 'Accommodative'}
            },
            'upcomingEvents': []
        }
    }

class MockHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        # Set CORS headers
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        if path == '/api/market/leading-indicators':
            data = get_economic_data()
            self.wfile.write(json.dumps(data).encode())
        elif path == '/health':
            self.wfile.write(json.dumps({'status': 'ok', 'message': 'Mock API server running'}).encode())
        else:
            self.wfile.write(json.dumps({'error': 'Not found'}).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

if __name__ == '__main__':
    with socketserver.TCPServer(('', PORT), MockHandler) as httpd:
        print(f'✓ Mock API Server running on http://localhost:{PORT}')
        print(f'✓ Endpoint: http://localhost:{PORT}/api/market/leading-indicators')
        print(f'✓ Health: http://localhost:{PORT}/health')
        httpd.serve_forever()
