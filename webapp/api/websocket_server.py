import asyncio
import json
import logging
import time
import random
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional
import websockets
from websockets.server import WebSocketServerProtocol
import aiohttp
import sqlite3
from dataclasses import dataclass, asdict
from threading import Lock

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class MarketData:
    symbol: str
    price: float
    bid: float
    ask: float
    volume: int
    timestamp: float
    change: float
    change_percent: float

@dataclass
class OptionsData:
    symbol: str
    strike: float
    expiry: str
    type: str  # 'CALL' or 'PUT'
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    implied_volatility: float
    delta: float
    gamma: float
    theta: float
    vega: float
    timestamp: float

class DataStore:
    """Thread-safe data storage for market data"""
    def __init__(self):
        self._lock = Lock()
        self._market_data: Dict[str, MarketData] = {}
        self._options_data: Dict[str, List[OptionsData]] = {}
        self._subscribers: Dict[str, Set[WebSocketServerProtocol]] = {}
        
    def update_market_data(self, symbol: str, data: MarketData):
        with self._lock:
            self._market_data[symbol] = data
            
    def get_market_data(self, symbol: str) -> Optional[MarketData]:
        with self._lock:
            return self._market_data.get(symbol)
            
    def update_options_data(self, symbol: str, options: List[OptionsData]):
        with self._lock:
            self._options_data[symbol] = options
            
    def get_options_data(self, symbol: str) -> List[OptionsData]:
        with self._lock:
            return self._options_data.get(symbol, [])
            
    def add_subscriber(self, channel: str, websocket: WebSocketServerProtocol):
        with self._lock:
            if channel not in self._subscribers:
                self._subscribers[channel] = set()
            self._subscribers[channel].add(websocket)
            
    def remove_subscriber(self, channel: str, websocket: WebSocketServerProtocol):
        with self._lock:
            if channel in self._subscribers:
                self._subscribers[channel].discard(websocket)
                if not self._subscribers[channel]:
                    del self._subscribers[channel]
                    
    def get_subscribers(self, channel: str) -> Set[WebSocketServerProtocol]:
        with self._lock:
            return self._subscribers.get(channel, set()).copy()

