// Alpaca WebSocket Service - HFT-ready real-time data service
// Super user-friendly and flexible subscription management

class EventEmitter {
  constructor() {
    this.events = {};
  }

  on(event, listener) {
    if (!this.events[event]) {
      this.events[event] = [];
    }
    this.events[event].push(listener);
    return this;
  }

  off(event, listener) {
    if (!this.events[event]) return this;
    const index = this.events[event].indexOf(listener);
    if (index > -1) {
      this.events[event].splice(index, 1);
    }
    return this;
  }

  emit(event, ...args) {
    if (!this.events[event]) return false;
    this.events[event].forEach(listener => {
      listener.apply(this, args);
    });
    return true;
  }

  removeAllListeners(event) {
    if (event) {
      delete this.events[event];
    } else {
      this.events = {};
    }
    return this;
  }
}

class AlpacaWebSocketService extends EventEmitter {
  constructor() {
    super();
    
    // Connection state
    this.ws = null;
    this.connected = false;
    this.connecting = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
    
    // Configuration
    this.config = {
      wsUrl: 'wss://stream.data.alpaca.markets/v2/iex', // Alpaca IEX data feed
      heartbeatInterval: 30000,
      connectionTimeout: 10000,
      maxReconnectDelay: 30000
    };
    
    // Alpaca credentials (will be fetched from backend)
    this.credentials = null;
    
    // Data management
    this.subscriptions = new Map(); // subscriptionId -> subscription details
    this.dataCache = new Map(); // symbol:dataType -> latest data
    this.availableFeeds = null;
    
    // Performance tracking
    this.metrics = {
      messagesReceived: 0,
      messagesDropped: 0,
      avgLatency: 0,
      connectionUptime: 0,
      lastLatency: 0,
      connectionStartTime: null,
      quotesReceived: 0,
      tradesReceived: 0,
      barsReceived: 0,
      newsReceived: 0
    };
    
    // Auto-connect if configured
    if (process.env.REACT_APP_AUTO_CONNECT_ALPACA !== 'false') {
      this.connect();
    }
  }

  // Connection Management
  async connect(userId = null) {
    if (this.connecting || this.connected) return;

    this.connecting = true;
    this.emit('connecting');

    try {
      const wsUrl = userId ? 
        `${this.config.wsUrl}?userId=${encodeURIComponent(userId)}` : 
        this.config.wsUrl;
      
      this.ws = new WebSocket(wsUrl);
      
      const timeout = setTimeout(() => {
        if (this.ws && this.ws.readyState === WebSocket.CONNECTING) {
          this.ws.close();
          this.handleConnectionError(new Error('Connection timeout'));
        }
      }, this.config.connectionTimeout);

      this.ws.onopen = () => {
        clearTimeout(timeout);
        this.handleConnectionOpen();
      };

      this.ws.onmessage = (event) => {
        this.handleMessage(event);
      };

      this.ws.onerror = (error) => {
        clearTimeout(timeout);
        this.handleConnectionError(error);
      };

      this.ws.onclose = (event) => {
        clearTimeout(timeout);
        this.handleConnectionClose(event);
      };

    } catch (error) {
      this.connecting = false;
      this.handleConnectionError(error);
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
    }
    this.stopHeartbeat();
    this.connected = false;
    this.connecting = false;
    this.reconnectAttempts = 0;
  }

  // Message Handling
  handleConnectionOpen() {
    this.connecting = false;
    this.connected = true;
    this.reconnectAttempts = 0;
    this.reconnectDelay = 1000;
    this.metrics.connectionStartTime = Date.now();
    
    this.emit('connected');
    this.startHeartbeat();
    this.loadAvailableFeeds();
    
    console.log('🟢 Connected to Alpaca WebSocket service');
  }

  handleConnectionClose(event) {
    this.connected = false;
    this.connecting = false;
    this.stopHeartbeat();
    
    this.emit('disconnected', event);
    
    if (this.metrics.connectionStartTime) {
      this.metrics.connectionUptime = Date.now() - this.metrics.connectionStartTime;
    }
    
    if (event.code !== 1000) {
      this.scheduleReconnect();
    }
    
    console.log('🔴 Disconnected from Alpaca WebSocket service');
  }

