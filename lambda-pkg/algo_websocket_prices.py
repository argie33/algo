#!/usr/bin/env python3
"""
Alpaca WebSocket price stream - stream live prices to frontend clients.
Connects to Alpaca Data WebSocket API for real-time quotes.
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import os
import json
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Set, Callable

try:
    import asyncio
    from websockets.server import serve, WebSocketServerProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logger = logging.getLogger(__name__)

ALPACA_WS_URL = "wss://data.alpaca.markets/v1beta1/crypto" if os.getenv('ALPACA_WS_MODE') == 'crypto' else "wss://data.alpaca.markets/v1beta3/news"
ALPACA_API_KEY = credential_manager.get_alpaca_credentials()["key"]


class PriceStreamServer:
    """WebSocket server that streams live prices from Alpaca."""

    def __init__(self, port: int = 8765):
        self.port = port
        self.clients: Set[WebSocketServerProtocol] = set()
        self.subscribed_symbols: Dict[str, Set] = {}
        self.last_prices: Dict[str, dict] = {}

    async def register(self, websocket: WebSocketServerProtocol):
        """Register a new client."""
        self.clients.add(websocket)
        logger.info(f"Client connected. Total: {len(self.clients)}")

    async def unregister(self, websocket: WebSocketServerProtocol):
        """Unregister a client."""
        self.clients.discard(websocket)
        logger.info(f"Client disconnected. Total: {len(self.clients)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        if not self.clients:
            return

        data = json.dumps(message)
        for client in self.clients:
            try:
                await client.send(data)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")

    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """Handle incoming WebSocket messages from clients."""
        await self.register(websocket)
        try:
            async for message in websocket:
                data = json.loads(message)
                action = data.get('action')

                if action == 'subscribe':
                    symbols = data.get('symbols', [])
                    for symbol in symbols:
                        if symbol not in self.subscribed_symbols:
                            self.subscribed_symbols[symbol] = set()
                        self.subscribed_symbols[symbol].add(websocket)
                    await websocket.send(json.dumps({'type': 'subscribed', 'symbols': symbols}))

                elif action == 'unsubscribe':
                    symbols = data.get('symbols', [])
                    for symbol in symbols:
                        if symbol in self.subscribed_symbols:
                            self.subscribed_symbols[symbol].discard(websocket)

        except Exception as e:
            logger.error(f"Client error: {e}")
        finally:
            await self.unregister(websocket)

    async def start(self):
        """Start the WebSocket server."""
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets library not installed. Install with: pip install websockets")
            return

        logger.info(f"Starting price stream server on ws://localhost:{self.port}")
        async with serve(self.handle_client, "localhost", self.port):
            await asyncio.Future()  # run forever

    def send_price(self, symbol: str, price: float, timestamp: str):
        """Queue a price update to broadcast."""
        message = {
            'type': 'price_update',
            'symbol': symbol,
            'price': price,
            'timestamp': timestamp,
        }
        self.last_prices[symbol] = message

        # Broadcast to subscribed clients
        if symbol in self.subscribed_symbols:
            asyncio.create_task(self.broadcast(message))


class AlpacaPriceConnector:
    """Connect to Alpaca WebSocket and forward prices."""

    def __init__(self, price_server: PriceStreamServer):
        self.price_server = price_server
        self.ws = None

    def connect_and_stream(self):
        """Connect to Alpaca and stream prices."""
        if not WEBSOCKET_AVAILABLE:
            logger.error("websocket-client library not installed. Install with: pip install websocket-client")
            return

        logger.info("Connecting to Alpaca WebSocket...")
        try:
            import websocket

            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    if 'T' in data and 'c' in data:  # Trade: T=type, c=price
                        symbol = data.get('S')
                        price = float(data['c'])
                        timestamp = data.get('t', '')
                        self.price_server.send_price(symbol, price, timestamp)
                except Exception as e:
                    logger.warning(f"Error processing message: {e}")

            def on_error(ws, error):
                logger.error(f"WebSocket error: {error}")

            def on_close(ws, close_status_code, close_msg):
                logger.info("Alpaca WebSocket closed")

            def on_open(ws):
                logger.info("Alpaca WebSocket connected")
                auth_msg = {
                    "action": "auth",
                    "key": ALPACA_API_KEY,
                    "secret": credential_manager.get_alpaca_credentials()["secret"],
                }
                ws.send(json.dumps(auth_msg))

            self.ws = websocket.WebSocketApp(
                ALPACA_WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            self.ws.run_forever()
        except Exception as e:
            logger.error(f"Failed to connect to Alpaca: {e}")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    server = PriceStreamServer(port=8765)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
