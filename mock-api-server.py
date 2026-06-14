#!/usr/bin/env python3
"""Simple mock API server for dashboard development when database is unavailable."""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
import math

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class MockAPIHandler(BaseHTTPRequestHandler):
    """HTTP handler that returns mock data matching the API contract."""

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # Set CORS headers
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', 'http://localhost:5175')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        # Route to appropriate mock response
        if path == '/api/health' or path == '/health':
            response = {"success": True, "message": "Mock API Server"}
        elif path == '/api/algo/market-health':
            response = self._mock_market_health()
        elif path == '/api/algo/markets' or path == '/api/market/markets':
            response = {"success": True, "data": {"markets": []}}
        elif path == '/api/algo/notifications':
            response = {"success": True, "data": {"notifications": []}}
        elif path == '/api/algo/positions':
            response = self._mock_positions()
        elif path == '/api/algo/performance':
            response = self._mock_performance()
        elif path == '/api/algo/circuit-breakers':
            response = self._mock_circuit_breakers()
        elif '/sentiment' in path:
            response = {"success": True, "data": {"sentiment": {}}}
        elif '/top-movers' in path:
            response = {"success": True, "data": {"movers": []}}
        elif '/technicals' in path:
            response = {"success": True, "data": {"technicals": {}}}
        elif '/seasonality' in path:
            response = {"success": True, "data": {"seasonality": {}}}
        else:
            response = {"success": True, "data": {}}

        self.wfile.write(json.dumps(response).encode())
        logger.info(f'GET {path}')

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', 'http://localhost:5175')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass

    @staticmethod
    def _mock_market_health():
        """Return mock market health data."""
        return {
            "success": True,
            "data": {
                "lastUpdated": datetime.now().isoformat(),
                "indices": {
                    "SPY": {
                        "symbol": "SPY",
                        "name": "S&P 500",
                        "price": 567.89,
                        "change": 1.23,
                        "changePercent": 0.22
                    },
                    "QQQ": {
                        "symbol": "QQQ",
                        "name": "Nasdaq 100",
                        "price": 418.56,
                        "change": 2.45,
                        "changePercent": 0.59
                    },
                    "IWM": {
                        "symbol": "IWM",
                        "name": "Russell 2000",
                        "price": 205.43,
                        "change": 0.87,
                        "changePercent": 0.43
                    },
                    "DIA": {
                        "symbol": "DIA",
                        "name": "Dow Jones",
                        "price": 423.12,
                        "change": 1.05,
                        "changePercent": 0.25
                    }
                },
                "marketExposure": {
                    "followThroughDay": {"score": 8.0, "max": 10.0},
                    "trend30Day": {"score": 7.5, "max": 15.0},
                    "breadth50DMA": {"score": 6.0, "max": 14.0},
                    "health200DMA": {"score": 8.5, "max": 10.0},
                    "mcClellan": {"score": 7.0, "max": 9.0}
                },
                "sectors": {
                    "XLK": {"name": "Technology", "change": 2.1, "weight": 30},
                    "XLF": {"name": "Financials", "change": 0.5, "weight": 14},
                    "XLV": {"name": "Health Care", "change": 1.2, "weight": 12},
                    "XLY": {"name": "Consumer Discretionary", "change": 0.8, "weight": 11},
                    "XLC": {"name": "Communication Services", "change": 1.5, "weight": 9},
                    "XLI": {"name": "Industrials", "change": 0.3, "weight": 8},
                    "XLP": {"name": "Consumer Staples", "change": 0.1, "weight": 6},
                    "XLE": {"name": "Energy", "change": -0.5, "weight": 4},
                    "XLU": {"name": "Utilities", "change": 0.2, "weight": 3},
                    "XLRE": {"name": "Real Estate", "change": 0.4, "weight": 2},
                    "XLB": {"name": "Materials", "change": 0.6, "weight": 2}
                }
            }
        }

    @staticmethod
    def _mock_markets():
        """Return mock markets data."""
        return {
            "success": True,
            "data": {
                "markets": [
                    {"symbol": "SPY", "name": "S&P 500", "price": 567.89, "change": 1.23},
                    {"symbol": "QQQ", "name": "Nasdaq 100", "price": 418.56, "change": 2.45},
                    {"symbol": "IWM", "name": "Russell 2000", "price": 205.43, "change": 0.87}
                ]
            }
        }

    @staticmethod
    def _mock_positions():
        """Return mock positions data."""
        return {
            "success": True,
            "data": {
                "positions": [
                    {
                        "symbol": "AAPL",
                        "shares": 100,
                        "entryPrice": 150.25,
                        "currentPrice": 156.75,
                        "gain": 6.50,
                        "gainPercent": 4.32,
                        "status": "OPEN"
                    },
                    {
                        "symbol": "MSFT",
                        "shares": 50,
                        "entryPrice": 320.10,
                        "currentPrice": 335.45,
                        "gain": 15.35,
                        "gainPercent": 4.79,
                        "status": "OPEN"
                    }
                ],
                "totalGain": 21.85,
                "totalGainPercent": 4.55
            }
        }

    @staticmethod
    def _mock_performance():
        """Return mock performance metrics."""
        return {
            "success": True,
            "data": {
                "metrics": {
                    "totalTrades": 42,
                    "winRate": 0.62,
                    "profitFactor": 2.15,
                    "sharpeRatio": 1.85,
                    "maxDrawdown": 0.18,
                    "totalReturn": 0.45
                }
            }
        }

    @staticmethod
    def _mock_circuit_breakers():
        """Return mock circuit breaker status."""
        return {
            "success": True,
            "data": {
                "circuitBreakers": {
                    "marketBreadth": {"triggered": False, "value": 0.65},
                    "volatility": {"triggered": False, "value": 16.5},
                    "gapDown": {"triggered": False, "value": 0.02}
                }
            }
        }

if __name__ == '__main__':
    server_address = ('127.0.0.1', 3001)
    server = HTTPServer(server_address, MockAPIHandler)
    logger.info('Mock API server running on http://localhost:3001')
    logger.info('Press Ctrl+C to stop')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info('Server stopped')
        server.server_close()
