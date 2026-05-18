#!/usr/bin/env python3
"""Simple Mock API Server using built-in http.server"""

import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

class APIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse URL
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # CORS headers
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()

        # Default response data
        response = {"status": "ok"}

        # Route handling
        if path == '/api/health':
            response = {"status": "healthy", "timestamp": "2026-05-18"}
        elif path == '/api/algo/markets':
            response = {"status": "healthy", "mcClellan": 45, "vixLevel": 18}
        elif path == '/api/algo/notifications':
            response = {"count": 0, "notifications": []}
        elif path == '/api/algo/sector-breadth':
            response = {"sectors": [{"name": "Technology", "strength": 75}]}
        elif path == '/api/algo/sector-rotation':
            response = {"data": [{"date": "2026-05-18", "sector": "Technology", "score": 85}]}
        elif path == '/api/algo/sector-stage2':
            response = {"stage2_candidates": [{"symbol": "XLK", "stage": 2}]}
        elif path == '/api/algo/swing-scores':
            response = {"data": [{"symbol": "AAPL", "score": 82}]}
        elif path == '/api/algo/swing-scores-history':
            response = {"history": [{"date": "2026-05-18", "avgScore": 72}]}
        elif path == '/api/economic/calendar':
            response = {"events": [{"date": "2026-05-22", "event": "Economic Event"}]}
        elif path == '/api/economic/leading-indicators':
            response = {"indicators": [{"name": "Consumer Confidence", "value": 104}]}
        elif path == '/api/economic/yield-curve-full':
            response = {"data": [{"maturity": "1M", "rate": 5.2}]}
        elif '/api/financials/' in path:
            response = {"symbol": "TEST", "data": [{"date": "2026-Q1", "value": 1000000000}]}
        elif path == '/api/industries':
            response = {"industries": [{"name": "Software", "performance": 8.5}], "total": 148}
        elif path == '/api/market/distribution-days':
            response = {"distribution_days": 3, "trend": "uptrend"}
        elif path == '/api/market/fear-greed':
            response = {"current": 62, "trend": "up"}
        elif path == '/api/market/naaim':
            response = {"current": 75, "trend": "bullish"}
        elif path == '/api/market/seasonality':
            response = {"month": "May", "historical_return": 2.1}
        elif path == '/api/market/sentiment':
            response = {"bullish": 68, "bearish": 22, "trend": "bullish"}
        elif path == '/api/market/technicals':
            response = {"macd": {"value": 0.5}, "rsi": 62, "momentum": "positive"}
        elif path == '/api/market/top-movers':
            response = {"gainers": [{"symbol": "AAPL", "gain": 2.5}], "losers": []}
        elif '/api/prices/history/' in path:
            symbol = path.split('/api/prices/history/')[-1]
            response = {"symbol": symbol, "data": [{"date": "2026-05-18", "close": 191}]}
        elif path == '/api/research/backtests':
            response = {"backtests": [{"id": "1", "strategy": "Swing Trading", "return": 15.2}], "total": 1}
        elif path == '/api/scores/stockscores':
            response = {"data": [{"symbol": "AAPL", "composite_score": 82}]}
        elif path == '/api/sectors':
            response = {"sectors": [{"name": "Technology", "performance": 8.2}], "total": 11}
        elif path == '/api/sentiment/data':
            response = {"data": [{"symbol": "AAPL", "bullish": 72, "bearish": 18}]}
        elif path == '/api/sentiment/summary':
            response = {"overall": "bullish", "bullish_count": 3200, "bearish_count": 1800}
        elif path == '/api/sentiment/divergence':
            response = {"divergences": [{"symbol": "AAPL", "price_trend": "up", "sentiment_trend": "down"}]}
        elif '/api/sentiment/analyst/insights/' in path:
            symbol = path.split('/api/sentiment/analyst/insights/')[-1]
            response = {"symbol": symbol, "bullish_percent": 72, "consensus": "buy"}
        elif path == '/api/signals/stocks':
            response = {"data": [{"symbol": "AAPL", "signal": "BUY"}]}
        elif '/api/stocks/' in path:
            symbol = path.split('/api/stocks/')[-1]
            response = {"symbol": symbol, "name": f"Stock {symbol}", "price": 185}
        else:
            self.send_response(404)
            response = {"error": "Not found"}

        # Send JSON response
        json_data = json.dumps(response)
        self.wfile.write(json_data.encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress verbose logging
        pass

if __name__ == '__main__':
    server = HTTPServer(('localhost', 3001), APIHandler)
    print("Starting Mock API Server on http://localhost:3001")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
