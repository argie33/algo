// Enhanced Live Data Service for HFT-ready WebSocket connections
// Integrates with AWS API Gateway WebSocket API

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

class LiveDataService extends EventEmitter {
  constructor() {
    super();
    
    // Connection state
    this.ws = null;
    this.connected = false;
    this.connecting = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
    this.maxReconnectDelay = 30000;
    
    // Configuration
    this.config = {
      wsUrl: process.env.REACT_APP_WS_URL || 'wss://your-websocket-api.execute-api.us-east-1.amazonaws.com/dev',
      heartbeatInterval: 30000, // 30 seconds
      connectionTimeout: 10000,  // 10 seconds
      messageTimeout: 5000,      // 5 seconds
      maxRetries: 3
    };
    
    // Data management
    this.subscriptions = new Set();
    this.marketData = new Map();
    this.messageQueue = [];
    this.pendingMessages = new Map();
    this.lastActivity = Date.now();
    
    // Performance metrics
    this.metrics = {
      messagesReceived: 0,
      messagesDropped: 0,
      avgLatency: 0,
      connectionUptime: 0,
      lastLatency: 0,
      connectionStartTime: null
    };
    
    // Auto-connect if configured
    if (process.env.REACT_APP_AUTO_CONNECT_WS !== 'false') {
      this.connect();
    }
  }

  // Connection Management
  async connect(userId = 'anonymous') {
    if (this.connecting || this.connected) {
      return;
    }

    this.connecting = true;
    this.emit('connecting');

    try {
      const wsUrl = `${this.config.wsUrl}?userId=${encodeURIComponent(userId)}`;
      
      this.ws = new WebSocket(wsUrl);
      this.ws.binaryType = 'arraybuffer';
      
      // Connection timeout
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
    this.lastActivity = Date.now();
    
    this.emit('connected');
    this.startHeartbeat();
    this.processMessageQueue();
    
    console.log('🟢 WebSocket connected to live data service');
  }

  handleConnectionClose(event) {
    this.connected = false;
    this.connecting = false;
    this.stopHeartbeat();
    
    this.emit('disconnected', event);
    
    // Calculate uptime
    if (this.metrics.connectionStartTime) {
      this.metrics.connectionUptime = Date.now() - this.metrics.connectionStartTime;
    }
    
    // Auto-reconnect on unexpected close
    if (event.code !== 1000) {
      this.scheduleReconnect();
    }
    
    console.log('🔴 WebSocket disconnected from live data service');
  }

  handleConnectionError(error) {
    this.connecting = false;
    this.connected = false;
    this.emit('error', error);
    this.scheduleReconnect();
    console.error('❌ WebSocket error:', error);
  }

  handleMessage(event) {
    const receiveTime = Date.now();
    this.lastActivity = receiveTime;
    this.metrics.messagesReceived++;
    
    try {
      const data = JSON.parse(event.data);
      
      // Calculate latency if timestamp is provided
      if (data.timestamp) {
        const latency = receiveTime - (data.timestamp * 1000);
        this.metrics.lastLatency = latency;
        this.updateAverageLatency(latency);
      }
      
      // Route message based on type
      switch (data.type) {
        case 'market_data':
          this.handleMarketData(data);
          break;
        case 'portfolio_update':
          this.handlePortfolioUpdate(data);
          break;
        case 'portfolio_holdings':
          this.handlePortfolioHoldings(data);
          break;
        case 'position_update':
          this.handlePositionUpdate(data);
          break;
        case 'pong':
          this.handlePong(data);
          break;
        case 'error':
          this.handleServerError(data);
          break;
        case 'subscribed':
          this.handleSubscriptionConfirm(data);
          break;
        default:
          console.warn('Unknown message type:', data.type);
      }
      
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error);
      this.metrics.messagesDropped++;
    }
  }

  handleMarketData(data) {
    const { symbol, data: marketData } = data;
    
    // Update local cache
    this.marketData.set(symbol, {
      ...marketData,
      receivedAt: Date.now()
    });
    
    // Emit to subscribers
    this.emit('marketData', { symbol, data: marketData });
    this.emit(`marketData:${symbol}`, marketData);
  }

  handlePong(data) {
    this.emit('pong', data);
  }

  handleServerError(data) {
    console.error('Server error:', data);
    this.emit('serverError', data);
  }

  handleSubscriptionConfirm(data) {
    this.emit('subscribed', data);
  }

  handlePortfolioUpdate(data) {
    const { userId, apiKeyId, portfolio } = data;
    console.log('📊 Portfolio update received:', portfolio);
    
    // Emit to specific portfolio subscription
    this.emit(`portfolio:${userId}:${apiKeyId}`, {
      type: 'portfolio_update',
      data: portfolio
    });
    
    // Emit to general portfolio listeners
    this.emit('portfolioUpdate', { userId, apiKeyId, portfolio });
  }

  handlePortfolioHoldings(data) {
    const { userId, apiKeyId, holdings } = data;
    console.log('📊 Portfolio holdings received:', holdings);
    
    // Emit to specific portfolio subscription
    this.emit(`portfolio:${userId}:${apiKeyId}`, {
      type: 'holdings_update',
      data: holdings
    });
    
    // Emit to general portfolio listeners
    this.emit('portfolioHoldings', { userId, apiKeyId, holdings });
  }

