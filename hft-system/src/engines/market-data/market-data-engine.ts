import WebSocket from 'ws';
import { AlpacaApi } from '@alpacahq/alpaca-trade-api';
import { BaseEngine, MarketTick, Quote, Trade, Bar, MarketDataError, Symbol } from '../../types';
import { Config } from '../../config';
import { Logger } from 'pino';

export interface MarketDataConfig {
  reconnectInterval: number;
  maxReconnectAttempts: number;
  subscriptionBatchSize: number;
  heartbeatInterval: number;
}

/**
 * High-performance market data engine using Alpaca WebSocket
 * Designed for ultra-low latency data ingestion
 */
export class MarketDataEngine extends BaseEngine {
  private alpaca: AlpacaApi;
  private ws: WebSocket | null = null;
  private subscriptions: Set<string> = new Set();
  private reconnectAttempts: number = 0;
  private heartbeatTimer: NodeJS.Timeout | null = null;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private isConnected: boolean = false;
  private messageCount: number = 0;
  private lastHeartbeat: number = 0;
  
  private readonly marketDataConfig: MarketDataConfig = {
    reconnectInterval: 5000,
    maxReconnectAttempts: 10,
    subscriptionBatchSize: 50,
    heartbeatInterval: 30000
  };

  constructor(config: Config, logger: Logger) {
    super('MarketDataEngine', config, logger);
    
    this.alpaca = new AlpacaApi({
      credentials: {
        key: config.alpaca.keyId,
        secret: config.alpaca.secretKey,
        paper: config.alpaca.paper
      },
      baseUrl: config.alpaca.baseUrl
    });
  }

  async initialize(): Promise<void> {
    this.logger.info('Initializing Market Data Engine...');
    
    try {
      // Test Alpaca connection
      const account = await this.alpaca.getAccount();
      this.logger.info({ accountId: account.id }, 'Alpaca connection established');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to connect to Alpaca');
      throw new MarketDataError('Failed to initialize Alpaca connection', { error });
    }
  }

  async start(): Promise<void> {
    if (this.isRunning) return;
    
    this.logger.info('Starting Market Data Engine...');
    
    try {
      await this.connectWebSocket();
      await this.subscribeToSymbols();
      
      this.isRunning = true;
      this.logger.info('Market Data Engine started successfully');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to start Market Data Engine');
      throw error;
    }
  }

  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping Market Data Engine...');
    
    this.isRunning = false;
    
