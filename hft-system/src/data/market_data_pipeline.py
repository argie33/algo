#!/usr/bin/env python3
"""
Budget Alpha HFT System - Market Data Pipeline
High-performance real-time market data ingestion for 100+ symbols
Designed for $500-1000/month budget with institutional-grade signal quality
"""

import asyncio
import aiohttp
import time
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import pandas as pd
import numpy as np
import redis
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import yfinance as yf
from alpaca_trade_api import REST, Stream
from alpaca_trade_api.common import URL
import websocket
import threading
import queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class MarketTick:
    """Standardized market data tick structure"""
    symbol: str
    timestamp: int  # Unix timestamp in microseconds
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    last_price: float
    last_size: int
    volume: int
    vwap: float
    high: float
    low: float
    open: float
    prev_close: float

@dataclass
class OrderBookLevel:
    """Order book level data"""
    price: float
    size: int
    orders: int

@dataclass
class OrderBookSnapshot:
    """Full order book snapshot"""
    symbol: str
    timestamp: int
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    
class MarketDataPipeline:
    """
    High-performance market data pipeline optimized for budget alpha generation.
    Combines multiple data sources for comprehensive market coverage.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.redis_client = redis.Redis(
            host=config.get('redis_host', 'localhost'),
            port=config.get('redis_port', 6379),
            decode_responses=True
        )
        
        # Symbol universe - focus on liquid, tradeable symbols
        self.symbols = self._load_symbol_universe()
        
        # Data feeds
        self.alpaca_client = REST(
            config['alpaca_api_key'],
            config['alpaca_secret_key'],
            URL(config.get('alpaca_base_url', 'https://paper-api.alpaca.markets'))
        )
        
        # Data queues for real-time processing
        self.tick_queue = asyncio.Queue(maxsize=10000)
        self.orderbook_queue = asyncio.Queue(maxsize=1000)
        
        # Statistics tracking
        self.stats = {
            'ticks_received': 0,
            'ticks_processed': 0,
            'last_update': time.time(),
            'symbols_active': set(),
            'feed_latency': deque(maxlen=1000)
        }
        
        # Running data for calculations
        self.market_data = {}  # symbol -> latest tick
        self.volume_profiles = defaultdict(lambda: deque(maxlen=390))  # 6.5 hours of minutes
        self.price_history = defaultdict(lambda: deque(maxlen=1000))
        
    def _load_symbol_universe(self) -> List[str]:
        """
        Load optimized symbol universe for budget alpha generation.
        Focus on liquid symbols with good signal-to-noise ratio.
        """
        # Core liquid ETFs and stocks
        core_symbols = [
            # Major ETFs
            'SPY', 'QQQ', 'IWM', 'VTI', 'EFA', 'EEM', 'GLD', 'SLV', 'TLT', 'HYG',
            'XLE', 'XLF', 'XLK', 'XLV', 'XLI', 'XLP', 'XLY', 'XLU', 'XLRE', 'XLB',
            
            # Large cap tech (high volume, good for algo trading)
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 
            'CRM', 'ADBE', 'ORCL', 'INTC', 'AMD', 'PYPL', 'UBER', 'SPOT',
            
            # Financial sector (sensitive to news/sentiment)
            'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'TFC', 'COF',
            
            # Healthcare (earnings plays)
            'JNJ', 'PFE', 'UNH', 'MRK', 'ABT', 'TMO', 'DHR', 'BMY', 'AMGN', 'GILD',
            
            # Consumer (sentiment sensitive)
            'WMT', 'HD', 'PG', 'KO', 'PEP', 'MCD', 'NKE', 'SBUX', 'TGT', 'COST',
            
            # Meme stocks (social sentiment plays)
            'GME', 'AMC', 'PLTR', 'WISH', 'CLOV', 'BB', 'NOK', 'SNDL', 'TLRY'
        ]
        
        # Add most active options symbols (good for flow analysis)
        options_active = [
            'SPX', 'SPXW', 'QQQS', 'IWMM', 'VIXM'  # Index options
        ]
        
        return core_symbols[:self.config.get('max_symbols', 100)]
    
    async def start_feeds(self):
        """Start all market data feeds"""
        logger.info(f"Starting market data feeds for {len(self.symbols)} symbols")
        
        # Start feed tasks concurrently
        tasks = [
            self._start_alpaca_stream(),
            self._start_yahoo_supplemental(),
            self._start_tick_processor(),
            self._start_orderbook_processor(),
            self._start_statistics_updater()
        ]
        
        await asyncio.gather(*tasks)
    
    async def _start_alpaca_stream(self):
        """Start Alpaca real-time stream for quotes and trades"""
        try:
            stream = Stream(
                self.config['alpaca_api_key'],
                self.config['alpaca_secret_key'],
                URL(self.config.get('alpaca_base_url', 'https://paper-api.alpaca.markets'))
            )
            
            # Subscribe to quotes and trades
            @stream.on_quote
            async def on_quote(quote):
                await self._process_quote(quote)
            
            @stream.on_trade
            async def on_trade(trade):
                await self._process_trade(trade)
                
            # Subscribe to symbols
            stream.subscribe_quotes(*self.symbols)
            stream.subscribe_trades(*self.symbols)
            
            logger.info("Starting Alpaca stream...")
            await stream._run_forever()
            
        except Exception as e:
            logger.error(f"Alpaca stream error: {e}")
            await asyncio.sleep(5)  # Retry after 5 seconds
            await self._start_alpaca_stream()
    
    async def _start_yahoo_supplemental(self):
        """Start Yahoo Finance supplemental data for additional coverage"""
        while True:
            try:
                # Get supplemental data every 15 seconds
                for symbol_batch in self._batch_symbols(self.symbols, 20):
                    await self._fetch_yahoo_batch(symbol_batch)
                    await asyncio.sleep(1)  # Rate limiting
                
                await asyncio.sleep(15)
                
            except Exception as e:
                logger.error(f"Yahoo supplemental error: {e}")
                await asyncio.sleep(30)
    
    async def _fetch_yahoo_batch(self, symbols: List[str]):
        """Fetch Yahoo Finance data for symbol batch"""
        try:
            # Use yfinance to get current data
            tickers = yf.Tickers(' '.join(symbols))
            
            for symbol in symbols:
                try:
                    ticker = tickers.tickers[symbol]
                    info = ticker.fast_info
                    
                    if hasattr(info, 'last_price') and info.last_price:
                        # Create supplemental tick
                        tick = MarketTick(
                            symbol=symbol,
                            timestamp=int(time.time() * 1_000_000),
                            bid=getattr(info, 'bid', info.last_price * 0.999),
                            ask=getattr(info, 'ask', info.last_price * 1.001),
                            bid_size=0,
                            ask_size=0,
                            last_price=info.last_price,
                            last_size=0,
                            volume=getattr(info, 'volume', 0),
                            vwap=info.last_price,  # Approximate
                            high=getattr(info, 'day_high', info.last_price),
                            low=getattr(info, 'day_low', info.last_price),
                            open=getattr(info, 'open', info.last_price),
                            prev_close=getattr(info, 'previous_close', info.last_price)
                        )
                        
                        await self.tick_queue.put(tick)
                        
                except Exception as e:
                    logger.debug(f"Error fetching {symbol}: {e}")
                    
        except Exception as e:
            logger.error(f"Yahoo batch fetch error: {e}")
    
    def _batch_symbols(self, symbols: List[str], batch_size: int) -> List[List[str]]:
        """Split symbols into batches"""
        return [symbols[i:i+batch_size] for i in range(0, len(symbols), batch_size)]
    
    async def _process_quote(self, quote):
        """Process Alpaca quote data"""
        try:
            # Convert to standardized tick format
            current_data = self.market_data.get(quote.symbol, {})
            
            tick = MarketTick(
                symbol=quote.symbol,
                timestamp=int(quote.timestamp.timestamp() * 1_000_000),
                bid=float(quote.bid_price),
                ask=float(quote.ask_price),
                bid_size=int(quote.bid_size),
                ask_size=int(quote.ask_size),
                last_price=current_data.get('last_price', float(quote.bid_price + quote.ask_price) / 2),
                last_size=current_data.get('last_size', 0),
                volume=current_data.get('volume', 0),
                vwap=current_data.get('vwap', float(quote.bid_price + quote.ask_price) / 2),
                high=current_data.get('high', float(quote.ask_price)),
                low=current_data.get('low', float(quote.bid_price)),
                open=current_data.get('open', float(quote.bid_price + quote.ask_price) / 2),
                prev_close=current_data.get('prev_close', float(quote.bid_price + quote.ask_price) / 2)
            )
            
            await self.tick_queue.put(tick)
            self.stats['ticks_received'] += 1
            
        except Exception as e:
            logger.error(f"Error processing quote for {quote.symbol}: {e}")
    
    async def _process_trade(self, trade):
        """Process Alpaca trade data"""
        try:
            # Update market data with trade information
            current_data = self.market_data.get(trade.symbol, {})
            
            tick = MarketTick(
                symbol=trade.symbol,
                timestamp=int(trade.timestamp.timestamp() * 1_000_000),
                bid=current_data.get('bid', float(trade.price) * 0.999),
                ask=current_data.get('ask', float(trade.price) * 1.001),
                bid_size=current_data.get('bid_size', 0),
                ask_size=current_data.get('ask_size', 0),
                last_price=float(trade.price),
                last_size=int(trade.size),
                volume=current_data.get('volume', 0) + int(trade.size),
                vwap=self._calculate_vwap(trade.symbol, float(trade.price), int(trade.size)),
                high=max(current_data.get('high', float(trade.price)), float(trade.price)),
                low=min(current_data.get('low', float(trade.price)), float(trade.price)),
                open=current_data.get('open', float(trade.price)),
                prev_close=current_data.get('prev_close', float(trade.price))
            )
            
            await self.tick_queue.put(tick)
            self.stats['ticks_received'] += 1
            
        except Exception as e:
            logger.error(f"Error processing trade for {trade.symbol}: {e}")
    
    def _calculate_vwap(self, symbol: str, price: float, size: int) -> float:
        """Calculate volume-weighted average price"""
        if symbol not in self.volume_profiles:
            return price
            
        profile = self.volume_profiles[symbol]
        if len(profile) == 0:
            return price
            
        # Add current trade to profile
        profile.append((price, size))
        
        # Calculate VWAP from recent trades
        total_value = sum(p * v for p, v in profile)
        total_volume = sum(v for p, v in profile)
        
        return total_value / total_volume if total_volume > 0 else price
    
    async def _start_tick_processor(self):
        """Process market data ticks in real-time"""
        while True:
            try:
                # Process ticks from queue
                tick = await self.tick_queue.get()
                await self._process_tick(tick)
                self.stats['ticks_processed'] += 1
                
            except Exception as e:
                logger.error(f"Tick processor error: {e}")
                await asyncio.sleep(0.1)
    
    async def _process_tick(self, tick: MarketTick):
        """Process individual market tick"""
        try:
            # Update latest market data
            self.market_data[tick.symbol] = asdict(tick)
            self.stats['symbols_active'].add(tick.symbol)
            
            # Update price history
            self.price_history[tick.symbol].append({
                'timestamp': tick.timestamp,
                'price': tick.last_price,
                'volume': tick.last_size,
                'bid': tick.bid,
                'ask': tick.ask
            })
            
            # Store in Redis for real-time access
            await self._store_tick_redis(tick)
            
            # Calculate derived signals
            signals = await self._calculate_signals(tick)
            
            # Store signals
            if signals:
                await self._store_signals(tick.symbol, signals)
                
        except Exception as e:
            logger.error(f"Error processing tick for {tick.symbol}: {e}")
    
    async def _store_tick_redis(self, tick: MarketTick):
        """Store tick data in Redis for real-time access"""
        try:
            # Store latest tick
            key = f"tick:{tick.symbol}"
            await asyncio.get_event_loop().run_in_executor(
                None, 
                self.redis_client.hset,
                key,
                mapping=asdict(tick)
            )
            
            # Set expiration
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.redis_client.expire,
                key,
                300  # 5 minutes
            )
            
            # Store in time-series for historical analysis
            ts_key = f"ts:{tick.symbol}"
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.redis_client.zadd,
                ts_key,
                {json.dumps(asdict(tick)): tick.timestamp}
            )
            
            # Keep only last 1 hour of data
            cutoff = tick.timestamp - (60 * 60 * 1_000_000)  # 1 hour ago
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.redis_client.zremrangebyscore,
                ts_key,
                0,
                cutoff
            )
            
        except Exception as e:
            logger.error(f"Redis storage error for {tick.symbol}: {e}")
    
    async def _calculate_signals(self, tick: MarketTick) -> Dict[str, float]:
        """Calculate real-time trading signals from market data"""
        try:
            signals = {}
            
            # Get recent price history
            history = list(self.price_history[tick.symbol])
            if len(history) < 20:
                return signals
            
            prices = [h['price'] for h in history[-20:]]
            volumes = [h['volume'] for h in history[-20:]]
            
            # 1. Momentum signal
            if len(prices) >= 10:
                momentum = (prices[-1] - prices[-10]) / prices[-10]
                signals['momentum_10'] = momentum
            
            # 2. Mean reversion signal
            if len(prices) >= 20:
                sma_20 = np.mean(prices[-20:])
                mean_reversion = (tick.last_price - sma_20) / sma_20
                signals['mean_reversion_20'] = -mean_reversion  # Negative for reversion
            
            # 3. Spread signal (liquidity measure)
            if tick.bid > 0 and tick.ask > 0:
                spread = (tick.ask - tick.bid) / tick.last_price
                signals['spread'] = spread
            
            # 4. Volume signal
            if len(volumes) >= 10:
                avg_volume = np.mean([v for v in volumes[-10:] if v > 0])
                if avg_volume > 0:
                    volume_ratio = tick.last_size / avg_volume
                    signals['volume_surge'] = min(volume_ratio, 5.0)  # Cap at 5x
            
            # 5. Order book imbalance
            if tick.bid_size > 0 and tick.ask_size > 0:
                total_size = tick.bid_size + tick.ask_size
                imbalance = (tick.bid_size - tick.ask_size) / total_size
                signals['order_book_imbalance'] = imbalance
            
            return signals
            
        except Exception as e:
            logger.error(f"Signal calculation error for {tick.symbol}: {e}")
            return {}
    
    async def _store_signals(self, symbol: str, signals: Dict[str, float]):
        """Store calculated signals for strategy consumption"""
        try:
            # Store in Redis with timestamp
            signal_key = f"signals:{symbol}"
            timestamp = int(time.time() * 1_000_000)
            
            signal_data = {
                'timestamp': timestamp,
                **signals
            }
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.redis_client.hset,
                signal_key,
                mapping=signal_data
            )
            
            # Also store in time-series for backtesting
            ts_signal_key = f"signals_ts:{symbol}"
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.redis_client.zadd,
                ts_signal_key,
                {json.dumps(signal_data): timestamp}
            )
            
        except Exception as e:
            logger.error(f"Signal storage error for {symbol}: {e}")
    
    async def _start_orderbook_processor(self):
        """Process order book data for market microstructure analysis"""
        # Placeholder for order book processing
        # This would connect to a provider with Level 2 data
        while True:
            await asyncio.sleep(1)
    
    async def _start_statistics_updater(self):
        """Update system statistics periodically"""
        while True:
            try:
                await asyncio.sleep(10)  # Update every 10 seconds
                
                current_time = time.time()
                elapsed = current_time - self.stats['last_update']
                
                ticks_per_second = self.stats['ticks_processed'] / elapsed if elapsed > 0 else 0
                
                stats_update = {
                    'timestamp': current_time,
                    'ticks_per_second': ticks_per_second,
                    'active_symbols': len(self.stats['symbols_active']),
                    'total_symbols': len(self.symbols),
                    'queue_size': self.tick_queue.qsize()
                }
                
                # Store stats in Redis
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.redis_client.hset,
                    'market_data_stats',
                    mapping=stats_update
                )
                
                logger.info(f"Stats: {ticks_per_second:.1f} ticks/sec, "
                          f"{len(self.stats['symbols_active'])} active symbols, "
                          f"queue: {self.tick_queue.qsize()}")
                
                # Reset counters
                self.stats['ticks_processed'] = 0
                self.stats['last_update'] = current_time
                self.stats['symbols_active'].clear()
                
            except Exception as e:
                logger.error(f"Statistics update error: {e}")
    
    def get_latest_tick(self, symbol: str) -> Optional[MarketTick]:
        """Get latest tick for symbol"""
        data = self.market_data.get(symbol)
        if data:
            return MarketTick(**data)
        return None
    
    def get_market_summary(self) -> Dict[str, Any]:
        """Get market data summary"""
        return {
            'active_symbols': len(self.market_data),
            'total_symbols': len(self.symbols),
            'last_update': max([d.get('timestamp', 0) for d in self.market_data.values()] or [0]),
            'symbols': list(self.market_data.keys())
        }

async def main():
    """Main entry point for market data pipeline"""
    
    # Configuration
    config = {
        'alpaca_api_key': os.getenv('ALPACA_API_KEY'),
        'alpaca_secret_key': os.getenv('ALPACA_SECRET_KEY'),
        'alpaca_base_url': os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets'),
        'redis_host': os.getenv('REDIS_HOST', 'localhost'),
        'redis_port': int(os.getenv('REDIS_PORT', 6379)),
        'max_symbols': int(os.getenv('MAX_SYMBOLS', 100))
    }
    
    # Validate configuration
    if not config['alpaca_api_key'] or not config['alpaca_secret_key']:
        logger.error("Missing Alpaca API credentials")
        return
    
    # Start pipeline
    pipeline = MarketDataPipeline(config)
    
    logger.info("Starting Budget Alpha Market Data Pipeline...")
    await pipeline.start_feeds()

if __name__ == "__main__":
    asyncio.run(main())