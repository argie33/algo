/**
 * Professional WebSocket Service for Real-time Market Data
 * Integrates with AWS API Gateway WebSocket and deployed infrastructure
 */

import { api } from './api';

// WebSocket endpoint from deployed infrastructure
const WS_ENDPOINT = process.env.REACT_APP_WEBSOCKET_ENDPOINT || 
                   'wss://your-websocket-id.execute-api.us-east-1.amazonaws.com/dev';

class WebSocketService {
  constructor() {
    this.ws = null;
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000; // Start with 1 second
    this.subscriptions = new Set();
    this.listeners = new Map();
    this.messageQueue = [];
    this.heartbeatInterval = null;
    this.connectionId = null;
    
    // Connection health metrics
    this.health = {
      latency: 0,
      messagesReceived: 0,
      messagesSent: 0,
      errors: 0,
      lastHeartbeat: null,
      connectionTime: null,
      reconnectCount: 0
    };
  }

  /**
   * Connect to WebSocket with authentication
   */
  async connect(userId = null) {
    try {
      console.log('🔌 Connecting to WebSocket:', WS_ENDPOINT);
      
      // Build connection URL with user context
      const wsUrl = userId ? `${WS_ENDPOINT}?userId=${userId}` : WS_ENDPOINT;
      
      this.ws = new WebSocket(wsUrl);
      this.setupEventHandlers();
      
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error('WebSocket connection timeout'));
        }, 10000);

        this.ws.onopen = () => {
          clearTimeout(timeout);
          this.onConnected();
          resolve();
        };

        this.ws.onerror = (error) => {
          clearTimeout(timeout);
          reject(error);
        };
      });
    } catch (error) {
      console.error('❌ WebSocket connection failed:', error);
      this.health.errors++;
      throw error;
    }
  }

  /**
   * Setup WebSocket event handlers
   */
  setupEventHandlers() {
    if (!this.ws) return;

    this.ws.onopen = () => {
      this.onConnected();
    };

    this.ws.onmessage = (event) => {
      this.onMessage(event);
    };

    this.ws.onclose = (event) => {
      this.onDisconnected(event);
    };

    this.ws.onerror = (error) => {
      this.onError(error);
    };
  }

  /**
   * Handle successful connection
   */
  onConnected() {
    console.log('✅ WebSocket connected successfully');
    this.isConnected = true;
    this.reconnectAttempts = 0;
    this.reconnectDelay = 1000;
    this.health.connectionTime = new Date();
    this.health.reconnectCount = this.reconnectAttempts;
    
    this.emit('connected', {
      connectionId: this.connectionId,
      timestamp: new Date()
    });

    // Start heartbeat
    this.startHeartbeat();
    
    // Process queued messages
    this.processMessageQueue();
    
    // Re-establish subscriptions
    this.reestablishSubscriptions();
  }

  /**
   * Handle incoming messages
   */
  onMessage(event) {
    try {
      const data = JSON.parse(event.data);
      this.health.messagesReceived++;
      
      console.log('📨 WebSocket message received:', data);
      
      // Handle different message types
      switch (data.type) {
        case 'market_data':
          this.handleMarketData(data);
          break;
        case 'pong':
          this.handlePong(data);
          break;
        case 'subscription_confirmed':
          this.handleSubscriptionConfirmed(data);
          break;
        case 'error':
          this.handleError(data);
          break;
        default:
          this.emit('message', data);
      }
    } catch (error) {
      console.error('❌ WebSocket message parse error:', error);
      this.health.errors++;
    }
  }

  /**
   * Handle disconnection
   */
  onDisconnected(event) {
    console.log('🔌 WebSocket disconnected:', event.code, event.reason);
    this.isConnected = false;
    this.connectionId = null;
    this.stopHeartbeat();
    
    this.emit('disconnected', {
      code: event.code,
      reason: event.reason,
      timestamp: new Date()
    });

    // Attempt reconnection if not intentional
    if (event.code !== 1000) { // 1000 = normal closure
      this.attemptReconnect();
    }
  }

  /**
   * Handle WebSocket errors
   */
  onError(error) {
    console.error('❌ WebSocket error:', error);
    this.health.errors++;
    this.emit('error', error);
  }

  /**
   * Handle market data messages
   */
  handleMarketData(data) {
    this.emit('market_data', data);
    
    // Emit symbol-specific events
    if (data.symbol) {
      this.emit(`market_data_${data.symbol}`, data);
    }
  }

  /**
   * Handle pong responses for latency calculation
   */
  handlePong(data) {
    if (this.health.lastHeartbeat) {
      this.health.latency = Date.now() - this.health.lastHeartbeat.getTime();
    }
    this.emit('pong', data);
  }

  /**
   * Handle subscription confirmations
   */
  handleSubscriptionConfirmed(data) {
    console.log('✅ Subscription confirmed:', data.symbols);
    this.emit('subscription_confirmed', data);
  }

  /**
   * Handle error messages
   */
  handleError(data) {
    console.error('❌ WebSocket server error:', data);
    this.emit('server_error', data);
  }

  /**
   * Send message to WebSocket
   */
  send(message) {
    if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify(message));
        this.health.messagesSent++;
        console.log('📤 WebSocket message sent:', message);
      } catch (error) {
        console.error('❌ Failed to send WebSocket message:', error);
        this.health.errors++;
      }
    } else {
      // Queue message for later
      this.messageQueue.push(message);
      console.log('📝 Message queued (WebSocket not ready):', message);
    }
  }

  /**
   * Subscribe to market data for symbols
   */
  subscribe(symbols, channels = ['quotes']) {
    const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
    
    const message = {
      action: 'subscribe',
      symbols: symbolsArray,
      channels: channels,
      timestamp: Date.now()
    };

    // Add to local subscriptions
    symbolsArray.forEach(symbol => this.subscriptions.add(symbol));
    
    this.send(message);
    this.emit('subscription_requested', { symbols: symbolsArray, channels });
    
    console.log('📡 Subscribed to symbols:', symbolsArray);
  }

  /**
   * Unsubscribe from symbols
   */
  unsubscribe(symbols) {
    const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
    
    const message = {
      action: 'unsubscribe',
      symbols: symbolsArray,
      timestamp: Date.now()
    };

    // Remove from local subscriptions
    symbolsArray.forEach(symbol => this.subscriptions.delete(symbol));
    
    this.send(message);
    this.emit('unsubscription_requested', { symbols: symbolsArray });
    
    console.log('📡 Unsubscribed from symbols:', symbolsArray);
  }

  /**
   * Get current subscriptions
   */
  getSubscriptions() {
    return Array.from(this.subscriptions);
  }

  /**
   * Disconnect WebSocket
   */
  disconnect() {
    console.log('🔌 Disconnecting WebSocket...');
    
    if (this.ws) {
      this.ws.close(1000, 'Manual disconnect');
      this.ws = null;
    }
    
    this.stopHeartbeat();
    this.isConnected = false;
    this.connectionId = null;
    this.subscriptions.clear();
    this.messageQueue = [];
  }

  /**
   * Start heartbeat to maintain connection
   */
  startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      if (this.isConnected) {
        this.health.lastHeartbeat = new Date();
        this.send({ action: 'ping', timestamp: Date.now() });
      }
    }, 30000); // Every 30 seconds
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
   * Process queued messages
   */
  processMessageQueue() {
    while (this.messageQueue.length > 0) {
      const message = this.messageQueue.shift();
      this.send(message);
    }
  }

  /**
   * Re-establish subscriptions after reconnect
   */
  reestablishSubscriptions() {
    if (this.subscriptions.size > 0) {
      const symbols = Array.from(this.subscriptions);
      console.log('🔄 Re-establishing subscriptions for:', symbols);
      this.subscribe(symbols);
    }
  }

  /**
   * Attempt to reconnect with exponential backoff
   */
  attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('❌ Max reconnection attempts reached');
      this.emit('max_reconnect_attempts', {
        attempts: this.reconnectAttempts,
        timestamp: new Date()
      });
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    
    console.log(`🔄 Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    this.emit('reconnect_attempt', {
      attempt: this.reconnectAttempts,
      delay: delay,
      timestamp: new Date()
    });

    setTimeout(() => {
      if (!this.isConnected) {
        this.connect().catch(error => {
          console.error('Reconnection failed:', error);
        });
      }
    }, delay);
  }

  /**
   * Add event listener
   */
  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  /**
   * Remove event listener
   */
  off(event, callback) {
    if (this.listeners.has(event)) {
      const callbacks = this.listeners.get(event);
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
    }
  }

  /**
   * Emit event to all listeners
   */
  emit(event, data) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error(`Error in event listener for ${event}:`, error);
        }
      });
    }
  }

  /**
   * Get connection health metrics
   */
  getHealth() {
    return {
      ...this.health,
      isConnected: this.isConnected,
      subscriptions: this.getSubscriptions(),
      reconnectAttempts: this.reconnectAttempts,
      queuedMessages: this.messageQueue.length,
      connectionId: this.connectionId
    };
  }

  /**
   * Get connection status
   */
  getStatus() {
    if (!this.isConnected) {
      return 'DISCONNECTED';
    }
    
    if (this.health.latency > 5000) {
      return 'POOR_CONNECTION';
    }
    
    if (this.health.latency > 1000) {
      return 'SLOW_CONNECTION';
    }
    
    return 'CONNECTED';
  }

  /**
   * Test connection with backend WebSocket health endpoint
   */
  async testConnection() {
    try {
      const response = await api.get('/api/websocket/health');
      return {
        success: true,
        backend: response.data,
        websocket: this.getHealth()
      };
    } catch (error) {
      return {
        success: false,
        error: error.message,
        websocket: this.getHealth()
      };
    }
  }
}

// Create singleton instance
const webSocketService = new WebSocketService();

export default webSocketService;