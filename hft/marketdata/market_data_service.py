"""
Market Data Service - Real-time price data ingestion from Alpaca
Handles websocket connections and publishes to Kafka for downstream processing
"""
import os
import json
import logging
import asyncio
from typing import Dict, List, Set
import aiohttp
from alpaca.data import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.live import CryptoDataStream, StockDataStream
from alpaca.data.models import QuoteData, TradeData
from aiokafka import AIOKafkaProducer
from prometheus_client import Counter, Gauge, start_http_server
import boto3
from pythonjsonlogger import jsonlogger
from pydantic import BaseModel

# Configure logging
logger = logging.getLogger(__name__)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

# Prometheus metrics
QUOTES_RECEIVED = Counter('market_data_quotes_total', 'Number of quotes received')
TRADES_RECEIVED = Counter('market_data_trades_total', 'Number of trades received')
KAFKA_PUBLISH_TIME = Gauge('market_data_kafka_publish_seconds', 'Time taken to publish to Kafka')
ACTIVE_SUBSCRIPTIONS = Gauge('market_data_active_subscriptions', 'Number of active symbol subscriptions')

class MarketDataConfig(BaseModel):
    """Configuration for Market Data Service"""
    symbols: List[str] = ["SPY", "TLT"]  # Default symbols to monitor
    kafka_topic_quotes: str = "market.quotes"
    kafka_topic_trades: str = "market.trades"
    kafka_bootstrap_servers: List[str]
    metrics_port: int = 8000

class MarketDataService:
    def __init__(self, config: MarketDataConfig):
        self.config = config
        self.active_symbols: Set[str] = set(config.symbols)
        self._load_credentials()
        self._setup_clients()
        
    def _load_credentials(self):
        """Load Alpaca credentials from AWS Secrets Manager"""
        secret_name = f"hft-dev/alpaca-credentials"
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name=session.region_name
        )
        
        secret = client.get_secret_value(SecretId=secret_name)
        creds = json.loads(secret['SecretString'])
        
        self.api_key = creds['api_key']
        self.secret_key = creds['secret_key']
        
    def _setup_clients(self):
        """Initialize Alpaca clients"""
        # Historical data clients (for initial data load)
        self.stock_client = StockHistoricalDataClient(self.api_key, self.secret_key)
        
        # Real-time data streams
        self.stock_stream = StockDataStream(self.api_key, self.secret_key)
        
        # Setup handlers
        self.stock_stream.quote_handlers.append(self._handle_stock_quote)
        self.stock_stream.trade_handlers.append(self._handle_stock_trade)
        
    async def _setup_kafka_producer(self):
        """Initialize Kafka producer"""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        await self.producer.start()
        
    async def _handle_stock_quote(self, quote: QuoteData):
        """Handle incoming stock quotes"""
        QUOTES_RECEIVED.inc()
        
        message = {
            "symbol": quote.symbol,
            "bid_price": float(quote.bid_price),
            "bid_size": int(quote.bid_size),
            "ask_price": float(quote.ask_price),
            "ask_size": int(quote.ask_size),
            "timestamp": quote.timestamp.isoformat()
        }
        
        async with KAFKA_PUBLISH_TIME.time():
            await self.producer.send_and_wait(
                self.config.kafka_topic_quotes,
                key=quote.symbol.encode('utf-8'),
                value=message
            )
            
    async def _handle_stock_trade(self, trade: TradeData):
        """Handle incoming stock trades"""
        TRADES_RECEIVED.inc()
        
        message = {
            "symbol": trade.symbol,
            "price": float(trade.price),
            "size": int(trade.size),
            "timestamp": trade.timestamp.isoformat(),
            "trade_id": str(trade.id)
        }
        
        async with KAFKA_PUBLISH_TIME.time():
            await self.producer.send_and_wait(
                self.config.kafka_topic_trades,
                key=trade.symbol.encode('utf-8'),
                value=message
            )
            
    async def start(self):
        """Start the market data service"""
        # Start Prometheus metrics server
        start_http_server(self.config.metrics_port)
        logger.info(f"Started metrics server on port {self.config.metrics_port}")
        
        # Setup Kafka producer
        await self._setup_kafka_producer()
        logger.info("Connected to Kafka cluster")
        
        # Subscribe to market data
        self.stock_stream.subscribe_quotes(*self.active_symbols)
        self.stock_stream.subscribe_trades(*self.active_symbols)
        ACTIVE_SUBSCRIPTIONS.set(len(self.active_symbols))
        logger.info(f"Subscribed to {len(self.active_symbols)} symbols")
        
        try:
            await self.stock_stream.run()
        finally:
            await self.producer.stop()
            
async def main():
    # Load configuration from environment or use defaults
    config = MarketDataConfig(
        kafka_bootstrap_servers=os.environ.get(
            "KAFKA_BOOTSTRAP_SERVERS", 
            "hft-dev-kafka:9092"
        ).split(","),
        symbols=os.environ.get(
            "WATCH_SYMBOLS", 
            "SPY,TLT"
        ).split(",")
    )
    
    service = MarketDataService(config)
    await service.start()

if __name__ == "__main__":
    asyncio.run(main())
