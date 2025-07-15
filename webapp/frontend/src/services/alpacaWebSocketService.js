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
    
    // Configuration - Use backend WebSocket proxy for authentication
    this.config = {
      wsUrl: this.getWebSocketUrl(), // Backend WebSocket proxy with authentication
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

  // Get HTTP API base URL for backend real-time data endpoints
  getApiBaseUrl() {
    const apiUrl = window.__CONFIG__?.API_URL || 
                   import.meta.env.VITE_API_URL;
    
    if (!apiUrl) {
      throw new Error('API URL not configured for WebSocket service');
    }
    
    return `${apiUrl}/api/websocket`;
  }

  // Connection Management (HTTP Polling instead of WebSocket)
  async connect(userId = null) {
    if (this.connecting || this.connected) return;

    this.connecting = true;
    this.emit('connecting');

    try {
      // Get authentication token from localStorage or context
      const authToken = localStorage.getItem('authToken') || sessionStorage.getItem('authToken');
      
      if (!authToken) {
        throw new Error('No authentication token available');
      }

      // Test connection to backend
      const apiBase = this.getApiBaseUrl();
      const response = await fetch(`${apiBase}/health`, {
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`Backend connection failed: ${response.status}`);
      }

      // Store auth token for future requests
      this.authToken = authToken;
      this.apiBase = apiBase;
      
      this.handleConnectionOpen();

    } catch (error) {
      this.connecting = false;
      this.handleConnectionError(error);
    }
  }

  disconnect() {
    this.stopPolling();
    this.stopHeartbeat();
    this.connected = false;
    this.connecting = false;
    this.reconnectAttempts = 0;
    this.authToken = null;
    this.apiBase = null;
  }

  // Connection Handling
  handleConnectionOpen() {
    this.connecting = false;
    this.connected = true;
    this.reconnectAttempts = 0;
    this.reconnectDelay = 1000;
    this.metrics.connectionStartTime = Date.now();
    
    this.emit('connected');
    this.startHeartbeat();
    this.startPolling(); // Start HTTP polling instead of WebSocket
    this.loadAvailableFeeds();
    
    console.log('🟢 Connected to Alpaca HTTP real-time service');
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
  async subscribe(symbols, dataType = 'quotes', frequency = '1Min') {
    if (!Array.isArray(symbols)) {
      symbols = [symbols];
    }
    
    try {
      const result = await this.sendRequest('/subscribe', {
        method: 'POST',
        body: JSON.stringify({
          symbols: symbols.map(s => s.toUpperCase()),
          dataTypes: [dataType],
          frequency
        })
      });

      if (result.success) {
        // Store subscription locally
        const subscriptionId = `sub_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        this.subscriptions.set(subscriptionId, {
          id: subscriptionId,
          symbols: symbols.map(s => s.toUpperCase()),
          dataType,
          frequency,
          subscribedAt: Date.now()
        });

        // Restart polling with new subscriptions
        this.startPolling();

        this.emit('subscribed', {
          subscriptionId,
          symbols: symbols.map(s => s.toUpperCase()),
          dataType,
          frequency
        });

        console.log(`✅ Subscribed to ${dataType} for ${symbols.join(', ')}`);
        return subscriptionId;
      } else {
        throw new Error(result.error || 'Subscription failed');
      }
    } catch (error) {
      console.error('Subscription error:', error);
      throw error;
    }
  }

  /**
   * Unsubscribe from specific subscription
   * @param {string} subscriptionId - Subscription ID to unsubscribe from
   * @returns {Promise} - Unsubscription promise
   */
  async unsubscribe(subscriptionId) {
    try {
      const subscription = this.subscriptions.get(subscriptionId);
      if (!subscription) {
        console.warn(`Subscription ${subscriptionId} not found`);
        return;
      }

      const result = await this.sendRequest('/subscribe', {
        method: 'DELETE',
        body: JSON.stringify({
          symbols: subscription.symbols
        })
      });

      // Remove from local subscriptions
      this.subscriptions.delete(subscriptionId);

      // Restart polling with remaining subscriptions
      if (this.subscriptions.size > 0) {
        this.startPolling();
      } else {
        this.stopPolling();
      }

      this.emit('unsubscribed', { subscriptionId });
      console.log(`🔄 Unsubscribed from ${subscriptionId}`);

    } catch (error) {
      console.error('Unsubscribe error:', error);
      throw error;
    }
  }

  /**
   * Unsubscribe from all subscriptions
   * @returns {Promise} - Unsubscription promise
   */
  async unsubscribeAll() {
    try {
      const result = await this.sendRequest('/subscribe', {
        method: 'DELETE',
        body: JSON.stringify({})
      });

      // Clear all local subscriptions
      this.subscriptions.clear();
      this.stopPolling();

      this.emit('unsubscribed', { subscriptionId: 'all' });
      console.log(`🔄 Unsubscribed from all subscriptions`);

    } catch (error) {
      console.error('Unsubscribe all error:', error);
      throw error;
    }
  }

  /**
   * Get list of current subscriptions
   * @returns {Promise} - Promise that resolves with subscriptions list
   */
  async getSubscriptions() {
    try {
      const result = await this.sendRequest('/subscriptions');
      return result.data || [];
    } catch (error) {
      console.error('❌ Get subscriptions error:', error);
      throw new Error('Unable to retrieve subscriptions - WebSocket service error');
    }
  }

  /**
   * Get available data feeds
   * @returns {Promise} - Promise that resolves with available feeds
   */
  async getAvailableFeeds() {
    try {
      const result = await this.sendRequest('/status');
      return result.data?.availableFeeds || [];
    } catch (error) {
      console.error('❌ Get available feeds error:', error);
      throw new Error('Unable to retrieve available feeds - WebSocket service error');
    }
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

  // HTTP Polling Management
  startPolling() {
    this.stopPolling();
    
    // Only start polling if we have subscriptions
    if (this.subscriptions.size === 0) {
      return;
    }

    this.pollingTimer = setInterval(async () => {
      if (this.connected && this.subscriptions.size > 0) {
        await this.pollMarketData();
      }
    }, this.config.heartbeatInterval || 5000); // Poll every 5 seconds
  }

  stopPolling() {
    if (this.pollingTimer) {
      clearInterval(this.pollingTimer);
      this.pollingTimer = null;
    }
  }

  async pollMarketData() {
    if (!this.connected || !this.authToken || this.subscriptions.size === 0) {
      return;
    }

    try {
      // Get all symbols we're subscribed to
      const allSymbols = Array.from(this.subscriptions.values())
        .flatMap(sub => sub.symbols)
        .filter((symbol, index, array) => array.indexOf(symbol) === index); // Remove duplicates

      if (allSymbols.length === 0) return;

      // Poll the stream endpoint
      const response = await fetch(`${this.apiBase}/stream/${allSymbols.join(',')}`, {
        headers: {
          'Authorization': `Bearer ${this.authToken}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`Polling failed: ${response.status}`);
      }

      const result = await response.json();
      
      if (result.success && result.data) {
        // Process market data similar to WebSocket messages
        Object.entries(result.data.data).forEach(([symbol, marketData]) => {
          if (!marketData.error) {
            this.handleMarketDataUpdate(symbol, 'quotes', marketData);
          }
        });
        
        this.metrics.messagesReceived++;
      }

    } catch (error) {
      console.error('Polling error:', error);
      this.metrics.messagesDropped++;
    }
  }

  handleMarketDataUpdate(symbol, dataType, marketData) {
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
    }
    
    // Emit events
    this.emit('marketData', { symbol, dataType, data: marketData });
    this.emit(`marketData:${dataType}`, { symbol, data: marketData });
    this.emit(`marketData:${symbol}`, { dataType, data: marketData });
    this.emit(`marketData:${dataType}:${symbol}`, marketData);
  }

  // HTTP Request Helper
  async sendRequest(endpoint, options = {}) {
    if (!this.connected || !this.authToken) {
      throw new Error('Not connected to Alpaca service');
    }

    const response = await fetch(`${this.apiBase}${endpoint}`, {
      headers: {
        'Authorization': `Bearer ${this.authToken}`,
        'Content-Type': 'application/json',
        ...options.headers
      },
      ...options
    });

    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`);
    }

    return await response.json();
  }

  // Heartbeat Management (HTTP-based)
  startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(async () => {
      if (this.connected) {
        try {
          const result = await this.sendRequest('/health');
          this.emit('pong', { 
            timestamp: Date.now(),
            serverStatus: result.data 
          });
        } catch (error) {
          console.warn('Heartbeat failed:', error.message);
          this.emit('error', error);
        }
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
  async loadAvailableFeeds() {
    if (this.connected) {
      try {
        this.availableFeeds = await this.getAvailableFeeds();
        this.emit('availableFeeds', this.availableFeeds);
      } catch (error) {
        console.warn('Failed to load available feeds:', error);
      }
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