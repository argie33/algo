/**
 * Live Market Data Feed Adapter
 * 
 * Connects HFT system to real-time market data sources:
 * - Alpaca WebSocket feeds
 * - AWS RDS technical data
 * - Redis cache for ultra-fast access
 * 
 * Optimized for sub-millisecond latency
 */

import WebSocket from 'ws';
import { EventEmitter } from 'events';
import { Redis } from 'ioredis';
import { Pool } from 'pg';
import type { Logger } from 'pino';
import type { Config } from '../../config';

export interface MarketTick {
  symbol: string;
  price: number;
  size: number;
  timestamp: bigint;
  sequence: number;
  exchange: string;
  bid?: number;
  ask?: number;
  bidSize?: number;
  askSize?: number;
}

export interface L2Update {
  symbol: string;
  bids: Array<[number, number]>; // [price, size]
  asks: Array<[number, number]>;
  timestamp: bigint;
  sequence: number;
}

export class LiveMarketDataAdapter extends EventEmitter {
  private ws: WebSocket | null = null;
  private redis: Redis;
  private dbPool: Pool;
  private logger: Logger;
  private config: Config;
  
  private connected: boolean = false;
  private subscriptions: Set<string> = new Set();
  private sequenceNumber: number = 0;
  private lastHeartbeat: number = 0;
  
  // Performance metrics
  private ticksReceived: number = 0;
  private avgLatency: number = 0;
  private maxLatency: number = 0;
  
  // Buffer for batch operations
  private tickBuffer: MarketTick[] = [];
  private readonly BUFFER_SIZE = 100;
  private readonly FLUSH_INTERVAL = 50; // 50ms
  
  constructor(config: Config, logger: Logger) {
    super();
    this.config = config;
    this.logger = logger;
    
    // Initialize Redis for ultra-fast caching
    this.redis = new Redis({
      host: config.redis.host,
      port: config.redis.port,
      password: config.redis.password,
      db: config.redis.db,
      lazyConnect: true,
      maxRetriesPerRequest: 3,
      retryDelayOnFailover: 100,
      enableAutoPipelining: true
    });
    
    // Initialize database pool
    this.dbPool = new Pool({
      host: config.database.host,
      port: config.database.port,
      database: config.database.database,
      user: config.database.username,
      password: config.database.password,
      ssl: config.database.ssl,
      max: 10, // Smaller pool for real-time operations
      connectionTimeoutMillis: 5000,
      idleTimeoutMillis: 30000
    });
    
    // Start buffer flush timer
    setInterval(() => this.flushTickBuffer(), this.FLUSH_INTERVAL);
  }
  
  /**
   * Connect to live data sources
   */
  async connect(): Promise<void> {
    this.logger.info('Connecting to live market data sources...');
    
    try {
      // Connect to Redis
      await this.redis.connect();
      this.logger.info('✅ Connected to Redis cache');
      
      // Test database connection
      const client = await this.dbPool.connect();
      await client.query('SELECT 1');
      client.release();
      this.logger.info('✅ Connected to PostgreSQL database');
      
      // Connect to WebSocket feed
      await this.connectWebSocket();
      
      this.connected = true;
      this.logger.info('✅ Live market data adapter connected');
      
    } catch (error) {
      this.logger.error('Failed to connect market data adapter:', error);
      throw error;
    }
  }
  
  /**
   * Connect to WebSocket market data feed
   */
  private async connectWebSocket(): Promise<void> {
    return new Promise((resolve, reject) => {
      // Use Alpaca WebSocket endpoint
      const wsUrl = this.config.alpaca.paper ? 
        'wss://stream.data.sandbox.alpaca.markets/v2/iex' :
        'wss://stream.data.alpaca.markets/v2/iex';
      
      this.ws = new WebSocket(wsUrl);
      
      this.ws.on('open', () => {
        this.logger.info('✅ WebSocket connected to Alpaca');
        
        // Authenticate
        this.ws!.send(JSON.stringify({
          action: 'auth',
          key: this.config.alpaca.apiKey,
          secret: this.config.alpaca.secretKey
        }));
        
        resolve();
      });
      
      this.ws.on('message', (data) => {
        this.handleWebSocketMessage(data);
      });
      
      this.ws.on('error', (error) => {
        this.logger.error('WebSocket error:', error);
        reject(error);
      });
      
      this.ws.on('close', () => {
        this.logger.warn('WebSocket connection closed, attempting reconnect...');
        this.connected = false;
        setTimeout(() => this.connectWebSocket(), 5000);
      });
    });
  }
  
