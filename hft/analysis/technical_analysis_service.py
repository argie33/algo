"""
Technical Analysis Service for HFT System
Processes real-time market data and calculates technical indicators
"""
import os
import json
import logging
import asyncio
from typing import Dict, List
import numpy as np
import pandas as pd
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from prometheus_client import Counter, Gauge, start_http_server
import redis
from pydantic import BaseModel
import talib
from pythonjsonlogger import jsonlogger

# Configure logging
logger = logging.getLogger(__name__)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

# Prometheus metrics
TRADES_PROCESSED = Counter('tech_analysis_trades_processed', 'Number of trades processed')
SIGNALS_GENERATED = Counter('tech_analysis_signals_generated', 'Number of signals generated')
CALC_LATENCY = Gauge('tech_analysis_calculation_latency_ms', 'Technical indicator calculation latency')

class TechnicalAnalysisConfig(BaseModel):
    """Configuration for Technical Analysis Service"""
    symbols: List[str] = ["SPY", "TLT"]  # Default symbols to monitor
    kafka_topic_trades: str = "market.trades"
    kafka_topic_signals: str = "trading.signals"
    kafka_bootstrap_servers: List[str]
    redis_host: str = "localhost"
    redis_port: int = 6379
    metrics_port: int = 8001
    
    # Technical indicator parameters
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0

class TechnicalAnalysisService:
    def __init__(self, config: TechnicalAnalysisConfig):
        self.config = config
        self.data_buffers: Dict[str, List[Dict]] = {sym: [] for sym in config.symbols}
        self._setup_redis()

    def _setup_redis(self):
        """Initialize Redis connection for fast data access"""
        self.redis = redis.Redis(
            host=self.config.redis_host,
            port=self.config.redis_port,
            decode_responses=True
        )
        
    async def _setup_kafka(self):
        """Setup Kafka consumer and producer"""
        self.consumer = AIOKafkaConsumer(
            self.config.kafka_topic_trades,
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            group_id="tech-analysis-service",
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            value_serializer=lambda m: json.dumps(m).encode('utf-8')
        )
        
        await self.consumer.start()
        await self.producer.start()

    def calculate_technical_indicators(self, symbol: str, data: List[Dict]) -> Dict:
        """Calculate technical indicators for a symbol"""
        start_time = pd.Timestamp.now()
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        prices = df['price'].astype(float).values
        
        with CALC_LATENCY.time():
            indicators = {
                'symbol': symbol,
                'timestamp': df.iloc[-1]['timestamp'],
                'last_price': float(prices[-1]),
                
                # RSI
                'rsi': float(talib.RSI(prices, timeperiod=self.config.rsi_period)[-1]),
                
                # MACD
                'macd': None,
                'macd_signal': None,
                'macd_hist': None,
            }
            
            # Calculate MACD
            macd, signal, hist = talib.MACD(
                prices, 
                fastperiod=self.config.macd_fast,
                slowperiod=self.config.macd_slow,
                signalperiod=self.config.macd_signal
            )
            indicators.update({
                'macd': float(macd[-1]),
                'macd_signal': float(signal[-1]),
                'macd_hist': float(hist[-1])
            })
            
            # Bollinger Bands
            upper, middle, lower = talib.BBANDS(
                prices,
                timeperiod=self.config.bb_period,
                nbdevup=self.config.bb_std,
                nbdevdn=self.config.bb_std
            )
            indicators.update({
                'bb_upper': float(upper[-1]),
                'bb_middle': float(middle[-1]), 
                'bb_lower': float(lower[-1])
            })
            
            # Store in Redis for fast access
            self.redis.hmset(
                f"tech_indicators:{symbol}",
                indicators
            )
            
            # Calculate processing latency
            latency = (pd.Timestamp.now() - start_time).total_seconds() * 1000
            indicators['calc_latency_ms'] = latency
            
            return indicators

    def check_signals(self, indicators: Dict) -> List[Dict]:
        """Check for trading signals based on indicators"""
        signals = []
        
        # Example signal logic (customize based on strategy)
        if indicators['rsi'] < 30:
            signals.append({
                'symbol': indicators['symbol'],
                'signal_type': 'BUY',
                'indicator': 'RSI',
                'value': indicators['rsi'],
                'timestamp': indicators['timestamp']
            })
            
        elif indicators['rsi'] > 70:
            signals.append({
                'symbol': indicators['symbol'],
                'signal_type': 'SELL', 
                'indicator': 'RSI',
                'value': indicators['rsi'],
                'timestamp': indicators['timestamp']
            })
            
        # MACD crossover signals
        if (indicators['macd_hist'] > 0 and 
            self.redis.hget(f"tech_indicators:{indicators['symbol']}", 'macd_hist') 
            and float(self.redis.hget(f"tech_indicators:{indicators['symbol']}", 'macd_hist')) < 0):
            
            signals.append({
                'symbol': indicators['symbol'],
                'signal_type': 'BUY',
                'indicator': 'MACD_CROSS',
                'value': indicators['macd_hist'],
                'timestamp': indicators['timestamp']
            })
            
        return signals

    async def process_market_data(self):
        """Process incoming market data and generate signals"""
        try:
            async for msg in self.consumer:
                trade = msg.value
                symbol = trade['symbol']
                
                if symbol not in self.data_buffers:
                    continue
                    
                # Update price buffer
                self.data_buffers[symbol].append(trade)
                if len(self.data_buffers[symbol]) > 100:  # Rolling window
                    self.data_buffers[symbol].pop(0)
                    
                TRADES_PROCESSED.inc()
                
                # Calculate indicators
                if len(self.data_buffers[symbol]) >= 30:  # Minimum data points
                    indicators = self.calculate_technical_indicators(
                        symbol, 
                        self.data_buffers[symbol]
                    )
                    
                    # Check for signals
                    signals = self.check_signals(indicators)
                    
                    if signals:
                        SIGNALS_GENERATED.inc(len(signals))
                        
                        # Publish signals
                        for signal in signals:
                            await self.producer.send_and_wait(
                                self.config.kafka_topic_signals,
                                value=signal
                            )
                            logger.info(f"Signal generated: {signal}")
                            
        except Exception as e:
            logger.error(f"Error processing market data: {str(e)}")
            raise

    async def start(self):
        """Start the technical analysis service"""
        logger.info("Starting Technical Analysis Service...")
        
        # Start Prometheus metrics server
        start_http_server(self.config.metrics_port)
        logger.info(f"Prometheus metrics server started on port {self.config.metrics_port}")
        
        # Setup Kafka
        await self._setup_kafka()
        logger.info("Kafka consumer and producer initialized")
        
        # Start processing
        await self.process_market_data()

    async def cleanup(self):
        """Cleanup resources"""
        await self.consumer.stop()
        await self.producer.stop()
        self.redis.close()

async def main():
    # Load configuration from environment
    config = TechnicalAnalysisConfig(
        kafka_bootstrap_servers=os.environ.get(
            "KAFKA_BOOTSTRAP_SERVERS", 
            "hft-dev-kafka:9092"
        ).split(","),
        redis_host=os.environ.get("REDIS_HOST", "localhost"),
        redis_port=int(os.environ.get("REDIS_PORT", "6379")),
        symbols=os.environ.get("WATCH_SYMBOLS", "SPY,TLT").split(",")
    )
    
    service = TechnicalAnalysisService(config)
    
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Shutting down Technical Analysis Service...")
    finally:
        await service.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
