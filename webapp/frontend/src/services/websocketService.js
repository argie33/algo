import { EventTarget } from 'events';

class WebSocketService extends EventTarget {
  constructor() {
    super();
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
    this.isConnected = false;
    this.subscriptions = new Set();
    this.messageQueue = [];
    this.heartbeatInterval = null;
    this.connectionTimeout = null;
    
    // Configuration
    this.config = {
      url: process.env.REACT_APP_WS_URL || 'ws://localhost:8765',
      pingInterval: 30000, // 30 seconds
      connectionTimeout: 10000, // 10 seconds
      maxMessageSize: 1024 * 1024, // 1MB
    };
    
    // Data caches
    this.marketDataCache = new Map();
    this.optionsDataCache = new Map();
    this.lastUpdated = new Map();
    
    // Statistics
    this.stats = {
      messagesReceived: 0,
      messagesSent: 0,
      connectTime: null,
      disconnectTime: null,
      dataValidationErrors: 0,
      reconnectCount: 0
    };
  }

  /**
   * Connect to WebSocket server
   */
  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected');
      return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
      try {
        console.log(`Connecting to WebSocket: ${this.config.url}`);
        this.ws = new WebSocket(this.config.url);
        
        // Set connection timeout
        this.connectionTimeout = setTimeout(() => {
          if (this.ws.readyState === WebSocket.CONNECTING) {
            this.ws.close();
            reject(new Error('Connection timeout'));
          }
        }, this.config.connectionTimeout);

        this.ws.onopen = (event) => {
          clearTimeout(this.connectionTimeout);
          this.isConnected = true;
          this.reconnectAttempts = 0;
          this.stats.connectTime = new Date();
          this.stats.reconnectCount = this.reconnectAttempts;
          
          console.log('WebSocket connected successfully');
          this.emit('connected', event);
          
          // Process queued messages
          this.processMessageQueue();
          
          // Start heartbeat
          this.startHeartbeat();
          
          // Resubscribe to channels
          this.resubscribe();
          
          resolve();
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event);
        };