  handlePositionUpdate(data) {
    const { userId, apiKeyId, position } = data;
    console.log('📊 Position update received:', position);
    
    // Emit to specific portfolio subscription
    this.emit(`portfolio:${userId}:${apiKeyId}`, {
      type: 'position_update',
      data: position
    });
    
    // Emit to general portfolio listeners
    this.emit('positionUpdate', { userId, apiKeyId, position });
  }

  // Subscription Management
  subscribe(symbols, channel = 'market_data') {
    if (!Array.isArray(symbols)) {
      symbols = [symbols];
    }
    
    symbols.forEach(symbol => this.subscriptions.add(symbol));
    
    const message = {
      action: 'subscribe',
      channel: channel,
      symbols: symbols
    };
    
    this.sendMessage(message);
    return this;
  }

  // Portfolio-specific subscription
  subscribeToPortfolio(userId, apiKeyId, callback) {
    const subscriptionKey = `portfolio:${userId}:${apiKeyId}`;
    
    if (this.subscriptions.has(subscriptionKey)) {
      console.log('📊 Already subscribed to portfolio live data');
      return this;
    }

    console.log('📊 Subscribing to portfolio live data...');
    
    // Add to subscriptions and set up callback
    this.subscriptions.add(subscriptionKey);
    this.on(`portfolio:${userId}:${apiKeyId}`, callback);
    
    const message = {
      action: 'subscribe',
      channel: 'portfolio',
      userId: userId,
      apiKeyId: apiKeyId,
      subscriptionKey: subscriptionKey
    };
    
    this.sendMessage(message);
    return this;
  }

  // Unsubscribe from portfolio
  unsubscribeFromPortfolio(userId, apiKeyId) {
    const subscriptionKey = `portfolio:${userId}:${apiKeyId}`;
    
    if (!this.subscriptions.has(subscriptionKey)) {
      console.log('📊 Not subscribed to portfolio live data');
      return this;
    }

    console.log('📊 Unsubscribing from portfolio live data...');
    
    // Remove from subscriptions and callbacks
    this.subscriptions.delete(subscriptionKey);
    this.removeAllListeners(`portfolio:${userId}:${apiKeyId}`);
    
    const message = {
      action: 'unsubscribe',
      channel: 'portfolio',
      userId: userId,
      apiKeyId: apiKeyId,
      subscriptionKey: subscriptionKey
    };
    
    this.sendMessage(message);
    return this;
  }

  unsubscribe(symbols, channel = 'market_data') {
    if (!Array.isArray(symbols)) {
      symbols = [symbols];
    }
    
    symbols.forEach(symbol => this.subscriptions.delete(symbol));
    
    const message = {
      action: 'unsubscribe',
      channel: channel,
      symbols: symbols
    };
    
    this.sendMessage(message);
    return this;
  }

  // Message Sending
  sendMessage(message) {
    if (!this.connected) {
      this.messageQueue.push(message);
      return;
    }

    try {
      this.ws.send(JSON.stringify(message));
    } catch (error) {
      console.error('Failed to send message:', error);
      this.messageQueue.push(message);
    }
  }

  processMessageQueue() {
    while (this.messageQueue.length > 0 && this.connected) {
      const message = this.messageQueue.shift();
      this.sendMessage(message);
    }
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

  // Reconnection Logic
  scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      this.emit('maxReconnectAttemptsReached');
      return;
    }

    this.reconnectAttempts++;
    
    // Exponential backoff
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.maxReconnectDelay
    );
    
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    setTimeout(() => {
      this.connect();
    }, delay);
  }

  // Data Access Methods
  getMarketData(symbol) {
    return this.marketData.get(symbol);
  }

  getAllMarketData() {
    return Object.fromEntries(this.marketData);
  }

  getLatestPrice(symbol) {
    const data = this.marketData.get(symbol);
    return data ? data.price : null;
  }

  isDataStale(symbol, maxAge = 60000) {
    const data = this.marketData.get(symbol);
    if (!data || !data.receivedAt) return true;
    
    return (Date.now() - data.receivedAt) > maxAge;
  }

  // Connection Status
  getConnectionStatus() {
    if (this.connected) return 'CONNECTED';
    if (this.connecting) return 'CONNECTING';
    return 'DISCONNECTED';
  }

  isConnected() {
    return this.connected;
  }

  // Performance Metrics
  getMetrics() {
    return {
      ...this.metrics,
      connectionUptime: this.metrics.connectionStartTime ? 
        Date.now() - this.metrics.connectionStartTime : 0,
      subscriptionsCount: this.subscriptions.size,
      cachedSymbols: this.marketData.size
    };
  }

  updateAverageLatency(latency) {
    if (this.metrics.avgLatency === 0) {
      this.metrics.avgLatency = latency;
    } else {
      // Exponential moving average
      this.metrics.avgLatency = this.metrics.avgLatency * 0.9 + latency * 0.1;
    }
  }

  // Utility Methods
  clearCache() {
    this.marketData.clear();
  }

  getSubscriptions() {
    return Array.from(this.subscriptions);
  }

  // Batch operations for performance
  subscribeBatch(symbols) {
    return this.subscribe(symbols);
  }

  unsubscribeBatch(symbols) {
    return this.unsubscribe(symbols);
  }

  // Health check
  healthCheck() {
    return {
      connected: this.connected,
      lastActivity: this.lastActivity,
      timeSinceLastActivity: Date.now() - this.lastActivity,
      metrics: this.getMetrics(),
      subscriptions: this.getSubscriptions()
    };
  }
}

// Create singleton instance
const liveDataService = new LiveDataService();

export default liveDataService;
export { LiveDataService };