class MarketDataSimulator:
    """Generates realistic market data for testing"""
    
    def __init__(self):
        self.symbols = [
            'AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 
            'SPY', 'QQQ', 'IWM', 'GLD', 'TLT', 'VIX'
        ]
        self.base_prices = {
            'AAPL': 150.0, 'MSFT': 330.0, 'GOOGL': 2800.0, 'TSLA': 200.0,
            'NVDA': 400.0, 'AMZN': 3200.0, 'META': 280.0, 'SPY': 420.0,
            'QQQ': 380.0, 'IWM': 180.0, 'GLD': 180.0, 'TLT': 95.0, 'VIX': 18.0
        }
        self.volatilities = {
            'AAPL': 0.25, 'MSFT': 0.22, 'GOOGL': 0.28, 'TSLA': 0.45,
            'NVDA': 0.35, 'AMZN': 0.30, 'META': 0.33, 'SPY': 0.15,
            'QQQ': 0.18, 'IWM': 0.22, 'GLD': 0.12, 'TLT': 0.08, 'VIX': 0.80
        }
        
    def generate_market_data(self, symbol: str) -> MarketData:
        """Generate realistic market data with random walk"""
        base_price = self.base_prices.get(symbol, 100.0)
        volatility = self.volatilities.get(symbol, 0.25)
        
        # Random walk with mean reversion
        change_pct = random.gauss(0, volatility / 100)
        price = base_price * (1 + change_pct)
        
        # Update base price slightly for next iteration
        self.base_prices[symbol] = price * 0.99 + base_price * 0.01
        
        # Calculate bid/ask spread (0.01% to 0.05%)
        spread = price * random.uniform(0.0001, 0.0005)
        bid = price - spread / 2
        ask = price + spread / 2
        
        # Generate volume
        volume = random.randint(10000, 1000000)
        
        return MarketData(
            symbol=symbol,
            price=round(price, 2),
            bid=round(bid, 2),
            ask=round(ask, 2),
            volume=volume,
            timestamp=time.time(),
            change=round(price - base_price, 2),
            change_percent=round(change_pct * 100, 2)
        )
        
    def generate_options_data(self, symbol: str) -> List[OptionsData]:
        """Generate realistic options chain data"""
        base_price = self.base_prices.get(symbol, 100.0)
        options = []
        
        # Generate options for next few expiries
        expiries = [
            (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d'),
            (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d'),
            (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d')
        ]
        
        for expiry in expiries:
            # Generate strikes around current price
            strikes = [base_price + i * 5 for i in range(-10, 11)]
            
            for strike in strikes:
                for option_type in ['CALL', 'PUT']:
                    # Calculate realistic option metrics
                    dte = (datetime.strptime(expiry, '%Y-%m-%d') - datetime.now()).days
                    time_to_expiry = max(0.01, dte / 365.0)
                    
                    # Simplified Black-Scholes approximation
                    moneyness = base_price / strike if option_type == 'CALL' else strike / base_price
                    intrinsic = max(0, base_price - strike) if option_type == 'CALL' else max(0, strike - base_price)
                    
                    # Implied volatility with skew
                    iv_base = 0.25
                    if option_type == 'PUT':
                        iv_base += 0.05  # Put skew
                    if moneyness < 0.95:
                        iv_base += 0.1  # OTM skew
                    
                    iv = iv_base + random.uniform(-0.05, 0.05)
                    
                    # Time value approximation
                    time_value = iv * base_price * (time_to_expiry ** 0.5) * 0.4
                    option_price = intrinsic + time_value
                    
                    # Greeks approximation
                    delta = 0.5 + (moneyness - 1) * 0.5 if option_type == 'CALL' else -0.5 + (1 - moneyness) * 0.5
                    gamma = 0.1 * (1 - abs(delta)) / (base_price * iv * (time_to_expiry ** 0.5))
                    theta = -option_price * 0.1 / (365 * time_to_expiry)
                    vega = base_price * (time_to_expiry ** 0.5) * 0.01
                    
                    # Bid/ask spread
                    spread = max(0.05, option_price * 0.05)
                    bid = max(0.01, option_price - spread/2)
                    ask = option_price + spread/2
                    
                    options.append(OptionsData(
                        symbol=symbol,
                        strike=round(strike, 2),
                        expiry=expiry,
                        type=option_type,
                        bid=round(bid, 2),
                        ask=round(ask, 2),
                        last=round(option_price, 2),
                        volume=random.randint(0, 1000),
                        open_interest=random.randint(100, 10000),
                        implied_volatility=round(iv, 3),
                        delta=round(delta, 3),
                        gamma=round(gamma, 4),
                        theta=round(theta, 3),
                        vega=round(vega, 3),
                        timestamp=time.time()
                    ))
                    
        return options

class WebSocketDataFeed:
    """Main WebSocket server for real-time market data"""
    
    def __init__(self, host: str = 'localhost', port: int = 8765):
        self.host = host
        self.port = port
        self.data_store = DataStore()
        self.simulator = MarketDataSimulator()
        self.running = False
        
    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """Handle individual client connections"""
        logger.info(f"Client connected from {websocket.remote_address}")
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.process_message(websocket, data)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'message': 'Invalid JSON format'
                    }))
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'message': str(e)
                    }))
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Client disconnected")
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            # Clean up subscriptions
            for channel in list(self.data_store._subscribers.keys()):
                self.data_store.remove_subscriber(channel, websocket)
                
    async def process_message(self, websocket: WebSocketServerProtocol, data: dict):
        """Process incoming client messages"""
        message_type = data.get('type')
        
        if message_type == 'subscribe':
            channel = data.get('channel')
            symbols = data.get('symbols', [])
            
            if channel == 'market_data':
                self.data_store.add_subscriber(f"market_data", websocket)
                # Send current data immediately
                for symbol in symbols:
                    current_data = self.data_store.get_market_data(symbol)
                    if current_data:
                        await websocket.send(json.dumps({
                            'type': 'market_data',
                            'data': asdict(current_data)
                        }))
                        
            elif channel == 'options_data':
                symbol = data.get('symbol')
                if symbol:
                    self.data_store.add_subscriber(f"options_data_{symbol}", websocket)
                    # Send current options data
                    options = self.data_store.get_options_data(symbol)
                    if options:
                        await websocket.send(json.dumps({
                            'type': 'options_data',
                            'symbol': symbol,
                            'data': [asdict(opt) for opt in options]
                        }))
                        
            await websocket.send(json.dumps({
                'type': 'subscribed',
                'channel': channel,
                'symbols': symbols
            }))
            
        elif message_type == 'unsubscribe':
            channel = data.get('channel')
            if channel:
                self.data_store.remove_subscriber(channel, websocket)
                await websocket.send(json.dumps({
                    'type': 'unsubscribed',
                    'channel': channel
                }))
                
        elif message_type == 'ping':
            await websocket.send(json.dumps({
                'type': 'pong',
                'timestamp': time.time()
            }))
            
    async def broadcast_market_data(self):
        """Periodically generate and broadcast market data"""
        while self.running:
            try:
                # Generate new market data for all symbols
                for symbol in self.simulator.symbols:
                    market_data = self.simulator.generate_market_data(symbol)
                    self.data_store.update_market_data(symbol, market_data)
                    
                    # Broadcast to subscribers
                    subscribers = self.data_store.get_subscribers("market_data")
                    if subscribers:
                        message = json.dumps({
                            'type': 'market_data',
                            'data': asdict(market_data)
                        })
                        
                        # Send to all subscribers
                        disconnected = set()
                        for websocket in subscribers:
                            try:
                                await websocket.send(message)
                            except websockets.exceptions.ConnectionClosed:
                                disconnected.add(websocket)
                            except Exception as e:
                                logger.error(f"Error broadcasting to client: {e}")
                                disconnected.add(websocket)
                                
                        # Clean up disconnected clients
                        for websocket in disconnected:
                            self.data_store.remove_subscriber("market_data", websocket)
                            
                await asyncio.sleep(1)  # Update every second
                
            except Exception as e:
                logger.error(f"Error in market data broadcast: {e}")
                await asyncio.sleep(5)
                
    async def broadcast_options_data(self):
        """Periodically generate and broadcast options data"""
        while self.running:
            try:
                # Generate options data every 30 seconds
                for symbol in ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY']:
                    options_data = self.simulator.generate_options_data(symbol)
                    self.data_store.update_options_data(symbol, options_data)
                    
                    # Broadcast to subscribers
                    subscribers = self.data_store.get_subscribers(f"options_data_{symbol}")
                    if subscribers:
                        message = json.dumps({
                            'type': 'options_data',
                            'symbol': symbol,
                            'data': [asdict(opt) for opt in options_data]
                        })
                        
                        # Send to all subscribers
                        disconnected = set()
                        for websocket in subscribers:
                            try:
                                await websocket.send(message)
                            except websockets.exceptions.ConnectionClosed:
                                disconnected.add(websocket)
                            except Exception as e:
                                logger.error(f"Error broadcasting options to client: {e}")
                                disconnected.add(websocket)
                                
                        # Clean up disconnected clients
                        for websocket in disconnected:
                            self.data_store.remove_subscriber(f"options_data_{symbol}", websocket)
                            
                await asyncio.sleep(30)  # Update every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in options data broadcast: {e}")
                await asyncio.sleep(30)
                
    async def start_server(self):
        """Start the WebSocket server and background tasks"""
        self.running = True
        
        # Start background tasks
        market_task = asyncio.create_task(self.broadcast_market_data())
        options_task = asyncio.create_task(self.broadcast_options_data())
        
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")
        
        try:
            async with websockets.serve(
                self.handle_client,
                self.host,
                self.port,
                ping_interval=20,
                ping_timeout=10,
                max_size=2**20  # 1MB max message size
            ):
                logger.info("WebSocket server started successfully")
                await asyncio.gather(market_task, options_task)
                
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            self.running = False
            market_task.cancel()
            options_task.cancel()

