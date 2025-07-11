#!/usr/bin/env python3
"""
Alpaca WebSocket Data Connector Lambda Function
High-frequency trading ready real-time market data connector
Connects to Alpaca's WebSocket API and distributes data to clients
"""

import json
import logging
import asyncio
import websockets
import boto3
import time
from decimal import Decimal
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import os
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AWS clients
dynamodb = boto3.resource('dynamodb')
apigateway = boto3.client('apigatewaymanagementapi')
secrets_client = boto3.client('secretsmanager')

# Environment variables
CONNECTIONS_TABLE = os.environ.get('CONNECTIONS_TABLE_NAME')
SUBSCRIPTIONS_TABLE = os.environ.get('SUBSCRIPTIONS_TABLE_NAME')
MARKET_DATA_TABLE = os.environ.get('MARKET_DATA_TABLE_NAME')
ALPACA_CREDENTIALS_SECRET = os.environ.get('ALPACA_CREDENTIALS_SECRET')
WEBSOCKET_ENDPOINT = os.environ.get('WEBSOCKET_ENDPOINT')

class DataType(Enum):
    QUOTES = "quotes"
    TRADES = "trades"
    BARS = "bars"
    NEWS = "news"
    CRYPTO = "crypto"

class MessageType(Enum):
    SUBSCRIPTION = "subscription"
    TRADE = "t"
    QUOTE = "q"
    BAR = "b"
    NEWS = "n"
    CRYPTO_TRADE = "xt"
    CRYPTO_QUOTE = "xq"
    CRYPTO_BAR = "xb"
    ERROR = "error"
    CONNECTION_ACK = "connection_ack"

@dataclass
class AlpacaCredentials:
    api_key: str
    api_secret: str
    data_feed: str
    base_url: str
    data_url: str