        this.ws.onclose = (event) => {
          this.handleDisconnect(event);
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          this.emit('error', error);
          
          if (this.ws.readyState === WebSocket.CONNECTING) {
            clearTimeout(this.connectionTimeout);
            reject(error);
          }
        };

      } catch (error) {
        console.error('Failed to create WebSocket connection:', error);
        reject(error);
      }
    });
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect() {
    if (this.ws) {
      this.isConnected = false;
      this.stopHeartbeat();
      clearTimeout(this.connectionTimeout);
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
      this.stats.disconnectTime = new Date();
      this.emit('disconnected');
    }
  }

  /**
   * Handle incoming messages
   */
  handleMessage(event) {
    try {
      this.stats.messagesReceived++;
      const data = JSON.parse(event.data);
      
      // Validate message structure
      if (!this.validateMessage(data)) {
        this.stats.dataValidationErrors++;
        console.warn('Invalid message received:', data);
        return;
      }

      switch (data.type) {
        case 'market_data':
          this.handleMarketData(data.data);
          break;
          
        case 'options_data':
          this.handleOptionsData(data.symbol, data.data);
          break;
          
        case 'subscribed':
          console.log(`Subscribed to ${data.channel}:`, data.symbols);
          this.emit('subscribed', data);
          break;
          
        case 'unsubscribed':
          console.log(`Unsubscribed from ${data.channel}`);
          this.emit('unsubscribed', data);
          break;
          
        case 'pong':
          // Heartbeat response
          break;
          
        case 'error':
          console.error('Server error:', data.message);
          this.emit('error', new Error(data.message));
          break;
          
        default:
          console.warn('Unknown message type:', data.type);
      }
      
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
      this.stats.dataValidationErrors++;
    }
  }

  /**
   * Handle market data updates
   */
  handleMarketData(data) {
    if (!data || !data.symbol) return;
    
    // Cache the data
    this.marketDataCache.set(data.symbol, {
      ...data,
      receivedAt: Date.now()
    });
    
    this.lastUpdated.set(`market_${data.symbol}`, Date.now());
    
    // Emit to listeners
    this.emit('marketData', data);
    this.emit(`marketData_${data.symbol}`, data);
  }

  /**
   * Handle options data updates
   */
  handleOptionsData(symbol, data) {
    if (!symbol || !Array.isArray(data)) return;
    
    // Process and cache options chain
    const processedOptions = data.map(option => ({
      ...option,
      receivedAt: Date.now()
    }));
    
    this.optionsDataCache.set(symbol, processedOptions);
    this.lastUpdated.set(`options_${symbol}`, Date.now());
    
    // Emit to listeners
    this.emit('optionsData', { symbol, data: processedOptions });
    this.emit(`optionsData_${symbol}`, processedOptions);
  }

  /**
   * Handle disconnection
   */
  handleDisconnect(event) {
    console.log('WebSocket disconnected:', event.code, event.reason);
    
    this.isConnected = false;
    this.stopHeartbeat();
    this.stats.disconnectTime = new Date();
    
    this.emit('disconnected', event);
    
    // Attempt reconnection if not a normal closure
    if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
      this.scheduleReconnect();
    }
  }

  /**
   * Schedule reconnection attempt
   */
  scheduleReconnect() {
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts);
    console.log(`Scheduling reconnect in ${delay}ms (attempt ${this.reconnectAttempts + 1})`);
    
    setTimeout(() => {
      this.reconnectAttempts++;
      this.connect().catch(error => {
        console.error('Reconnection failed:', error);
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.scheduleReconnect();
        } else {
          console.error('Max reconnection attempts reached');
          this.emit('maxReconnectAttemptsReached');
        }
      });
    }, delay);
  }

  /**
   * Send message to server
   */
  sendMessage(message) {
    if (!this.isConnected || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
      // Queue message for later
      this.messageQueue.push(message);
      return false;
    }

    try {
      const messageStr = JSON.stringify(message);
      
      // Check message size
      if (messageStr.length > this.config.maxMessageSize) {
        console.error('Message too large:', messageStr.length);
        return false;
      }
      
      this.ws.send(messageStr);
      this.stats.messagesSent++;
      return true;
      
    } catch (error) {
      console.error('Error sending message:', error);
      return false;
    }
  }

  /**
   * Process queued messages
   */
  processMessageQueue() {
    while (this.messageQueue.length > 0) {
      const message = this.messageQueue.shift();
      if (!this.sendMessage(message)) {
        // Put it back if send failed
        this.messageQueue.unshift(message);
        break;
      }
    }
  }

  /**
   * Subscribe to market data for symbols
   */
  subscribeMarketData(symbols) {
    const subscription = {
      type: 'subscribe',
      channel: 'market_data',
      symbols: Array.isArray(symbols) ? symbols : [symbols]
    };
    
    this.subscriptions.add(JSON.stringify(subscription));
    return this.sendMessage(subscription);
  }

  /**
   * Subscribe to options data for a symbol
   */
  subscribeOptionsData(symbol) {
    const subscription = {
      type: 'subscribe',
      channel: 'options_data',
      symbol: symbol
    };
    
    this.subscriptions.add(JSON.stringify(subscription));
    return this.sendMessage(subscription);
  }

  /**
   * Unsubscribe from a channel
   */
  unsubscribe(channel, symbol = null) {
    const unsubscription = {
      type: 'unsubscribe',
      channel: channel,
      ...(symbol && { symbol })
    };
    
    // Remove from subscriptions
    const subKey = JSON.stringify({
      type: 'subscribe',
      channel: channel,
      ...(symbol && { symbol })
    });
    this.subscriptions.delete(subKey);
    
    return this.sendMessage(unsubscription);
  }

  /**
   * Resubscribe to all channels after reconnection
   */
  resubscribe() {
    for (const subscriptionStr of this.subscriptions) {
      try {
        const subscription = JSON.parse(subscriptionStr);
        this.sendMessage(subscription);
      } catch (error) {
        console.error('Error resubscribing:', error);
      }
    }
  }

  /**
   * Start heartbeat to keep connection alive
   */
  startHeartbeat() {
    this.stopHeartbeat(); // Clear any existing interval
    
    this.heartbeatInterval = setInterval(() => {
      if (this.isConnected) {
        this.sendMessage({ type: 'ping', timestamp: Date.now() });
      }
    }, this.config.pingInterval);
  }

  /**
   * Stop heartbeat
   */
  stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * Validate incoming message structure
   */
  validateMessage(data) {
    if (!data || typeof data !== 'object') return false;
    if (!data.type || typeof data.type !== 'string') return false;
    
    switch (data.type) {
      case 'market_data':
        return this.validateMarketData(data.data);
      case 'options_data':
        return data.symbol && Array.isArray(data.data);
      case 'error':
        return data.message && typeof data.message === 'string';
      default:
        return true; // Allow other message types
    }
  }

  /**
   * Validate market data structure
   */
  validateMarketData(data) {
    if (!data || typeof data !== 'object') return false;
    
    const required = ['symbol', 'price', 'bid', 'ask', 'volume', 'timestamp'];
    return required.every(field => data.hasOwnProperty(field));
  }

  /**
   * Get cached market data for a symbol
   */
  getMarketData(symbol) {
    return this.marketDataCache.get(symbol);
  }

  /**
   * Get cached options data for a symbol
   */
  getOptionsData(symbol) {
    return this.optionsDataCache.get(symbol);
  }

  /**
   * Get all cached market data
   */
  getAllMarketData() {
    return Object.fromEntries(this.marketDataCache);
  }

  /**
   * Check if data is stale
   */
  isDataStale(type, symbol, maxAge = 60000) { // 1 minute default
    const key = `${type}_${symbol}`;
    const lastUpdate = this.lastUpdated.get(key);
    return !lastUpdate || (Date.now() - lastUpdate) > maxAge;
  }

  /**
   * Get connection statistics
   */
  getStats() {
    return {
      ...this.stats,
      isConnected: this.isConnected,
      subscriptions: this.subscriptions.size,
      cachedMarketData: this.marketDataCache.size,
      cachedOptionsData: this.optionsDataCache.size,
      queuedMessages: this.messageQueue.length
    };
  }

  /**
   * Clear all cached data
   */
  clearCache() {
    this.marketDataCache.clear();
    this.optionsDataCache.clear();
    this.lastUpdated.clear();
  }

  /**
   * Get connection status
   */
  getConnectionStatus() {
    if (!this.ws) return 'DISCONNECTED';
    
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING: return 'CONNECTING';
      case WebSocket.OPEN: return 'CONNECTED';
      case WebSocket.CLOSING: return 'CLOSING';
      case WebSocket.CLOSED: return 'DISCONNECTED';
      default: return 'UNKNOWN';
    }
  }
}

// Create singleton instance
const websocketService = new WebSocketService();

// Auto-connect on import (can be disabled if needed)
if (process.env.REACT_APP_AUTO_CONNECT_WS !== 'false') {
  websocketService.connect().catch(console.error);
}

export default websocketService;