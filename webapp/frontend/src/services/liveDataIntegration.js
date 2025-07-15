/**
 * Live Data Integration Service
 * Handles backend integration for live data management and WebSocket coordination
 */

import { api } from './api';
import webSocketService from './webSocketService';

class LiveDataIntegration {
  constructor() {
    this.isInitialized = false;
    this.backendHealth = null;
    this.subscriptionCache = new Map();
    this.dataCache = new Map();
    this.listeners = new Map();
  }

  /**
   * Initialize the live data integration
   */
  async initialize() {
    try {
      console.log('🚀 Initializing Live Data Integration...');
      
      // Check backend health
      await this.checkBackendHealth();
      
      // Test WebSocket connectivity
      await this.testWebSocketConnectivity();
      
      // Setup WebSocket event handlers
      this.setupWebSocketHandlers();
      
      this.isInitialized = true;
      console.log('✅ Live Data Integration initialized successfully');
      
      return { success: true };
    } catch (error) {
      console.error('❌ Failed to initialize Live Data Integration:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Check backend WebSocket health
   */
  async checkBackendHealth() {
    try {
      const response = await api.get('/api/websocket/health');
      this.backendHealth = response.data;
      
      console.log('✅ Backend WebSocket health check passed:', this.backendHealth);
      return this.backendHealth;
    } catch (error) {
      console.error('❌ Backend health check failed:', error);
      throw new Error('Backend WebSocket service unavailable');
    }
  }

  /**
   * Test WebSocket connectivity
   */
  async testWebSocketConnectivity() {
    try {
      const healthData = await webSocketService.testConnection();
      console.log('✅ WebSocket connectivity test passed:', healthData);
      return healthData;
    } catch (error) {
      console.error('❌ WebSocket connectivity test failed:', error);
      throw new Error('WebSocket connection unavailable');
    }
  }

  /**
   * Setup WebSocket event handlers
   */
  setupWebSocketHandlers() {
    // Handle market data updates
    webSocketService.on('market_data', (data) => {
      this.handleMarketDataUpdate(data);
    });

    // Handle connection events
    webSocketService.on('connected', (data) => {
      console.log('🔌 WebSocket connected:', data);
      this.emit('connection_status', { status: 'connected', data });
    });

    webSocketService.on('disconnected', (data) => {
      console.log('🔌 WebSocket disconnected:', data);
      this.emit('connection_status', { status: 'disconnected', data });
    });

    webSocketService.on('error', (error) => {
      console.error('❌ WebSocket error:', error);
      this.emit('connection_error', error);
    });

    // Handle subscription confirmations
    webSocketService.on('subscription_confirmed', (data) => {
      console.log('✅ Subscription confirmed:', data);
      this.updateSubscriptionCache(data.symbols, 'active');
      this.emit('subscription_update', data);
    });
  }

  /**
   * Handle market data updates
   */
  handleMarketDataUpdate(data) {
    // Cache the data
    this.dataCache.set(data.symbol, {
      ...data,
      receivedAt: new Date(),
      cached: true
    });

    // Emit to listeners
    this.emit('market_data', data);
    this.emit(`market_data_${data.symbol}`, data);
  }

  /**
   * Subscribe to symbols with backend coordination
   */
  async subscribe(symbols, options = {}) {
    try {
      const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
      
      console.log('📡 Subscribing to symbols via backend coordination:', symbolsArray);
      
      // Register subscription with backend
      const response = await api.post('/api/websocket/subscribe', {
        symbols: symbolsArray,
        dataTypes: options.dataTypes || ['quotes'],
        channels: options.channels || ['market_data']
      });

      if (response.data.success) {
        // Subscribe via WebSocket
        webSocketService.subscribe(symbolsArray, options.channels);
        
        // Update cache
        this.updateSubscriptionCache(symbolsArray, 'pending');
        
        console.log('✅ Backend subscription registered:', response.data);
        return { success: true, data: response.data };
      } else {
        throw new Error(response.data.error || 'Subscription failed');
      }
    } catch (error) {
      console.error('❌ Subscription failed:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Unsubscribe from symbols
   */
  async unsubscribe(symbols) {
    try {
      const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
      
      console.log('📡 Unsubscribing from symbols:', symbolsArray);
      
      // Unregister with backend
      const response = await api.delete('/api/websocket/subscribe', {
        data: { symbols: symbolsArray }
      });

      if (response.data.success) {
        // Unsubscribe via WebSocket
        webSocketService.unsubscribe(symbolsArray);
        
        // Update cache
        this.updateSubscriptionCache(symbolsArray, 'inactive');
        
        console.log('✅ Backend unsubscription completed:', response.data);
        return { success: true, data: response.data };
      } else {
        throw new Error(response.data.error || 'Unsubscription failed');
      }
    } catch (error) {
      console.error('❌ Unsubscription failed:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Get current user subscriptions from backend
   */
  async getUserSubscriptions() {
    try {
      const response = await api.get('/api/websocket/subscriptions');
      
      if (response.data.success) {
        const subscriptions = response.data.data.symbols || [];
        
        // Update local cache
        subscriptions.forEach(symbol => {
          this.subscriptionCache.set(symbol, 'active');
        });
        
        return { success: true, subscriptions };
      } else {
        throw new Error(response.data.error || 'Failed to get subscriptions');
      }
    } catch (error) {
      console.error('❌ Failed to get user subscriptions:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Connect to WebSocket with user context
   */
  async connect(userId = null) {
    try {
      await webSocketService.connect(userId);
      return { success: true };
    } catch (error) {
      console.error('❌ Failed to connect WebSocket:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Disconnect from WebSocket
   */
  disconnect() {
    webSocketService.disconnect();
    this.dataCache.clear();
    this.subscriptionCache.clear();
  }

  /**
   * Get connection status and health
   */
  getConnectionStatus() {
    return {
      webSocket: webSocketService.getStatus(),
      health: webSocketService.getHealth(),
      backend: this.backendHealth,
      initialized: this.isInitialized
    };
  }

  /**
   * Get cached market data
   */
  getMarketData(symbol = null) {
    if (symbol) {
      return this.dataCache.get(symbol) || null;
    }
    return Object.fromEntries(this.dataCache);
  }

  /**
   * Get cached subscriptions
   */
  getSubscriptions() {
    const activeSubscriptions = [];
    for (const [symbol, status] of this.subscriptionCache.entries()) {
      if (status === 'active') {
        activeSubscriptions.push(symbol);
      }
    }
    return activeSubscriptions;
  }

  /**
   * Update subscription cache
   */
  updateSubscriptionCache(symbols, status) {
    const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
    symbolsArray.forEach(symbol => {
      this.subscriptionCache.set(symbol, status);
    });
  }

  /**
   * Get system metrics
   */
  getMetrics() {
    const wsHealth = webSocketService.getHealth();
    
    return {
      connection: {
        isConnected: wsHealth.isConnected,
        latency: wsHealth.latency,
        status: webSocketService.getStatus()
      },
      subscriptions: {
        active: this.getSubscriptions().length,
        total: this.subscriptionCache.size
      },
      data: {
        symbolsWithData: this.dataCache.size,
        messagesReceived: wsHealth.messagesReceived,
        messagesSent: wsHealth.messagesSent,
        errors: wsHealth.errors
      },
      backend: this.backendHealth
    };
  }

  /**
   * Test full integration
   */
  async testIntegration() {
    try {
      console.log('🧪 Running full integration test...');
      
      const results = {
        backend: null,
        websocket: null,
        subscription: null,
        dataFlow: null
      };

      // Test backend health
      try {
        results.backend = await this.checkBackendHealth();
      } catch (error) {
        results.backend = { error: error.message };
      }

      // Test WebSocket connectivity
      try {
        results.websocket = await this.testWebSocketConnectivity();
      } catch (error) {
        results.websocket = { error: error.message };
      }

      // Test subscription flow
      try {
        const testSymbol = 'AAPL';
        const subResult = await this.subscribe([testSymbol]);
        await new Promise(resolve => setTimeout(resolve, 2000)); // Wait 2 seconds
        const unsubResult = await this.unsubscribe([testSymbol]);
        
        results.subscription = {
          subscribe: subResult,
          unsubscribe: unsubResult
        };
      } catch (error) {
        results.subscription = { error: error.message };
      }

      console.log('🧪 Integration test completed:', results);
      return results;
    } catch (error) {
      console.error('❌ Integration test failed:', error);
      return { error: error.message };
    }
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
   * Emit event
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
}

// Create singleton instance
const liveDataIntegration = new LiveDataIntegration();

export default liveDataIntegration;