class DataValidator:
    """Validates incoming market data for accuracy and completeness"""
    
    @staticmethod
    def validate_market_data(data: dict) -> bool:
        """Validate market data structure and values"""
        required_fields = ['symbol', 'price', 'bid', 'ask', 'volume', 'timestamp']
        
        # Check required fields
        for field in required_fields:
            if field not in data:
                return False
                
        # Validate data types and ranges
        try:
            price = float(data['price'])
            bid = float(data['bid'])
            ask = float(data['ask'])
            volume = int(data['volume'])
            
            # Basic sanity checks
            if price <= 0 or bid <= 0 or ask <= 0 or volume < 0:
                return False
                
            if bid > ask:  # Bid should not exceed ask
                return False
                
            if abs(price - (bid + ask) / 2) > (ask - bid) * 2:  # Price should be near mid
                return False
                
            return True
            
        except (ValueError, TypeError):
            return False
            
    @staticmethod
    def validate_options_data(data: dict) -> bool:
        """Validate options data structure and values"""
        required_fields = [
            'symbol', 'strike', 'expiry', 'type', 'bid', 'ask', 'last',
            'volume', 'open_interest', 'implied_volatility'
        ]
        
        # Check required fields
        for field in required_fields:
            if field not in data:
                return False
                
        try:
            # Validate option type
            if data['type'] not in ['CALL', 'PUT']:
                return False
                
            # Validate numeric fields
            strike = float(data['strike'])
            bid = float(data['bid'])
            ask = float(data['ask'])
            last = float(data['last'])
            iv = float(data['implied_volatility'])
            
            # Basic sanity checks
            if strike <= 0 or bid < 0 or ask < 0 or last < 0:
                return False
                
            if bid > ask and bid > 0 and ask > 0:
                return False
                
            if iv < 0 or iv > 5:  # IV should be reasonable
                return False
                
            return True
            
        except (ValueError, TypeError):
            return False

if __name__ == "__main__":
    # Create and start the WebSocket server
    server = WebSocketDataFeed(host='0.0.0.0', port=8765)
    
    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server failed to start: {e}")