  handleConnectionError(error) {
    this.connecting = false;
    this.connected = false;
    this.emit('error', error);
    this.scheduleReconnect();
    console.error('❌ Alpaca WebSocket error:', error);
  }

  handleMessage(event) {
    const receiveTime = Date.now();
    this.metrics.messagesReceived++;
    
    try {
      const data = JSON.parse(event.data);
      
      // Calculate latency
      if (data.timestamp) {
        const latency = receiveTime - (data.timestamp * 1000);
        this.metrics.lastLatency = latency;
        this.updateAverageLatency(latency);
      }
      
      // Route message based on type
      switch (data.action || data.type) {
        case 'market_data':
          this.handleMarketData(data);
          break;
        case 'subscribed':
          this.handleSubscriptionConfirm(data);
          break;
        case 'unsubscribed':
          this.handleUnsubscriptionConfirm(data);
          break;
        case 'subscriptions_list':
          this.handleSubscriptionsList(data);
          break;
        case 'available_feeds':
          this.handleAvailableFeeds(data);
          break;
        case 'pong':
          this.handlePong(data);
          break;
        case 'error':
          this.handleServerError(data);
          break;
        default:
          console.warn('Unknown message type:', data);
      }
      
    } catch (error) {
      console.error('Failed to parse Alpaca WebSocket message:', error);
      this.metrics.messagesDropped++;
    }
  }

  handleMarketData(data) {
    const { symbol, dataType, data: marketData } = data;
    
    // Update cache
    const cacheKey = `${symbol}:${dataType}`;
    this.dataCache.set(cacheKey, {
      ...marketData,
      receivedAt: Date.now()
    });
    
    // Update metrics
    switch (dataType) {
      case 'quotes':
        this.metrics.quotesReceived++;
        break;
      case 'trades':
        this.metrics.tradesReceived++;
        break;
      case 'bars':
        this.metrics.barsReceived++;
        break;
      case 'news':
        this.metrics.newsReceived++;
        break;
    }
    
    // Emit events
    this.emit('marketData', { symbol, dataType, data: marketData });
    this.emit(`marketData:${dataType}`, { symbol, data: marketData });
    this.emit(`marketData:${symbol}`, { dataType, data: marketData });
    this.emit(`marketData:${dataType}:${symbol}`, marketData);
  }

  handleSubscriptionConfirm(data) {
    const { subscriptionId, dataType, symbols, frequency } = data;
    
    if (subscriptionId) {
      this.subscriptions.set(subscriptionId, {
        id: subscriptionId,
        dataType,
        symbols,
        frequency,
        subscribedAt: Date.now()
      });
    }
    
    this.emit('subscribed', data);
    console.log(`✅ Subscribed to ${dataType} for ${symbols?.join(', ')}`);
  }

  handleUnsubscriptionConfirm(data) {
    const { subscriptionId } = data;
    
    if (subscriptionId) {
      this.subscriptions.delete(subscriptionId);
    }
    
    this.emit('unsubscribed', data);
    console.log(`🔄 Unsubscribed from ${subscriptionId}`);
  }

  handleSubscriptionsList(data) {
    const { subscriptions } = data;
    
    // Update local subscriptions map
    this.subscriptions.clear();
    subscriptions.forEach(sub => {
      this.subscriptions.set(sub.subscriptionId, sub);
    });
    
    this.emit('subscriptionsList', subscriptions);
  }

  handleAvailableFeeds(data) {
    this.availableFeeds = data.feeds;
    this.emit('availableFeeds', data.feeds);
  }

  handlePong(data) {
    this.emit('pong', data);
  }

  handleServerError(data) {
    console.error('Alpaca server error:', data);
    this.emit('serverError', data);
  }

  // Subscription Management - Super User Friendly
  
  /**
   * Subscribe to real-time quotes
   * @param {string|Array} symbols - Stock symbols (e.g., 'AAPL' or ['AAPL', 'TSLA'])
   * @returns {Promise} - Subscription promise
   */
  subscribeToQuotes(symbols) {
    return this.subscribe(symbols, 'quotes');
  }