class AlpacaDataConnector:
    def __init__(self):
        self.websocket = None
        self.credentials = None
        self.subscriptions = {}
        self.connections = {}
        self.is_connected = False
        self.last_heartbeat = time.time()
        
        # DynamoDB tables
        self.connections_table = dynamodb.Table(CONNECTIONS_TABLE)
        self.subscriptions_table = dynamodb.Table(SUBSCRIPTIONS_TABLE)
        self.market_data_table = dynamodb.Table(MARKET_DATA_TABLE)
        
        # API Gateway management
        self.apig_client = boto3.client('apigatewaymanagementapi',
                                      endpoint_url=WEBSOCKET_ENDPOINT)
    
    async def initialize(self):
        """Initialize the connector with Alpaca credentials"""
        try:
            # Get Alpaca credentials from Secrets Manager
            self.credentials = await self._get_alpaca_credentials()
            logger.info(f"Initialized with Alpaca data feed: {self.credentials.data_feed}")
            
            # Load existing subscriptions from DynamoDB
            await self._load_subscriptions()
            
            # Connect to Alpaca WebSocket
            await self._connect_to_alpaca()
            
        except Exception as e:
            logger.error(f"Failed to initialize Alpaca connector: {e}")
            raise
    
    async def _get_alpaca_credentials(self) -> AlpacaCredentials:
        """Get Alpaca credentials from AWS Secrets Manager"""
        try:
            response = secrets_client.get_secret_value(SecretId=ALPACA_CREDENTIALS_SECRET)
            secret = json.loads(response['SecretString'])
            
            return AlpacaCredentials(
                api_key=secret['api_key'],
                api_secret=secret['api_secret'],
                data_feed=secret['data_feed'],
                base_url=secret['base_url'],
                data_url=secret['data_url']
            )
        except Exception as e:
            logger.error(f"Failed to get Alpaca credentials: {e}")
            raise
    
    async def _load_subscriptions(self):
        """Load existing subscriptions from DynamoDB"""
        try:
            response = self.subscriptions_table.scan()
            for item in response['Items']:
                sub_id = item['subscription_id']
                self.subscriptions[sub_id] = {
                    'symbols': item['symbols'],
                    'data_type': item['data_type'],
                    'frequency': item.get('frequency'),
                    'connection_id': item['connection_id'],
                    'created_at': item['created_at']
                }
            logger.info(f"Loaded {len(self.subscriptions)} existing subscriptions")
        except Exception as e:
            logger.error(f"Failed to load subscriptions: {e}")
    
    async def _connect_to_alpaca(self):
        """Connect to Alpaca WebSocket API"""
        try:
            # Alpaca WebSocket URLs
            ws_urls = {
                'iex': 'wss://stream.data.alpaca.markets/v2/iex',
                'sip': 'wss://stream.data.alpaca.markets/v2/sip',
                'otc': 'wss://stream.data.alpaca.markets/v1beta1/crypto'
            }
            
            ws_url = ws_urls.get(self.credentials.data_feed, ws_urls['iex'])
            
            self.websocket = await websockets.connect(ws_url)
            logger.info(f"Connected to Alpaca WebSocket: {ws_url}")
            
            # Authenticate
            auth_message = {
                "action": "auth",
                "key": self.credentials.api_key,
                "secret": self.credentials.api_secret
            }
            await self.websocket.send(json.dumps(auth_message))
            
            # Wait for authentication response
            auth_response = await self.websocket.recv()
            auth_data = json.loads(auth_response)
            
            if auth_data[0].get('T') == 'success':
                self.is_connected = True
                logger.info("Successfully authenticated with Alpaca")
                
                # Re-subscribe to existing subscriptions
                await self._resubscribe_existing()
                
                # Start message handling
                asyncio.create_task(self._handle_alpaca_messages())
                
            else:
                raise Exception(f"Alpaca authentication failed: {auth_data}")
                
        except Exception as e:
            logger.error(f"Failed to connect to Alpaca: {e}")
            raise
    
    async def _resubscribe_existing(self):
        """Re-subscribe to existing subscriptions after reconnection"""
        if not self.subscriptions:
            return
        
        # Group subscriptions by data type
        subscription_groups = {}
        for sub_id, sub_info in self.subscriptions.items():
            data_type = sub_info['data_type']
            if data_type not in subscription_groups:
                subscription_groups[data_type] = []
            subscription_groups[data_type].extend(sub_info['symbols'])
        
        # Send subscription messages to Alpaca
        for data_type, symbols in subscription_groups.items():
            await self._send_alpaca_subscription(data_type, symbols)
    
    async def _send_alpaca_subscription(self, data_type: str, symbols: List[str]):
        """Send subscription message to Alpaca"""
        try:
            # Map our data types to Alpaca subscription types
            alpaca_types = {
                'quotes': 'quotes',
                'trades': 'trades',
                'bars': 'bars',
                'news': 'news',
                'crypto': 'trades'  # Crypto uses trade stream
            }
            
            alpaca_type = alpaca_types.get(data_type, 'trades')
            
            subscription_message = {
                "action": "subscribe",
                alpaca_type: symbols
            }
            
            await self.websocket.send(json.dumps(subscription_message))
            logger.info(f"Subscribed to {data_type} for symbols: {symbols}")
            
        except Exception as e:
            logger.error(f"Failed to send Alpaca subscription: {e}")
    
    async def _handle_alpaca_messages(self):
        """Handle incoming messages from Alpaca WebSocket"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    
                    # Handle different message types
                    if isinstance(data, list):
                        for item in data:
                            await self._process_alpaca_message(item)
                    else:
                        await self._process_alpaca_message(data)
                        
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON message from Alpaca: {message}")
                except Exception as e:
                    logger.error(f"Error processing Alpaca message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Alpaca WebSocket connection closed")
            self.is_connected = False
            # Implement reconnection logic here
            
        except Exception as e:
            logger.error(f"Error in Alpaca message handler: {e}")
            self.is_connected = False
    
    async def _process_alpaca_message(self, message: Dict[str, Any]):
        """Process individual Alpaca message"""
        try:
            msg_type = message.get('T')
            
            if msg_type == 't':  # Trade
                await self._handle_trade_message(message)
            elif msg_type == 'q':  # Quote
                await self._handle_quote_message(message)
            elif msg_type == 'b':  # Bar
                await self._handle_bar_message(message)
            elif msg_type == 'n':  # News
                await self._handle_news_message(message)
            elif msg_type in ['xt', 'xq', 'xb']:  # Crypto
                await self._handle_crypto_message(message)
            elif msg_type == 'subscription':
                await self._handle_subscription_message(message)
            elif msg_type == 'error':
                await self._handle_error_message(message)
            else:
                logger.debug(f"Unknown message type: {msg_type}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def _handle_trade_message(self, message: Dict[str, Any]):
        """Handle trade message from Alpaca"""
        try:
            symbol = message.get('S')
            trade_data = {
                'symbol': symbol,
                'price': float(message.get('p', 0)),
                'size': int(message.get('s', 0)),
                'timestamp': message.get('t'),
                'conditions': message.get('c', []),
                'exchange': message.get('x', '')
            }
            
            # Store in DynamoDB
            await self._store_market_data(symbol, 'trades', trade_data)
            
            # Send to subscribed clients
            await self._broadcast_to_subscribers(symbol, 'trades', trade_data)
            
        except Exception as e:
            logger.error(f"Error handling trade message: {e}")
    
    async def _handle_quote_message(self, message: Dict[str, Any]):
        """Handle quote message from Alpaca"""
        try:
            symbol = message.get('S')
            quote_data = {
                'symbol': symbol,
                'bid': float(message.get('bp', 0)),
                'ask': float(message.get('ap', 0)),
                'bid_size': int(message.get('bs', 0)),
                'ask_size': int(message.get('as', 0)),
                'timestamp': message.get('t'),
                'bid_exchange': message.get('bx', ''),
                'ask_exchange': message.get('ax', '')
            }
            
            # Store in DynamoDB
            await self._store_market_data(symbol, 'quotes', quote_data)
            
            # Send to subscribed clients
            await self._broadcast_to_subscribers(symbol, 'quotes', quote_data)
            
        except Exception as e:
            logger.error(f"Error handling quote message: {e}")
    
    async def _handle_bar_message(self, message: Dict[str, Any]):
        """Handle bar message from Alpaca"""
        try:
            symbol = message.get('S')
            bar_data = {
                'symbol': symbol,
                'open': float(message.get('o', 0)),
                'high': float(message.get('h', 0)),
                'low': float(message.get('l', 0)),
                'close': float(message.get('c', 0)),
                'volume': int(message.get('v', 0)),
                'timestamp': message.get('t'),
                'trade_count': message.get('n', 0),
                'vwap': float(message.get('vw', 0))
            }
            
            # Store in DynamoDB
            await self._store_market_data(symbol, 'bars', bar_data)
            
            # Send to subscribed clients
            await self._broadcast_to_subscribers(symbol, 'bars', bar_data)
            
        except Exception as e:
            logger.error(f"Error handling bar message: {e}")
    
    async def _handle_news_message(self, message: Dict[str, Any]):
        """Handle news message from Alpaca"""
        try:
            symbols = message.get('symbols', [])
            news_data = {
                'id': message.get('id'),
                'headline': message.get('headline', ''),
                'summary': message.get('summary', ''),
                'author': message.get('author', ''),
                'created_at': message.get('created_at'),
                'updated_at': message.get('updated_at'),
                'url': message.get('url', ''),
                'symbols': symbols
            }
            
            # Store in DynamoDB and broadcast to subscribers for each symbol
            for symbol in symbols:
                await self._store_market_data(symbol, 'news', news_data)
                await self._broadcast_to_subscribers(symbol, 'news', news_data)
            
        except Exception as e:
            logger.error(f"Error handling news message: {e}")
    
    async def _handle_crypto_message(self, message: Dict[str, Any]):
        """Handle crypto message from Alpaca"""
        try:
            symbol = message.get('S')
            msg_type = message.get('T')
            
            if msg_type == 'xt':  # Crypto trade
                crypto_data = {
                    'symbol': symbol,
                    'price': float(message.get('p', 0)),
                    'size': float(message.get('s', 0)),
                    'timestamp': message.get('t')
                }
                data_type = 'crypto'
            elif msg_type == 'xq':  # Crypto quote
                crypto_data = {
                    'symbol': symbol,
                    'bid': float(message.get('bp', 0)),
                    'ask': float(message.get('ap', 0)),
                    'bid_size': float(message.get('bs', 0)),
                    'ask_size': float(message.get('as', 0)),
                    'timestamp': message.get('t')
                }
                data_type = 'crypto'
            else:
                return
            
            # Store in DynamoDB
            await self._store_market_data(symbol, data_type, crypto_data)
            
            # Send to subscribed clients
            await self._broadcast_to_subscribers(symbol, data_type, crypto_data)
            
        except Exception as e:
            logger.error(f"Error handling crypto message: {e}")
    
    async def _store_market_data(self, symbol: str, data_type: str, data: Dict[str, Any]):
        """Store market data in DynamoDB"""
        try:
            # Convert floats to Decimal for DynamoDB
            def convert_floats(obj):
                if isinstance(obj, float):
                    return Decimal(str(obj))
                elif isinstance(obj, dict):
                    return {k: convert_floats(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_floats(item) for item in obj]
                return obj
            
            converted_data = convert_floats(data)
            
            item = {
                'symbol_type': f"{symbol}#{data_type}",
                'timestamp': int(time.time() * 1000),
                'data': converted_data,
                'ttl': int(time.time()) + 86400  # 24 hour TTL
            }
            
            self.market_data_table.put_item(Item=item)
            
        except Exception as e:
            logger.error(f"Error storing market data: {e}")
    
    async def _broadcast_to_subscribers(self, symbol: str, data_type: str, data: Dict[str, Any]):
        """Broadcast data to all subscribed WebSocket clients"""
        try:
            # Find subscribers for this symbol and data type
            subscribers = []
            for sub_id, sub_info in self.subscriptions.items():
                if (symbol in sub_info['symbols'] and 
                    sub_info['data_type'] == data_type):
                    subscribers.append(sub_info['connection_id'])
            
            if not subscribers:
                return
            
            # Prepare message for clients
            message = {
                'action': 'market_data',
                'symbol': symbol,
                'dataType': data_type,
                'data': data,
                'timestamp': int(time.time() * 1000)
            }
            
            # Send to each subscriber
            for connection_id in subscribers:
                try:
                    await self._send_to_connection(connection_id, message)
                except Exception as e:
                    logger.warning(f"Failed to send to connection {connection_id}: {e}")
                    # Remove stale connection
                    await self._remove_stale_connection(connection_id)
                    
        except Exception as e:
            logger.error(f"Error broadcasting to subscribers: {e}")
    
    async def _send_to_connection(self, connection_id: str, message: Dict[str, Any]):
        """Send message to specific WebSocket connection"""
        try:
            self.apig_client.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(message)
            )
        except Exception as e:
            logger.error(f"Error sending to connection {connection_id}: {e}")
            raise
    
    async def _remove_stale_connection(self, connection_id: str):
        """Remove stale connection from database"""
        try:
            # Remove from connections table
            self.connections_table.delete_item(
                Key={'connection_id': connection_id}
            )
            
            # Remove associated subscriptions
            response = self.subscriptions_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr('connection_id').eq(connection_id)
            )
            
            for item in response['Items']:
                self.subscriptions_table.delete_item(
                    Key={'subscription_id': item['subscription_id']}
                )
                # Remove from local cache
                if item['subscription_id'] in self.subscriptions:
                    del self.subscriptions[item['subscription_id']]
                    
        except Exception as e:
            logger.error(f"Error removing stale connection: {e}")
    
    async def handle_client_message(self, connection_id: str, message: Dict[str, Any]):
        """Handle message from WebSocket client"""
        try:
            action = message.get('action')
            
            if action == 'subscribe':
                await self._handle_subscribe_request(connection_id, message)
            elif action == 'unsubscribe':
                await self._handle_unsubscribe_request(connection_id, message)
            elif action == 'list_subscriptions':
                await self._handle_list_subscriptions(connection_id)
            elif action == 'get_available_feeds':
                await self._handle_get_available_feeds(connection_id)
            elif action == 'ping':
                await self._handle_ping(connection_id, message)
            else:
                logger.warning(f"Unknown action: {action}")
                
        except Exception as e:
            logger.error(f"Error handling client message: {e}")
    
    async def _handle_subscribe_request(self, connection_id: str, message: Dict[str, Any]):
        """Handle subscription request from client"""
        try:
            symbols = message.get('symbols', [])
            data_type = message.get('dataType', 'quotes')
            frequency = message.get('frequency', '1Min')
            
            # Generate subscription ID
            subscription_id = f"{connection_id}_{data_type}_{int(time.time())}"
            
            # Store subscription in DynamoDB
            self.subscriptions_table.put_item(
                Item={
                    'subscription_id': subscription_id,
                    'connection_id': connection_id,
                    'symbols': symbols,
                    'data_type': data_type,
                    'frequency': frequency,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
            )
            
            # Add to local cache
            self.subscriptions[subscription_id] = {
                'symbols': symbols,
                'data_type': data_type,
                'frequency': frequency,
                'connection_id': connection_id,
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
            # Subscribe to Alpaca if connected
            if self.is_connected:
                await self._send_alpaca_subscription(data_type, symbols)
            
            # Send confirmation to client
            response = {
                'action': 'subscribed',
                'subscriptionId': subscription_id,
                'dataType': data_type,
                'symbols': symbols,
                'frequency': frequency
            }
            
            await self._send_to_connection(connection_id, response)
            
        except Exception as e:
            logger.error(f"Error handling subscribe request: {e}")
    
    async def _handle_unsubscribe_request(self, connection_id: str, message: Dict[str, Any]):
        """Handle unsubscribe request from client"""
        try:
            subscription_id = message.get('subscriptionId')
            
            if subscription_id:
                # Remove specific subscription
                self.subscriptions_table.delete_item(
                    Key={'subscription_id': subscription_id}
                )
                
                if subscription_id in self.subscriptions:
                    del self.subscriptions[subscription_id]
            else:
                # Remove all subscriptions for this connection
                response = self.subscriptions_table.scan(
                    FilterExpression=boto3.dynamodb.conditions.Attr('connection_id').eq(connection_id)
                )
                
                for item in response['Items']:
                    self.subscriptions_table.delete_item(
                        Key={'subscription_id': item['subscription_id']}
                    )
                    if item['subscription_id'] in self.subscriptions:
                        del self.subscriptions[item['subscription_id']]
            
            # Send confirmation
            response = {
                'action': 'unsubscribed',
                'subscriptionId': subscription_id
            }
            
            await self._send_to_connection(connection_id, response)
            
        except Exception as e:
            logger.error(f"Error handling unsubscribe request: {e}")
    
    async def _handle_list_subscriptions(self, connection_id: str):
        """Handle list subscriptions request"""
        try:
            subscriptions = []
            for sub_id, sub_info in self.subscriptions.items():
                if sub_info['connection_id'] == connection_id:
                    subscriptions.append({
                        'subscriptionId': sub_id,
                        'symbols': sub_info['symbols'],
                        'dataType': sub_info['data_type'],
                        'frequency': sub_info.get('frequency'),
                        'createdAt': sub_info['created_at']
                    })
            
            response = {
                'action': 'subscriptions_list',
                'subscriptions': subscriptions
            }
            
            await self._send_to_connection(connection_id, response)
            
        except Exception as e:
            logger.error(f"Error listing subscriptions: {e}")
    
    async def _handle_get_available_feeds(self, connection_id: str):
        """Handle get available feeds request"""
        try:
            feeds = {
                'quotes': {
                    'description': 'Real-time bid/ask quotes',
                    'symbols': 'All US equities and ETFs',
                    'frequency': 'Real-time'
                },
                'trades': {
                    'description': 'Real-time trade executions',
                    'symbols': 'All US equities and ETFs',
                    'frequency': 'Real-time'
                },
                'bars': {
                    'description': 'OHLCV bars',
                    'symbols': 'All US equities and ETFs',
                    'frequency': ['1Min', '5Min', '15Min', '1Hour', '1Day']
                },
                'news': {
                    'description': 'Real-time news updates',
                    'symbols': 'Major US equities',
                    'frequency': 'Real-time'
                },
                'crypto': {
                    'description': 'Cryptocurrency data',
                    'symbols': 'Major crypto pairs (BTCUSD, ETHUSD, etc.)',
                    'frequency': 'Real-time'
                }
            }
            
            response = {
                'action': 'available_feeds',
                'feeds': feeds
            }
            
            await self._send_to_connection(connection_id, response)
            
        except Exception as e:
            logger.error(f"Error getting available feeds: {e}")
    
    async def _handle_ping(self, connection_id: str, message: Dict[str, Any]):
        """Handle ping request"""
        try:
            response = {
                'action': 'pong',
                'timestamp': message.get('timestamp', int(time.time() * 1000))
            }
            
            await self._send_to_connection(connection_id, response)
            
        except Exception as e:
            logger.error(f"Error handling ping: {e}")

# Global connector instance
connector = None

async def lambda_handler(event, context):
    """Main Lambda handler"""
    global connector
    
    try:
        # Initialize connector if not already done
        if connector is None:
            connector = AlpacaDataConnector()
            await connector.initialize()
        
        # Handle different event types
        event_type = event.get('requestContext', {}).get('eventType')
        
        if event_type == 'CONNECT':
            return await handle_connect(event, context)
        elif event_type == 'DISCONNECT':
            return await handle_disconnect(event, context)
        elif event_type == 'MESSAGE':
            return await handle_message(event, context)
        else:
            logger.warning(f"Unknown event type: {event_type}")
            return {'statusCode': 400, 'body': 'Unknown event type'}
            
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}")
        return {'statusCode': 500, 'body': 'Internal server error'}

async def handle_connect(event, context):
    """Handle WebSocket connect"""
    try:
        connection_id = event['requestContext']['connectionId']
        
        # Store connection in DynamoDB
        connector.connections_table.put_item(
            Item={
                'connection_id': connection_id,
                'connected_at': datetime.now(timezone.utc).isoformat(),
                'ttl': int(time.time()) + 86400  # 24 hour TTL
            }
        )
        
        logger.info(f"Connection established: {connection_id}")
        return {'statusCode': 200, 'body': 'Connected'}
        
    except Exception as e:
        logger.error(f"Error handling connect: {e}")
        return {'statusCode': 500, 'body': 'Connection failed'}

async def handle_disconnect(event, context):
    """Handle WebSocket disconnect"""
    try:
        connection_id = event['requestContext']['connectionId']
        
        # Remove connection and subscriptions
        await connector._remove_stale_connection(connection_id)
        
        logger.info(f"Connection disconnected: {connection_id}")
        return {'statusCode': 200, 'body': 'Disconnected'}
        
    except Exception as e:
        logger.error(f"Error handling disconnect: {e}")
        return {'statusCode': 500, 'body': 'Disconnect failed'}

async def handle_message(event, context):
    """Handle WebSocket message"""
    try:
        connection_id = event['requestContext']['connectionId']
        message = json.loads(event['body'])
        
        # Handle client message
        await connector.handle_client_message(connection_id, message)
        
        return {'statusCode': 200, 'body': 'Message processed'}
        
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        return {'statusCode': 500, 'body': 'Message processing failed'}

# For testing purposes
if __name__ == "__main__":
    import asyncio
    
    # Test the connector
    async def test_connector():
        connector = AlpacaDataConnector()
        await connector.initialize()
        
        # Keep running
        while True:
            await asyncio.sleep(1)
    
    asyncio.run(test_connector())