  /**
   * Handle incoming WebSocket messages
   */
  private handleWebSocketMessage(data: Buffer): void {
    try {
      const messages = JSON.parse(data.toString());
      
      if (!Array.isArray(messages)) return;
      
      for (const message of messages) {
        this.processMessage(message);
      }
      
    } catch (error) {
      this.logger.error('Error processing WebSocket message:', error);
    }
  }
  
  /**
   * Process individual market data message
   */
  private processMessage(message: any): void {
    const now = process.hrtime.bigint();
    
    switch (message.T) {
      case 't': // Trade
        this.processTrade(message, now);
        break;
      case 'q': // Quote
        this.processQuote(message, now);
        break;
      case 'b': // Bar
        this.processBar(message, now);
        break;
    }
  }
  
  /**
   * Process trade message
   */
  private processTrade(trade: any, timestamp: bigint): void {
    const tick: MarketTick = {
      symbol: trade.S,
      price: trade.p,
      size: trade.s,
      timestamp,
      sequence: ++this.sequenceNumber,
      exchange: trade.x || 'IEX'
    };
    
    // Add to buffer for batch processing
    this.tickBuffer.push(tick);
    
    // Emit immediately for real-time processing
    this.emit('tick', tick);
    
    // Update metrics
    this.ticksReceived++;
    this.updateLatencyMetrics(trade.t, timestamp);
    
    // Cache in Redis for ultra-fast access
    this.cacheMarketData(tick);
  }
  
  /**
   * Process quote message
   */
  private processQuote(quote: any, timestamp: bigint): void {
    const tick: MarketTick = {
      symbol: quote.S,
      price: (quote.bp + quote.ap) / 2, // Mid price
      size: 0,
      timestamp,
      sequence: ++this.sequenceNumber,
      exchange: 'IEX',
      bid: quote.bp,
      ask: quote.ap,
      bidSize: quote.bs,
      askSize: quote.as
    };
    
    this.emit('quote', tick);
    this.cacheMarketData(tick);
  }
  
  /**
   * Process bar message
   */
  private processBar(bar: any, timestamp: bigint): void {
    // Handle bar data if needed
    this.emit('bar', {
      symbol: bar.S,
      open: bar.o,
      high: bar.h,
      low: bar.l,
      close: bar.c,
      volume: bar.v,
      timestamp,
      vwap: bar.vw
    });
  }
  
  /**
   * Cache market data in Redis for ultra-fast access
   */
  private async cacheMarketData(tick: MarketTick): Promise<void> {
    const key = `tick:${tick.symbol}`;
    const pipeline = this.redis.pipeline();
    
    // Store latest tick
    pipeline.hset(key, {
      price: tick.price,
      size: tick.size,
      timestamp: tick.timestamp.toString(),
      sequence: tick.sequence
    });
    
    // Set expiration
    pipeline.expire(key, 60); // 1 minute TTL
    
    // Add to time series (keep last 1000 ticks)
    const tsKey = `ts:${tick.symbol}`;
    pipeline.lpush(tsKey, JSON.stringify({
      p: tick.price,
      s: tick.size,
      t: tick.timestamp.toString()
    }));
    pipeline.ltrim(tsKey, 0, 999); // Keep only last 1000
    pipeline.expire(tsKey, 300); // 5 minute TTL
    
    try {
      await pipeline.exec();
    } catch (error) {
      this.logger.error('Redis cache error:', error);
    }
  }
  
  /**
   * Subscribe to symbols
   */
  async subscribe(symbols: string[]): Promise<void> {
    if (!this.connected || !this.ws) {
      throw new Error('Not connected to market data feed');
    }
    
    const newSymbols = symbols.filter(s => !this.subscriptions.has(s));
    
    if (newSymbols.length === 0) return;
    
    // Subscribe to trades and quotes
    this.ws.send(JSON.stringify({
      action: 'subscribe',
      trades: newSymbols,
      quotes: newSymbols,
      bars: newSymbols
    }));
    
    newSymbols.forEach(symbol => this.subscriptions.add(symbol));
    
    this.logger.info(`✅ Subscribed to ${newSymbols.length} symbols:`, newSymbols);
  }
  