  /**
   * Subscribe to live trades
   * @param {string|Array} symbols - Stock symbols
   * @returns {Promise} - Subscription promise
   */
  subscribeToTrades(symbols) {
    return this.subscribe(symbols, 'trades');
  }

  /**
   * Subscribe to OHLCV bars
   * @param {string|Array} symbols - Stock symbols
   * @param {string} frequency - Bar frequency ('1Min', '5Min', '15Min', '1Hour', '1Day')
   * @returns {Promise} - Subscription promise
   */
  subscribeToBars(symbols, frequency = '1Min') {
    return this.subscribe(symbols, 'bars', frequency);
  }

  /**
   * Subscribe to real-time news
   * @param {string|Array} symbols - Stock symbols
   * @returns {Promise} - Subscription promise
   */
  subscribeToNews(symbols) {
    return this.subscribe(symbols, 'news');
  }

  /**
   * Subscribe to cryptocurrency data
   * @param {string|Array} symbols - Crypto symbols (e.g., 'BTCUSD', 'ETHUSD')
   * @returns {Promise} - Subscription promise
   */
  subscribeToCrypto(symbols) {
    return this.subscribe(symbols, 'crypto');
  }

  /**
   * Generic subscription method
   * @param {string|Array} symbols - Symbols to subscribe to
   * @param {string} dataType - Data type ('quotes', 'trades', 'bars', 'news', 'crypto')
   * @param {string} frequency - Frequency for bars
   * @returns {Promise} - Subscription promise
   */
  subscribe(symbols, dataType = 'quotes', frequency = '1Min') {
    if (!Array.isArray(symbols)) {
      symbols = [symbols];
    }
    
    const message = {
      action: 'subscribe',
      symbols: symbols.map(s => s.toUpperCase()),
      dataType,
      frequency
    };
    
    return this.sendMessage(message);
  }

  /**
   * Unsubscribe from specific subscription
   * @param {string} subscriptionId - Subscription ID to unsubscribe from
   * @returns {Promise} - Unsubscription promise
   */
  unsubscribe(subscriptionId) {
    const message = {
      action: 'unsubscribe',
      subscriptionId
    };
    
    return this.sendMessage(message);
  }

  /**
   * Unsubscribe from all subscriptions
   * @returns {Promise} - Unsubscription promise
   */
  unsubscribeAll() {
    const message = {
      action: 'unsubscribe'
    };
    
    return this.sendMessage(message);
  }

  /**
   * Get list of current subscriptions
   * @returns {Promise} - Promise that resolves with subscriptions list
   */
  getSubscriptions() {
    const message = {
      action: 'list_subscriptions'
    };
    
    return this.sendMessage(message);
  }

  /**
   * Get available data feeds
   * @returns {Promise} - Promise that resolves with available feeds
   */
  getAvailableFeeds() {
    const message = {
      action: 'get_available_feeds'
    };
    
    return this.sendMessage(message);
  }

  // Data Access Methods
  
  /**
   * Get latest quote for a symbol
   * @param {string} symbol - Stock symbol
   * @returns {Object|null} - Latest quote data
   */
  getLatestQuote(symbol) {
    return this.dataCache.get(`${symbol.toUpperCase()}:quotes`);
  }

  /**
   * Get latest trade for a symbol
   * @param {string} symbol - Stock symbol
   * @returns {Object|null} - Latest trade data
   */
  getLatestTrade(symbol) {
    return this.dataCache.get(`${symbol.toUpperCase()}:trades`);
  }

  /**
   * Get latest bar for a symbol
   * @param {string} symbol - Stock symbol
   * @returns {Object|null} - Latest bar data
   */
  getLatestBar(symbol) {
    return this.dataCache.get(`${symbol.toUpperCase()}:bars`);
  }

