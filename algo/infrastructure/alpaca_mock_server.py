"""Local HTTP mock server that mimics Alpaca REST API.

Allows testing the complete trading system locally without real Alpaca account.
The system uses REAL code paths, just against a local mock API instead of live.

Usage:
    python -m algo.infrastructure.alpaca_mock_server
    # Server starts on http://localhost:8001
    # Configure system to use APCA_API_BASE_URL=http://localhost:8001
"""

import json
import logging
from decimal import Decimal
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class AlpacaMockAccount:
    """Simulates Alpaca account state."""

    def __init__(self):
        self.account_id = str(uuid.uuid4())[:8]
        self.cash = Decimal("100000")
        self.positions = {}
        self.orders = {}
        self.trades_history = []

    def to_dict(self) -> dict[str, Any]:
        """Return account as dict (Alpaca format)."""
        portfolio_value = self.cash + sum(
            Decimal(str(p["qty"])) * Decimal(str(p["current_price"]))
            for p in self.positions.values()
        )
        return {
            "id": self.account_id,
            "account_number": self.account_id,
            "status": "ACTIVE",
            "cash": str(self.cash),
            "portfolio_value": str(portfolio_value),
            "buying_power": str(self.cash * Decimal("4")),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


class AlpacaMockHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Alpaca mock API."""

    # Shared mock account across all requests
    mock_account = AlpacaMockAccount()

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        logger.info(f"[MOCK_API] {format % args}")

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/v2/account":
            self.send_json(200, self.mock_account.to_dict())
        elif self.path.startswith("/v2/positions"):
            positions = list(self.mock_account.positions.values())
            self.send_json(200, positions)
        elif self.path.startswith("/v2/orders"):
            orders = list(self.mock_account.orders.values())
            self.send_json(200, orders)
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        """Handle POST requests (order submission)."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Invalid JSON"})
            return

        if self.path == "/v2/orders":
            self.handle_order_submission(data)
        else:
            self.send_json(404, {"error": "Not found"})

    def handle_order_submission(self, data: dict) -> None:
        """Process order submission."""
        symbol = data.get("symbol", "").upper()
        qty = int(data.get("qty", 0))
        side = data.get("side", "").lower()

        if not symbol or qty <= 0 or side not in ("buy", "sell"):
            self.send_json(400, {"error": "Invalid order parameters"})
            return

        # Simulate order execution
        current_price = Decimal("100.00")  # Fixed price for demo
        order_id = str(uuid.uuid4())[:8]

        try:
            if side == "buy":
                cost = Decimal(str(qty)) * current_price
                if cost > self.mock_account.cash:
                    self.send_json(403, {"error": "Insufficient buying power"})
                    return

                self.mock_account.cash -= cost
                if symbol in self.mock_account.positions:
                    self.mock_account.positions[symbol]["qty"] += qty
                else:
                    self.mock_account.positions[symbol] = {
                        "symbol": symbol,
                        "qty": qty,
                        "avg_fill_price": str(current_price),
                        "current_price": str(current_price),
                    }

                logger.info(f"[MOCK_API] BUY: {qty} {symbol} @ ${current_price}")

            elif side == "sell":
                if symbol not in self.mock_account.positions or \
                   self.mock_account.positions[symbol]["qty"] < qty:
                    self.send_json(403, {"error": "Insufficient shares"})
                    return

                proceeds = Decimal(str(qty)) * current_price
                self.mock_account.cash += proceeds
                self.mock_account.positions[symbol]["qty"] -= qty

                if self.mock_account.positions[symbol]["qty"] == 0:
                    del self.mock_account.positions[symbol]

                logger.info(f"[MOCK_API] SELL: {qty} {symbol} @ ${current_price}")

            # Create order response
            order = {
                "id": order_id,
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "type": data.get("type", "market"),
                "time_in_force": data.get("time_in_force", "day"),
                "filled_qty": qty,
                "filled_avg_price": str(current_price),
                "status": "filled",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "filled_at": datetime.now(timezone.utc).isoformat(),
            }

            self.mock_account.orders[order_id] = order
            self.send_json(200, order)

        except Exception as e:
            logger.error(f"[MOCK_API] Order processing error: {e}")
            self.send_json(500, {"error": str(e)})

    def send_json(self, status: int, data: dict) -> None:
        """Send JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


def start_mock_server(port: int = 8001, host: str = "localhost") -> None:
    """Start the mock Alpaca API server."""
    server = HTTPServer((host, port), AlpacaMockHandler)
    logger.info(f"[MOCK_API] Starting mock Alpaca server on http://{host}:{port}")
    logger.info(f"[MOCK_API] Configure system with: APCA_API_BASE_URL=http://{host}:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("[MOCK_API] Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    start_mock_server()
