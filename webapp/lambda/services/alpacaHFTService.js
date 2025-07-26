/**
 * Alpaca HFT Service - High Frequency Trading Integration
 * Handles real-time order execution, position management, and live data streaming
 */

const Alpaca = require('@alpacahq/alpaca-trade-api');
const { createLogger } = require('../utils/structuredLogger');
const { query } = require('../utils/database');

class AlpacaHFTService {
  constructor(apiKey, apiSecret, isPaper = true) {
    this.logger = createLogger('financial-platform', 'alpaca-hft-service');
    this.correlationId = this.generateCorrelationId();
    
    // Initialize Alpaca client
    this.alpaca = new Alpaca({
      key: apiKey,
      secret: apiSecret,
      paper: isPaper,
      usePolygon: false // Use Alpaca's data feed for HFT
    });
    
    this.isPaper = isPaper;
    this.connected = false;
    this.websocket = null;
    this.subscriptions = new Map();
    
    // Performance tracking
    this.metrics = {
      ordersSubmitted: 0,
      ordersFilled: 0,
      ordersRejected: 0,
      avgExecutionTime: 0,
      totalExecutionTime: 0,
      lastHeartbeat: Date.now()
    };
    
    // Connection state
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000; // Start with 1 second
  }

  generateCorrelationId() {
    return `alpaca-hft-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Initialize the HFT service connection
   */
  async initialize() {
    try {
      this.logger.info('Initializing Alpaca HFT Service', {
        isPaper: this.isPaper,
        correlationId: this.correlationId
      });

      // Verify account access
      const account = await this.alpaca.getAccount();
      
      if (!account) {
        throw new Error('Unable to access Alpaca account');
      }

      this.logger.info('Alpaca account verified', {
        accountId: account.id,
        buyingPower: account.buying_power,
        accountType: this.isPaper ? 'paper' : 'live',
        correlationId: this.correlationId
      });

      // Initialize WebSocket connection for real-time data
      await this.initializeWebSocket();
      
      this.connected = true;
      return {
        success: true,
        account: {
          id: account.id,
          buyingPower: parseFloat(account.buying_power),
          equity: parseFloat(account.equity),
          dayTradeCount: account.day_trade_count,
          status: account.status
        }
      };

    } catch (error) {
      this.logger.error('Failed to initialize Alpaca HFT Service', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      return { success: false, error: error.message };
    }
  }

  /**
   * Initialize WebSocket connection for real-time market data
   */
  async initializeWebSocket() {
    try {
      this.logger.info('Initializing WebSocket connection', {
        correlationId: this.correlationId
      });

      // Create WebSocket connection for real-time data
      this.websocket = this.alpaca.data_stream_v2;
      
      // Set up event handlers
      this.websocket.onConnect(() => {
        this.logger.info('WebSocket connected', { correlationId: this.correlationId });
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
      });

      this.websocket.onDisconnect(() => {
        this.logger.warn('WebSocket disconnected', { correlationId: this.correlationId });
        this.scheduleReconnect();
      });

      this.websocket.onStateChange((state) => {
        this.logger.info('WebSocket state changed', { 
          state, 
          correlationId: this.correlationId 
        });
      });

      this.websocket.onError((error) => {
        this.logger.error('WebSocket error', { 
          error: error.message, 
          correlationId: this.correlationId 
        });
      });

      // Connect to WebSocket
      this.websocket.connect();

    } catch (error) {
      this.logger.error('Failed to initialize WebSocket', {
        error: error.message,
        correlationId: this.correlationId
      });
      throw error;
    }
  }

  /**
   * Schedule WebSocket reconnection with exponential backoff
   */
  scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.logger.error('Max reconnection attempts reached', {
        attempts: this.reconnectAttempts,
        correlationId: this.correlationId
      });
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

    this.logger.info('Scheduling WebSocket reconnection', {
      attempt: this.reconnectAttempts,
      delay,
      correlationId: this.correlationId
    });

    setTimeout(() => {
      this.initializeWebSocket();
    }, delay);
  }

  /**
   * Subscribe to real-time market data for HFT symbols
   */
  async subscribeToMarketData(symbols, onDataReceived) {
    if (!this.websocket || !this.connected) {
      throw new Error('WebSocket not connected');
    }

    try {
      this.logger.info('Subscribing to market data', {
        symbols,
        correlationId: this.correlationId
      });

      // Subscribe to trades and quotes
      symbols.forEach(symbol => {
        // Subscribe to trades
        this.websocket.onStockTrade((subject, data) => {
          if (data.Symbol === symbol) {
            const marketData = {
              symbol: data.Symbol,
              price: data.Price,
              size: data.Size,
              timestamp: data.Timestamp,
              type: 'trade',
              source: 'alpaca'
            };
            
            onDataReceived(marketData);
          }
        });

        // Subscribe to quotes
        this.websocket.onStockQuote((subject, data) => {
          if (data.Symbol === symbol) {
            const marketData = {
              symbol: data.Symbol,
              bid: data.BidPrice,
              ask: data.AskPrice,
              bidSize: data.BidSize,
              askSize: data.AskSize,
              timestamp: data.Timestamp,
              type: 'quote',
              source: 'alpaca'
            };
            
            onDataReceived(marketData);
          }
        });

        this.subscriptions.set(symbol, {
          subscribed: true,
          subscribedAt: Date.now()
        });
      });

      // Subscribe to the symbols
      this.websocket.subscribeForTrades(symbols);
      this.websocket.subscribeForQuotes(symbols);

      return { success: true, subscribedSymbols: symbols };

    } catch (error) {
      this.logger.error('Failed to subscribe to market data', {
        error: error.message,
        symbols,
        correlationId: this.correlationId
      });
      
      return { success: false, error: error.message };
    }
  }

  /**
   * Execute HFT order with ultra-low latency
   */
  async executeHFTOrder(signal) {
    const startTime = Date.now();
    const orderId = this.generateOrderId();

    try {
      this.logger.info('Executing HFT order', {
        orderId,
        symbol: signal.symbol,
        side: signal.type,
        quantity: signal.quantity,
        correlationId: this.correlationId
      });

      // Validate order parameters
      const validation = this.validateOrderParameters(signal);
      if (!validation.valid) {
        throw new Error(`Order validation failed: ${validation.reason}`);
      }

      // Prepare Alpaca order request
      const orderRequest = {
        symbol: signal.symbol.replace('/', ''), // Remove slash for Alpaca format
        qty: Math.abs(signal.quantity),
        side: signal.type.toLowerCase(),
        type: 'market', // Use market orders for HFT speed
        time_in_force: 'ioc', // Immediate or Cancel for HFT
        client_order_id: orderId
      };

      // Add limit price if specified
      if (signal.price && signal.orderType === 'limit') {
        orderRequest.type = 'limit';
        orderRequest.limit_price = signal.price;
      }

      this.metrics.ordersSubmitted++;

      // Submit order to Alpaca
      const alpacaOrder = await this.alpaca.createOrder(orderRequest);
      
      const executionTime = Date.now() - startTime;
      this.updateExecutionMetrics(executionTime);

      // Store order in database
      await this.recordOrderExecution(orderId, signal, alpacaOrder, executionTime);

      this.logger.info('HFT order executed successfully', {
        orderId,
        alpacaOrderId: alpacaOrder.id,
        status: alpacaOrder.status,
        executionTime,
        correlationId: this.correlationId
      });

      this.metrics.ordersFilled++;

      return {
        success: true,
        orderId,
        alpacaOrderId: alpacaOrder.id,
        status: alpacaOrder.status,
        executedPrice: parseFloat(alpacaOrder.filled_avg_price || signal.price),
        executedQuantity: parseFloat(alpacaOrder.filled_qty || signal.quantity),
        executionTime,
        commission: parseFloat(alpacaOrder.commission || 0)
      };

    } catch (error) {
      const executionTime = Date.now() - startTime;
      
      this.logger.error('HFT order execution failed', {
        orderId,
        error: error.message,
        executionTime,
        correlationId: this.correlationId
      });

      this.metrics.ordersRejected++;

      // Record failed order
      await this.recordFailedOrder(orderId, signal, error.message, executionTime);

      return {
        success: false,
        orderId,
        error: error.message,
        executionTime
      };
    }
  }

  /**
   * Validate order parameters before execution
   */
  validateOrderParameters(signal) {
    // Check required fields
    if (!signal.symbol || !signal.type || !signal.quantity) {
      return { valid: false, reason: 'Missing required order parameters' };
    }

    // Check quantity is positive
    if (signal.quantity <= 0) {
      return { valid: false, reason: 'Order quantity must be positive' };
    }

    // Check valid order type
    if (!['BUY', 'SELL'].includes(signal.type.toUpperCase())) {
      return { valid: false, reason: 'Invalid order type' };
    }

    // Check symbol format
    if (!signal.symbol.match(/^[A-Z]{1,10}(\/[A-Z]{3})?$/)) {
      return { valid: false, reason: 'Invalid symbol format' };
    }

    return { valid: true };
  }

  /**
   * Get real-time position information
   */
  async getPositions() {
    try {
      const positions = await this.alpaca.getPositions();
      
      return positions.map(position => ({
        symbol: position.symbol,
        quantity: parseFloat(position.qty),
        side: position.side,
        marketValue: parseFloat(position.market_value),
        costBasis: parseFloat(position.cost_basis),
        unrealizedPL: parseFloat(position.unrealized_pl),
        unrealizedPLPercent: parseFloat(position.unrealized_plpc),
        currentPrice: parseFloat(position.current_price),
        avgEntryPrice: parseFloat(position.avg_entry_price)
      }));

    } catch (error) {
      this.logger.error('Failed to get positions', {
        error: error.message,
        correlationId: this.correlationId
      });
      throw error;
    }
  }

  /**
   * Get account information
   */
  async getAccount() {
    try {
      const account = await this.alpaca.getAccount();
      
      return {
        id: account.id,
        accountNumber: account.account_number,
        status: account.status,
        currency: account.currency,
        buyingPower: parseFloat(account.buying_power),
        equity: parseFloat(account.equity),
        cash: parseFloat(account.cash),
        portfolioValue: parseFloat(account.portfolio_value),
        dayTradeCount: account.day_trade_count,
        daytrader: account.pattern_day_trader,
        tradingBlocked: account.trading_blocked,
        transfersBlocked: account.transfers_blocked,
        accountBlocked: account.account_blocked
      };

    } catch (error) {
      this.logger.error('Failed to get account', {
        error: error.message,
        correlationId: this.correlationId
      });
      throw error;
    }
  }

  /**
   * Record order execution in database
   */
  async recordOrderExecution(orderId, signal, alpacaOrder, executionTime) {
    try {
      const sql = `
        INSERT INTO hft_orders (
          user_id, strategy_id, symbol, order_type, side, quantity, 
          price, status, time_in_force, alpaca_order_id, execution_time_ms,
          filled_quantity, avg_fill_price, submitted_at, metadata
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
      `;

      await query(sql, [
        signal.userId || 'system',
        signal.strategyId || null,
        signal.symbol,
        'market',
        signal.type.toUpperCase(),
        signal.quantity,
        signal.price || null,
        alpacaOrder.status,
        'ioc',
        alpacaOrder.id,
        executionTime,
        parseFloat(alpacaOrder.filled_qty || 0),
        parseFloat(alpacaOrder.filled_avg_price || 0),
        new Date(),
        JSON.stringify({
          orderId,
          clientOrderId: alpacaOrder.client_order_id,
          submittedAt: alpacaOrder.submitted_at,
          isPaper: this.isPaper
        })
      ]);

    } catch (error) {
      this.logger.error('Failed to record order execution', {
        orderId,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Record failed order attempt
   */
  async recordFailedOrder(orderId, signal, errorMessage, executionTime) {
    try {
      const sql = `
        INSERT INTO hft_orders (
          user_id, strategy_id, symbol, order_type, side, quantity, 
          status, execution_time_ms, metadata
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
      `;

      await query(sql, [
        signal.userId || 'system',
        signal.strategyId || null,
        signal.symbol,
        'market',
        signal.type.toUpperCase(),
        signal.quantity,
        'REJECTED',
        executionTime,
        JSON.stringify({
          orderId,
          error: errorMessage,
          isPaper: this.isPaper,
          failedAt: new Date().toISOString()
        })
      ]);

    } catch (error) {
      this.logger.error('Failed to record failed order', {
        orderId,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Update execution time metrics
   */
  updateExecutionMetrics(executionTime) {
    this.metrics.totalExecutionTime += executionTime;
    this.metrics.avgExecutionTime = this.metrics.totalExecutionTime / this.metrics.ordersSubmitted;
  }

  /**
   * Generate unique order ID
   */
  generateOrderId() {
    return `hft-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Get performance metrics
   */
  getMetrics() {
    return {
      ...this.metrics,
      connected: this.connected,
      subscriptions: this.subscriptions.size,
      uptime: Date.now() - (this.metrics.lastHeartbeat || Date.now())
    };
  }

  /**
   * Cleanup and disconnect
   */
  async disconnect() {
    try {
      this.logger.info('Disconnecting Alpaca HFT Service', {
        correlationId: this.correlationId
      });

      if (this.websocket) {
        this.websocket.disconnect();
      }

      this.connected = false;
      this.subscriptions.clear();

      return { success: true };

    } catch (error) {
      this.logger.error('Error disconnecting', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      return { success: false, error: error.message };
    }
  }
}

module.exports = AlpacaHFTService;