  /**
   * Get all cached data for a symbol
   * @param {string} symbol - Stock symbol
   * @returns {Object} - All cached data types for the symbol
   */
  getSymbolData(symbol) {
    const symbolUpper = symbol.toUpperCase();
    const result = {};
    
    for (const [key, value] of this.dataCache.entries()) {
      if (key.startsWith(`${symbolUpper}:`)) {
        const dataType = key.split(':')[1];
        result[dataType] = value;
      }
    }
    
    return result;
  }

  /**
   * Get all cached market data
   * @returns {Object} - All cached data organized by symbol and type
   */
  getAllMarketData() {
    const result = {};
    
    for (const [key, value] of this.dataCache.entries()) {
      const [symbol, dataType] = key.split(':');
      if (!result[symbol]) {
        result[symbol] = {};
      }
      result[symbol][dataType] = value;
    }
    
    return result;
  }

  /**
   * Check if data is stale
   * @param {string} symbol - Stock symbol
   * @param {string} dataType - Data type
   * @param {number} maxAge - Max age in milliseconds (default: 60s)
   * @returns {boolean} - True if data is stale
   */
  isDataStale(symbol, dataType, maxAge = 60000) {
    const data = this.dataCache.get(`${symbol.toUpperCase()}:${dataType}`);
    if (!data || !data.receivedAt) return true;
    
    return (Date.now() - data.receivedAt) > maxAge;
  }

  // Message Sending
  sendMessage(message) {
    return new Promise((resolve, reject) => {
      if (!this.connected) {
        reject(new Error('Not connected to Alpaca WebSocket'));
        return;
      }

      try {
        this.ws.send(JSON.stringify(message));
        resolve();
      } catch (error) {
        reject(error);
      }
    });
  }

  // Heartbeat Management
  startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.connected) {
        this.sendMessage({
          action: 'ping',
          timestamp: Date.now()
        });
      }
    }, this.config.heartbeatInterval);
  }

  stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  // Auto-load available feeds on connection
  loadAvailableFeeds() {
    if (this.connected) {
      this.getAvailableFeeds();
    }
  }

  // Reconnection Logic
  scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      this.emit('maxReconnectAttemptsReached');
      return;
    }

    this.reconnectAttempts++;
    
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.config.maxReconnectDelay
    );
    
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    setTimeout(() => {
      this.connect();
    }, delay);
  }

  // Utility Methods
  updateAverageLatency(latency) {
    if (this.metrics.avgLatency === 0) {
      this.metrics.avgLatency = latency;
    } else {
      // Exponential moving average
      this.metrics.avgLatency = this.metrics.avgLatency * 0.9 + latency * 0.1;
    }
  }

  /**
   * Get connection status
   * @returns {string} - Connection status ('CONNECTING', 'CONNECTED', 'DISCONNECTED')
   */
  getConnectionStatus() {
    if (this.connected) return 'CONNECTED';
    if (this.connecting) return 'CONNECTING';
    return 'DISCONNECTED';
  }

  /**
   * Get performance metrics
   * @returns {Object} - Performance metrics
   */
  getMetrics() {
    return {
      ...this.metrics,
      connectionUptime: this.metrics.connectionStartTime ? 
        Date.now() - this.metrics.connectionStartTime : 0,
      subscriptionsCount: this.subscriptions.size,
      cachedSymbolsCount: new Set(Array.from(this.dataCache.keys()).map(k => k.split(':')[0])).size
    };
  }

  /**
   * Get active subscriptions
   * @returns {Array} - Array of active subscriptions
   */
  getActiveSubscriptions() {
    return Array.from(this.subscriptions.values());
  }

  /**
   * Clear all cached data
   */
  clearCache() {
    this.dataCache.clear();
  }

  /**
   * Health check
   * @returns {Object} - Health check information
   */
  healthCheck() {
    return {
      connected: this.connected,
      subscriptions: this.getActiveSubscriptions(),
      metrics: this.getMetrics(),
      availableFeeds: this.availableFeeds,
      cacheSize: this.dataCache.size
    };
  }
}

// Create singleton instance
const alpacaWebSocketService = new AlpacaWebSocketService();

export default alpacaWebSocketService;
export { AlpacaWebSocketService };