  /**
   * Unsubscribe from symbols
   */
  async unsubscribe(symbols: string[]): Promise<void> {
    if (!this.connected || !this.ws) return;
    
    const activeSymbols = symbols.filter(s => this.subscriptions.has(s));
    
    if (activeSymbols.length === 0) return;
    
    this.ws.send(JSON.stringify({
      action: 'unsubscribe',
      trades: activeSymbols,
      quotes: activeSymbols,
      bars: activeSymbols
    }));
    
    activeSymbols.forEach(symbol => this.subscriptions.delete(symbol));
    
    this.logger.info(`Unsubscribed from ${activeSymbols.length} symbols`);
  }
  
  /**
   * Get latest market data from cache
   */
  async getLatestTick(symbol: string): Promise<MarketTick | null> {
    try {
      const data = await this.redis.hgetall(`tick:${symbol}`);
      
      if (!data.price) return null;
      
      return {
        symbol,
        price: parseFloat(data.price),
        size: parseInt(data.size),
        timestamp: BigInt(data.timestamp),
        sequence: parseInt(data.sequence),
        exchange: 'IEX'
      };
      
    } catch (error) {
      this.logger.error('Error getting latest tick:', error);
      return null;
    }
  }
  
  /**
   * Get recent price history from cache
   */
  async getRecentTicks(symbol: string, count: number = 100): Promise<MarketTick[]> {
    try {
      const data = await this.redis.lrange(`ts:${symbol}`, 0, count - 1);
      
      return data.map(tick => {
        const parsed = JSON.parse(tick);
        return {
          symbol,
          price: parsed.p,
          size: parsed.s,
          timestamp: BigInt(parsed.t),
          sequence: 0,
          exchange: 'IEX'
        };
      });
      
    } catch (error) {
      this.logger.error('Error getting recent ticks:', error);
      return [];
    }
  }
  
  /**
   * Flush tick buffer to database
   */
  private async flushTickBuffer(): Promise<void> {
    if (this.tickBuffer.length === 0) return;
    
    const ticks = this.tickBuffer.splice(0, this.BUFFER_SIZE);
    
    try {
      const client = await this.dbPool.connect();
      
      // Insert ticks into real-time price table
      const values = ticks.map(tick => 
        `('${tick.symbol}', ${tick.price}, ${tick.size}, to_timestamp(${Number(tick.timestamp)} / 1000000))`
      ).join(',');
      
      const query = `
        INSERT INTO realtime_ticks (symbol, price, size, timestamp)
        VALUES ${values}
        ON CONFLICT (symbol, timestamp) DO UPDATE SET
          price = EXCLUDED.price,
          size = EXCLUDED.size
      `;
      
      await client.query(query);
      client.release();
      
    } catch (error) {
      this.logger.error('Error flushing tick buffer:', error);
      // Return ticks to buffer for retry
      this.tickBuffer.unshift(...ticks);
    }
  }
  
  /**
   * Update latency metrics
   */
  private updateLatencyMetrics(marketTimestamp: number, processTimestamp: bigint): void {
    const latency = Number(processTimestamp) / 1000000 - marketTimestamp; // Convert to ms
    
    if (latency > this.maxLatency) {
      this.maxLatency = latency;
    }
    
    this.avgLatency = (this.avgLatency * (this.ticksReceived - 1) + latency) / this.ticksReceived;
  }
  
  /**
   * Get performance metrics
   */
  getMetrics() {
    return {
      connected: this.connected,
      subscriptions: this.subscriptions.size,
      ticksReceived: this.ticksReceived,
      avgLatency: this.avgLatency,
      maxLatency: this.maxLatency,
      bufferSize: this.tickBuffer.length
    };
  }
  
  /**
   * Disconnect and cleanup
   */
  async disconnect(): Promise<void> {
    this.logger.info('Disconnecting market data adapter...');
    
    this.connected = false;
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    
    await this.redis.quit();
    await this.dbPool.end();
    
    this.logger.info('✅ Market data adapter disconnected');
  }
}