    // Clear timers
    if (this.heartbeatTimer) {
      clearTimeout(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    
    // Close WebSocket
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    
    this.isConnected = false;
    this.logger.info('Market Data Engine stopped');
  }

  /**
   * Connect to Alpaca WebSocket
   */
  private async connectWebSocket(): Promise<void> {
    return new Promise((resolve, reject) => {
      const wsUrl = this.config.alpaca.dataUrl || 'wss://stream.data.alpaca.markets/v2/iex';
      
      this.logger.info({ url: wsUrl }, 'Connecting to market data WebSocket...');
      
      this.ws = new WebSocket(wsUrl);
      
      this.ws.on('open', () => {
        this.logger.info('WebSocket connected');
        this.authenticate()
          .then(() => {
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.startHeartbeat();
            resolve();
          })
          .catch(reject);
      });
      
      this.ws.on('message', (data: Buffer) => {
        this.handleMessage(data);
      });
      
      this.ws.on('close', (code: number, reason: Buffer) => {
        this.logger.warn({ code, reason: reason.toString() }, 'WebSocket closed');
        this.isConnected = false;
        this.handleDisconnection();
      });
      
      this.ws.on('error', (error: Error) => {
        this.logger.error({ error }, 'WebSocket error');
        reject(new MarketDataError('WebSocket connection failed', { error }));
      });
      
      // Connection timeout
      setTimeout(() => {
        if (!this.isConnected) {
          reject(new MarketDataError('WebSocket connection timeout'));
        }
      }, 10000);
    });
  }

  /**
   * Authenticate with Alpaca WebSocket
   */
  private async authenticate(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.ws) {
        reject(new MarketDataError('WebSocket not connected'));
        return;
      }
      
      const authMessage = {
        action: 'auth',
        key: this.config.alpaca.keyId,
        secret: this.config.alpaca.secretKey
      };
      
      this.ws.send(JSON.stringify(authMessage));
      
      // Wait for auth response
      const originalHandler = this.ws.onmessage;
      this.ws.onmessage = (event) => {
        try {
          const messages = JSON.parse(event.data.toString());
          
          for (const message of messages) {
            if (message.T === 'success' && message.msg === 'authenticated') {
              this.logger.info('WebSocket authenticated successfully');
              this.ws!.onmessage = originalHandler;
              resolve();
              return;
            } else if (message.T === 'error') {
              this.logger.error({ message }, 'Authentication failed');
              reject(new MarketDataError('Authentication failed', { message }));
              return;
            }
          }
        } catch (error) {
          reject(new MarketDataError('Failed to parse auth response', { error }));
        }
      };
      
      // Auth timeout
      setTimeout(() => {
        reject(new MarketDataError('Authentication timeout'));
      }, 5000);
    });
  }

  /**
   * Subscribe to market data for all enabled symbols
   */
  private async subscribeToSymbols(): Promise<void> {
    const enabledSymbols = this.config.getEnabledSymbols();
    const symbolNames = enabledSymbols.map(s => s.symbol);
    
    this.logger.info({ symbols: symbolNames }, 'Subscribing to market data...');
    
    // Subscribe to trades, quotes, and bars
    const subscribeMessage = {
      action: 'subscribe',
      trades: symbolNames,
      quotes: symbolNames,
      bars: symbolNames
    };
    
    if (this.ws && this.isConnected) {
      this.ws.send(JSON.stringify(subscribeMessage));
      
      symbolNames.forEach(symbol => {
        this.subscriptions.add(symbol);
      });
      
      this.logger.info({ count: symbolNames.length }, 'Subscribed to symbols');
    }
  }

  /**
   * Handle incoming WebSocket messages
   */
  private handleMessage(data: Buffer): void {
    const startTime = performance.now();
    
    try {
      this.messageCount++;
      this.updateMetric('messages_received', this.messageCount);
      
      const messages = JSON.parse(data.toString());
      
      for (const message of messages) {
        this.processMessage(message, startTime);
      }
      
    } catch (error) {
      this.logger.error({ error, data: data.toString() }, 'Failed to parse message');
      this.incrementMetric('parse_errors');
    }
  }

  /**
   * Process individual market data message
   */
  private processMessage(message: any, receivedTime: number): void {
    const messageType = message.T;
    
    try {
      switch (messageType) {
        case 't': // Trade
          this.processTrade(message, receivedTime);
          break;
        case 'q': // Quote
          this.processQuote(message, receivedTime);
          break;
        case 'b': // Bar
          this.processBar(message, receivedTime);
          break;
        case 'status':
          this.processStatus(message);
          break;
        case 'subscription':
          this.processSubscription(message);
          break;
        default:
          this.logger.debug({ messageType, message }, 'Unknown message type');
      }
    } catch (error) {
      this.logger.error({ error, message }, 'Failed to process message');
      this.incrementMetric('processing_errors');
    }
  }

  /**
   * Process trade message
   */
  private processTrade(message: any, receivedTime: number): void {
    const trade: Trade = {
      symbol: message.S,
      exchange: message.x || 'UNKNOWN',
      timestamp: new Date(message.t).getTime(),
      received_timestamp: receivedTime,
      price: message.p,
      size: message.s,
      conditions: message.c || [],
      tape: message.z
    };
    
    // Record latency
    const latency = receivedTime - trade.timestamp;
    this.recordMetric('trade_latency', latency);
    this.incrementMetric('trades_processed');
    
    // Emit trade event
    this.emit('trade', trade);
    
    // Also emit as tick for signal processing
    const tick: MarketTick = {
      symbol: trade.symbol,
      exchange: trade.exchange,
      timestamp: trade.timestamp,
      received_timestamp: trade.received_timestamp,
      price: trade.price,
      size: trade.size,
      conditions: trade.conditions
    };
    
    this.emit('tick', tick);
  }

  /**
   * Process quote message
   */
  private processQuote(message: any, receivedTime: number): void {
    const quote: Quote = {
      symbol: message.S,
      exchange: 'UNKNOWN',
      timestamp: new Date(message.t).getTime(),
      received_timestamp: receivedTime,
      bid_price: message.bp,
      bid_size: message.bs,
      ask_price: message.ap,
      ask_size: message.as,
      bid_exchange: message.bx,
      ask_exchange: message.ax
    };
    
    // Record latency
    const latency = receivedTime - quote.timestamp;
    this.recordMetric('quote_latency', latency);
    this.incrementMetric('quotes_processed');
    
    // Emit quote event
    this.emit('quote', quote);
  }

  /**
   * Process bar message
   */
  private processBar(message: any, receivedTime: number): void {
    const bar: Bar = {
      symbol: message.S,
      exchange: 'UNKNOWN',
      timestamp: new Date(message.t).getTime(),
      received_timestamp: receivedTime,
      open: message.o,
      high: message.h,
      low: message.l,
      close: message.c,
      volume: message.v,
      trade_count: message.n,
      vwap: message.vw
    };
    
    this.incrementMetric('bars_processed');
    this.emit('bar', bar);
  }

  /**
   * Process status message
   */
  private processStatus(message: any): void {
    this.logger.info({ message }, 'Received status message');
    
    if (message.status === 'connected') {
      this.isConnected = true;
    }
  }

  /**
   * Process subscription confirmation
   */
  private processSubscription(message: any): void {
    this.logger.info({ message }, 'Subscription confirmed');
  }

  /**
   * Handle WebSocket disconnection
   */
  private handleDisconnection(): void {
    this.isConnected = false;
    
    if (this.heartbeatTimer) {
      clearTimeout(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    
    if (this.isRunning && this.reconnectAttempts < this.marketDataConfig.maxReconnectAttempts) {
      this.logger.info({ attempt: this.reconnectAttempts + 1 }, 'Attempting to reconnect...');
      
      this.reconnectTimer = setTimeout(() => {
        this.reconnectAttempts++;
        this.connectWebSocket()
          .then(() => this.subscribeToSymbols())
          .catch((error) => {
            this.logger.error({ error }, 'Reconnection failed');
            this.handleDisconnection();
          });
      }, this.marketDataConfig.reconnectInterval);
    } else {
      this.logger.error('Max reconnection attempts reached');
      this.emit('error', new MarketDataError('Max reconnection attempts reached'));
    }
  }

  /**
   * Start heartbeat monitoring
   */
  private startHeartbeat(): void {
    this.heartbeatTimer = setTimeout(() => {
      if (this.isConnected) {
        this.lastHeartbeat = Date.now();
        this.startHeartbeat(); // Schedule next heartbeat
      }
    }, this.marketDataConfig.heartbeatInterval);
  }

  /**
   * Add symbol subscription
   */
  async subscribeSymbol(symbol: string): Promise<void> {
    if (this.subscriptions.has(symbol)) {
      return;
    }
    
    const subscribeMessage = {
      action: 'subscribe',
      trades: [symbol],
      quotes: [symbol],
      bars: [symbol]
    };
    
    if (this.ws && this.isConnected) {
      this.ws.send(JSON.stringify(subscribeMessage));
      this.subscriptions.add(symbol);
      this.logger.info({ symbol }, 'Added symbol subscription');
    }
  }

  /**
   * Remove symbol subscription
   */
  async unsubscribeSymbol(symbol: string): Promise<void> {
    if (!this.subscriptions.has(symbol)) {
      return;
    }
    
    const unsubscribeMessage = {
      action: 'unsubscribe',
      trades: [symbol],
      quotes: [symbol],
      bars: [symbol]
    };
    
    if (this.ws && this.isConnected) {
      this.ws.send(JSON.stringify(unsubscribeMessage));
      this.subscriptions.delete(symbol);
      this.logger.info({ symbol }, 'Removed symbol subscription');
    }
  }

  /**
   * Get connection status
   */
  getConnectionStatus(): any {
    return {
      connected: this.isConnected,
      subscriptions: Array.from(this.subscriptions),
      messageCount: this.messageCount,
      reconnectAttempts: this.reconnectAttempts,
      lastHeartbeat: this.lastHeartbeat
    };
  }

  /**
   * Record a metric (helper method)
   */
  private recordMetric(name: string, value: number): void {
    this.updateMetric(name, value);
  }
}
