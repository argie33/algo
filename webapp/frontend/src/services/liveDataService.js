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
    
    // Enhanced Configuration
    this.config = {
      wsUrl: import.meta.env.VITE_WS_URL || process.env.REACT_APP_WS_URL || null, // Support both Vite and React env vars
      heartbeatInterval: 30000, // 30 seconds
      connectionTimeout: 10000,  // 10 seconds
      messageTimeout: 5000,      // 5 seconds
      maxRetries: 3,
      connectionHealthInterval: 5000, // Check connection health every 5 seconds
      staleDataTimeout: 120000, // 2 minutes - consider data stale
      maxMessageQueueSize: 100, // Prevent memory issues
      enableAutoReconnect: true,
      enableConnectionHealthCheck: true,
      enableMetricsCollection: true
    };
    
    // Data management
    this.subscriptions = new Set();
    this.marketData = new Map();
    this.messageQueue = [];
    this.pendingMessages = new Map();
    this.lastActivity = Date.now();
    
    // Enhanced Performance metrics
    this.metrics = {
      messagesReceived: 0,
      messagesDropped: 0,
      avgLatency: 0,
      connectionUptime: 0,
      lastLatency: 0,
      connectionStartTime: null,
      reconnectCount: 0,
      errorCount: 0,
      messagesSent: 0,
      subscriptionCount: 0,
      lastPingTime: null,
      lastPongTime: null,
      connectionQuality: 'unknown' // 'excellent', 'good', 'fair', 'poor'
    };
    
    // Connection health monitoring
    this.connectionHealthTimer = null;
    this.connectionQualityHistory = [];
    
    // Auto-connect if configured and WebSocket URL is available
    if (process.env.REACT_APP_AUTO_CONNECT_WS !== 'false' && this.config.wsUrl) {
      this.connect();
    }
    
    // Start connection health monitoring
    if (this.config.enableConnectionHealthCheck) {
      this.startConnectionHealthMonitoring();
    }
  }

  // Enhanced Connection Management with JWT Authentication
  async connect(userId = null) {
    if (this.connecting || this.connected) {
      console.log('🔄 Connection already in progress or established');
      return;
    }

    // Check if WebSocket URL is configured
    if (!this.config.wsUrl) {
      console.warn('⚠️ WebSocket URL not configured. Live data service disabled.');
      this.emit('configurationError', 'WebSocket URL not configured');
      return;
    }

    // Get authentication token
    const token = localStorage.getItem('accessToken') || localStorage.getItem('authToken');
    if (!token) {
      console.warn('⚠️ No authentication token found. WebSocket requires authentication.');
      this.emit('authenticationError', 'Authentication token required for WebSocket connection');
      return;
    }

    // Get userId from token or use provided value
    let actualUserId = userId;
    if (!actualUserId) {
      try {
        // Decode JWT to get userId (basic decode, not verification)
        const tokenPayload = JSON.parse(atob(token.split('.')[1]));
        actualUserId = tokenPayload.sub || tokenPayload.userId || tokenPayload.user_id || 'unknown';
      } catch (error) {
        console.warn('⚠️ Could not decode token for userId:', error.message);
        actualUserId = 'authenticated';
      }
    }

    console.log('🔄 Attempting to connect to WebSocket...', {
      url: this.config.wsUrl,
      userId: actualUserId,
      hasToken: !!token,
      attempt: this.reconnectAttempts + 1
    });

    this.connecting = true;
    this.emit('connecting', { attempt: this.reconnectAttempts + 1 });

    try {
      // Include authentication token in WebSocket connection
      const wsUrl = `${this.config.wsUrl}?userId=${encodeURIComponent(actualUserId)}&token=${encodeURIComponent(token)}`;
      
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
      this.lastError = error;
      this.handleConnectionError(error);
    }
  }

  disconnect() {
    console.log('🔴 Disconnecting WebSocket...');
    
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
    }
    
    this.stopHeartbeat();
    this.connected = false;
    this.connecting = false;
    this.reconnectAttempts = 0;
    
    // Clear reconnect timer
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    
    // Clear message queue
    this.messageQueue = [];
    
    this.emit('disconnected', {
      reason: 'client_disconnect',
      timestamp: Date.now()
    });
  }

  // Message Handling
  handleConnectionOpen() {
    this.connecting = false;
    this.connected = true;
    this.reconnectAttempts = 0;
    this.reconnectDelay = 1000;
    this.metrics.connectionStartTime = Date.now();
    this.lastActivity = Date.now();
    this.metrics.reconnectCount = this.reconnectAttempts;
    this.metrics.connectionQuality = 'good';
    
    this.emit('connected', {
      reconnectAttempts: this.reconnectAttempts,
      connectionTime: Date.now(),
      queuedMessages: this.messageQueue.length
    });
    
    this.startHeartbeat();
    this.processMessageQueue();
    
    console.log('🟢 WebSocket connected to live data service', {
      reconnectAttempts: this.reconnectAttempts,
      queuedMessages: this.messageQueue.length,
      subscriptions: this.subscriptions.size
    });
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
    this.metrics.errorCount++;
    this.metrics.connectionQuality = 'poor';
    
    const errorDetails = {
      error: error,
      reconnectAttempts: this.reconnectAttempts,
      timestamp: Date.now(),
      wsUrl: this.config.wsUrl
    };
    
    this.emit('error', errorDetails);
    
    if (this.config.enableAutoReconnect) {
      this.scheduleReconnect();
    }
    
    console.error('❌ WebSocket error:', errorDetails);
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
    this.metrics.lastPongTime = Date.now();
    
    // Calculate ping latency
    if (this.metrics.lastPingTime) {
      const latency = this.metrics.lastPongTime - this.metrics.lastPingTime;
      this.metrics.lastLatency = latency;
      this.updateAverageLatency(latency);
      this.updateConnectionQuality(latency);
    }
    
    this.emit('pong', {
      ...data,
      latency: this.metrics.lastLatency,
      timestamp: this.metrics.lastPongTime
    });
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

  // Enhanced Message Sending
  sendMessage(message) {
    if (!this.connected) {
      if (this.messageQueue.length < this.config.maxMessageQueueSize) {
        this.messageQueue.push(message);
        console.log('📤 Message queued (not connected):', message.action);
      } else {
        console.warn('⚠️ Message queue full, dropping message:', message.action);
        this.metrics.messagesDropped++;
      }
      return;
    }

    try {
      const messageStr = JSON.stringify(message);
      this.ws.send(messageStr);
      this.metrics.messagesSent++;
      
      // Track ping messages for latency measurement
      if (message.action === 'ping') {
        this.metrics.lastPingTime = Date.now();
      }
      
      console.log('📤 Message sent:', message.action);
    } catch (error) {
      console.error('Failed to send message:', error);
      this.metrics.messagesDropped++;
      
      if (this.messageQueue.length < this.config.maxMessageQueueSize) {
        this.messageQueue.push(message);
      }
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

  // Enhanced Reconnection Logic
  scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('❌ Max reconnection attempts reached:', this.maxReconnectAttempts);
      this.emit('maxReconnectAttemptsReached', {
        attempts: this.reconnectAttempts,
        maxAttempts: this.maxReconnectAttempts,
        lastError: this.lastError
      });
      return;
    }

    this.reconnectAttempts++;
    
    // Exponential backoff with jitter
    const baseDelay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    const jitter = Math.random() * 1000; // Add up to 1s jitter
    const delay = Math.min(baseDelay + jitter, this.maxReconnectDelay);
    
    console.log(`🔄 Reconnecting in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    this.emit('reconnecting', {
      attempt: this.reconnectAttempts,
      maxAttempts: this.maxReconnectAttempts,
      delay: delay
    });
    
    this.reconnectTimer = setTimeout(() => {
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

  // Enhanced Performance Metrics
  getMetrics() {
    const now = Date.now();
    return {
      ...this.metrics,
      connectionUptime: this.metrics.connectionStartTime ? 
        now - this.metrics.connectionStartTime : 0,
      subscriptionsCount: this.subscriptions.size,
      cachedSymbols: this.marketData.size,
      messageQueueSize: this.messageQueue.length,
      timeSinceLastActivity: now - this.lastActivity,
      connectionQualityScore: this.getConnectionQualityScore(),
      isHealthy: this.isConnectionHealthy()
    };
  }
  
  getConnectionQualityScore() {
    const qualityMap = {
      'excellent': 100,
      'good': 80,
      'fair': 60,
      'poor': 40,
      'unknown': 0
    };
    
    return qualityMap[this.metrics.connectionQuality] || 0;
  }
  
  isConnectionHealthy() {
    const now = Date.now();
    const timeSinceLastActivity = now - this.lastActivity;
    
    return this.connected && 
           timeSinceLastActivity < this.config.staleDataTimeout &&
           this.metrics.connectionQuality !== 'poor';
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

  // Connection Health Monitoring
  startConnectionHealthMonitoring() {
    if (this.connectionHealthTimer) {
      clearInterval(this.connectionHealthTimer);
    }
    
    this.connectionHealthTimer = setInterval(() => {
      this.checkConnectionHealth();
    }, this.config.connectionHealthInterval);
  }
  
  stopConnectionHealthMonitoring() {
    if (this.connectionHealthTimer) {
      clearInterval(this.connectionHealthTimer);
      this.connectionHealthTimer = null;
    }
  }
  
  checkConnectionHealth() {
    const now = Date.now();
    const timeSinceLastActivity = now - this.lastActivity;
    
    // Check if connection is stale
    if (this.connected && timeSinceLastActivity > this.config.staleDataTimeout) {
      console.warn('⚠️ Connection appears stale, forcing reconnect');
      this.metrics.connectionQuality = 'poor';
      this.disconnect();
      if (this.config.enableAutoReconnect) {
        this.connect();
      }
    }
    
    // Update connection quality based on recent metrics
    this.updateConnectionQualityHistory();
    
    // Emit health status
    this.emit('healthUpdate', this.healthCheck());
  }
  
  updateConnectionQuality(latency) {
    let quality = 'excellent';
    
    if (latency > 1000) {
      quality = 'poor';
    } else if (latency > 500) {
      quality = 'fair';
    } else if (latency > 100) {
      quality = 'good';
    }
    
    this.metrics.connectionQuality = quality;
  }
  
  updateConnectionQualityHistory() {
    const now = Date.now();
    const qualityEntry = {
      timestamp: now,
      quality: this.metrics.connectionQuality,
      latency: this.metrics.lastLatency,
      connected: this.connected
    };
    
    this.connectionQualityHistory.push(qualityEntry);
    
    // Keep only last 10 minutes of history
    const tenMinutesAgo = now - (10 * 60 * 1000);
    this.connectionQualityHistory = this.connectionQualityHistory.filter(
      entry => entry.timestamp > tenMinutesAgo
    );
  }
  
  // Enhanced Health check
  healthCheck() {
    const now = Date.now();
    return {
      connected: this.connected,
      connecting: this.connecting,
      lastActivity: this.lastActivity,
      timeSinceLastActivity: now - this.lastActivity,
      metrics: this.getMetrics(),
      subscriptions: this.getSubscriptions(),
      connectionQuality: this.metrics.connectionQuality,
      qualityHistory: this.connectionQualityHistory.slice(-5), // Last 5 entries
      config: {
        wsUrl: this.config.wsUrl ? 'configured' : 'not configured',
        autoReconnect: this.config.enableAutoReconnect,
        healthCheck: this.config.enableConnectionHealthCheck
      }
    };
  }
  
  // Enhanced cleanup
  cleanup() {
    this.disconnect();
    this.stopHeartbeat();
    this.stopConnectionHealthMonitoring();
    this.removeAllListeners();
    this.clearCache();
    
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}

// Create singleton instance
const liveDataService = new LiveDataService();

// Add cleanup on page unload
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    liveDataService.cleanup();
  });
  
  // Add visibility change handler for connection management
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      console.log('🔄 Page hidden, pausing WebSocket heartbeat');
      liveDataService.stopHeartbeat();
    } else {
      console.log('🔄 Page visible, resuming WebSocket heartbeat');
      if (liveDataService.connected) {
        liveDataService.startHeartbeat();
      } else if (liveDataService.config.enableAutoReconnect) {
        liveDataService.connect();
      }
    }
  });
}

export default liveDataService;
export { LiveDataService };

// Enhanced error handling and debugging
if (process.env.NODE_ENV === 'development') {
  // Add development-only debugging
  liveDataService.on('error', (error) => {
    console.group('🔴 WebSocket Error Debug');
    console.error('Error details:', error);
    console.log('Connection state:', liveDataService.getConnectionStatus());
    console.log('Metrics:', liveDataService.getMetrics());
    console.log('Health:', liveDataService.healthCheck());
    console.groupEnd();
  });
  
  liveDataService.on('connected', (details) => {
    console.group('🟢 WebSocket Connected');
    console.log('Connection details:', details);
    console.log('Health:', liveDataService.healthCheck());
    console.groupEnd();
  });
  
  // Make service available globally for debugging
  window.liveDataService = liveDataService;
}