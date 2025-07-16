import { api } from './api';

// Simple EventEmitter implementation for browser compatibility
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

/**
 * Real-time data service using HTTP polling instead of WebSocket
 * This service provides a WebSocket-like API but uses HTTP polling to the backend
 */
class RealTimeDataService extends EventEmitter {
  constructor() {
    super();
    
    // Service state
    this.isConnected = false;
    this.isPolling = false;
    this.subscriptions = new Set();
    this.pollingInterval = null;
    this.retryCount = 0;
    this.maxRetries = 5;
    
    // Configuration
    this.config = {
      pollingInterval: 5000, // 5 seconds - matches backend UPDATE_INTERVAL
      maxRetries: 5,
      backoffMultiplier: 1.5,
      timeout: 10000 // 10 seconds
    };
    
    // Data caches
    this.marketDataCache = new Map();
    this.lastUpdated = new Map();
    
    // Statistics
    this.stats = {
      messagesReceived: 0,
      requestsSent: 0,
      connectTime: null,
      disconnectTime: null,
      dataValidationErrors: 0,
      reconnectCount: 0,
      pollErrors: 0
    };
    
    console.log('🚀 Real-time data service initialized with HTTP polling');
  }

  /**
   * Connect to the real-time data service
   */
  connect() {
    if (this.isConnected) {
      console.log('📡 Already connected to real-time data service');
      return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
      try {
        console.log('🔌 Connecting to real-time data service...');
        
        this.isConnected = true;
        this.stats.connectTime = new Date();
        this.retryCount = 0;
        
        console.log('✅ Connected to real-time data service');
        this.emit('connected');
        
        // Start polling if we have subscriptions
        if (this.subscriptions.size > 0) {
          this.startPolling();
        }
        
        resolve();
      } catch (error) {
        console.error('❌ Failed to connect to real-time data service:', error);
        reject(error);
      }
    });
  }

  /**
   * Disconnect from the real-time data service
   */
  disconnect() {
    if (!this.isConnected) {
      console.log('📡 Already disconnected from real-time data service');
      return;
    }

    console.log('🔌 Disconnecting from real-time data service...');
    
    this.isConnected = false;
    this.stats.disconnectTime = new Date();
    this.stopPolling();
    
    console.log('✅ Disconnected from real-time data service');
    this.emit('disconnected');
  }

  /**
   * Subscribe to market data for symbols
   */
  async subscribeMarketData(symbols, channels = ['quotes']) {
    try {
      console.log(`📊 Subscribing to market data for symbols:`, symbols);
      
      const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
      
      // Add to local subscriptions
      symbolsArray.forEach(symbol => this.subscriptions.add(symbol.toUpperCase()));
      
      // Notify backend about subscription
      const response = await api.post('/api/websocket/subscribe', {
        symbols: symbolsArray,
        dataTypes: channels
      });
      
      console.log('✅ Subscription successful:', response.data);
      this.emit('subscribed', { symbols: symbolsArray, channels });
      
      // Start polling if connected
      if (this.isConnected && !this.isPolling) {
        this.startPolling();
      }
      
      return true;
    } catch (error) {
      console.error('❌ Failed to subscribe to market data:', error);
      this.emit('error', error);
      return false;
    }
  }

  /**
   * Unsubscribe from symbols
   */
  async unsubscribe(symbols) {
    try {
      console.log(`📊 Unsubscribing from symbols:`, symbols);
      
      const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
      
      // Remove from local subscriptions
      symbolsArray.forEach(symbol => this.subscriptions.delete(symbol.toUpperCase()));
      
      // Notify backend about unsubscription
      const response = await api.delete('/api/websocket/subscribe', {
        data: { symbols: symbolsArray }
      });
      
      console.log('✅ Unsubscription successful:', response.data);
      this.emit('unsubscribed', { symbols: symbolsArray });
      
      // Stop polling if no subscriptions left
      if (this.subscriptions.size === 0) {
        this.stopPolling();
      }
      
      return true;
    } catch (error) {
      console.error('❌ Failed to unsubscribe from symbols:', error);
      this.emit('error', error);
      return false;
    }
  }

  /**
   * Start polling for market data
   */
  startPolling() {
    if (this.isPolling || this.subscriptions.size === 0) {
      return;
    }

    console.log(`🔄 Starting polling for ${this.subscriptions.size} symbols`);
    this.isPolling = true;
    
    // Initial poll
    this.pollMarketData();
    
    // Set up interval polling
    this.pollingInterval = setInterval(() => {
      this.pollMarketData();
    }, this.config.pollingInterval);
  }

  /**
   * Stop polling for market data
   */
  stopPolling() {
    if (!this.isPolling) {
      return;
    }

    console.log('⏹️ Stopping market data polling');
    this.isPolling = false;
    
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
    }
  }

  /**
   * Poll market data from the backend
   */
  async pollMarketData() {
    if (!this.isConnected || this.subscriptions.size === 0) {
      return;
    }

    try {
      const symbols = Array.from(this.subscriptions).join(',');
      console.log(`📊 Polling market data for: ${symbols}`);
      
      this.stats.requestsSent++;
      const response = await api.get(`/api/websocket/stream/${symbols}`, {
        timeout: this.config.timeout
      });
      
      if (response.data && response.data.success) {
        const marketData = response.data.data;
        this.stats.messagesReceived++;
        this.retryCount = 0; // Reset retry count on success
        
        // Process market data
        this.processMarketData(marketData);
        
        // Emit data events
        this.emit('marketData', marketData);
        
        // Emit individual symbol events
        Object.keys(marketData.data || {}).forEach(symbol => {
          const symbolData = marketData.data[symbol];
          if (symbolData && !symbolData.error) {
            this.emit(`marketData_${symbol}`, symbolData);
          }
        });
        
        console.log(`✅ Polled data for ${Object.keys(marketData.data || {}).length} symbols`);
      } else {
        console.warn('⚠️ Invalid response from market data polling:', response.data);
      }
      
    } catch (error) {
      this.stats.pollErrors++;
      console.error('❌ Error polling market data:', error);
      
      // Handle authentication errors
      if (error.response?.status === 401) {
        console.error('🔐 Authentication error - user needs to log in again');
        this.emit('error', new Error('Authentication required'));
        this.disconnect();
        return;
      }
      
      // Handle retry logic
      if (this.retryCount < this.config.maxRetries) {
        this.retryCount++;
        const delay = this.config.pollingInterval * Math.pow(this.config.backoffMultiplier, this.retryCount);
        console.log(`🔄 Retrying in ${delay}ms (attempt ${this.retryCount}/${this.config.maxRetries})`);
        
        setTimeout(() => {
          this.pollMarketData();
        }, delay);
      } else {
        console.error('❌ Max retries reached, stopping polling');
        this.emit('error', error);
        this.stopPolling();
      }
    }
  }

  /**
   * Process and cache market data
   */
  processMarketData(marketData) {
    if (!marketData || !marketData.data) {
      return;
    }

    const now = Date.now();
    
    Object.keys(marketData.data).forEach(symbol => {
      const symbolData = marketData.data[symbol];
      
      if (symbolData && !symbolData.error) {
        // Cache the data
        this.marketDataCache.set(symbol, {
          ...symbolData,
          receivedAt: now
        });
        
        this.lastUpdated.set(symbol, now);
      }
    });
  }

  /**
   * Get cached market data for a symbol
   */
  getMarketData(symbol) {
    return this.marketDataCache.get(symbol.toUpperCase());
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
  isDataStale(symbol, maxAge = 60000) { // 1 minute default
    const lastUpdate = this.lastUpdated.get(symbol.toUpperCase());
    return !lastUpdate || (Date.now() - lastUpdate) > maxAge;
  }

  /**
   * Get connection statistics
   */
  getStats() {
    return {
      ...this.stats,
      isConnected: this.isConnected,
      isPolling: this.isPolling,
      subscriptions: this.subscriptions.size,
      cachedSymbols: this.marketDataCache.size,
      retryCount: this.retryCount
    };
  }

  /**
   * Get current subscriptions
   */
  getSubscriptions() {
    return Array.from(this.subscriptions);
  }

  /**
   * Clear all cached data
   */
  clearCache() {
    this.marketDataCache.clear();
    this.lastUpdated.clear();
  }

  /**
   * Get connection status
   */
  getConnectionStatus() {
    if (!this.isConnected) {
      return 'DISCONNECTED';
    }
    
    if (this.isPolling) {
      return 'POLLING';
    }
    
    return 'CONNECTED';
  }

  /**
   * Get user subscriptions from backend
   */
  async getUserSubscriptions() {
    try {
      const response = await api.get('/api/websocket/subscriptions');
      return response.data?.data?.symbols || [];
    } catch (error) {
      console.error('❌ Failed to get user subscriptions:', error);
      return [];
    }
  }

  /**
   * Get health status from backend
   */
  async getHealthStatus() {
    try {
      const response = await api.get('/api/websocket/health');
      return response.data?.data || { status: 'unknown' };
    } catch (error) {
      console.error('❌ Failed to get health status:', error);
      return { status: 'error', error: error.message };
    }
  }
}

// Create singleton instance
const realTimeDataService = new RealTimeDataService();

// Auto-connect on import
realTimeDataService.connect().catch(console.error);

export default realTimeDataService;