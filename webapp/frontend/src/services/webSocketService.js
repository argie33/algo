/**
 * Professional Real-time Data Service for Market Data
 * Uses HTTP polling to mimic WebSocket functionality for Lambda compatibility
 * Integrates with deployed Lambda WebSocket routes
 */

import { api } from './api';

// Get WebSocket URL from config or environment
const getWebSocketURL = () => {
  // Try runtime config first (from public/config.js)
  if (window.__CONFIG__ && window.__CONFIG__.WS_URL) {
    return window.__CONFIG__.WS_URL;
  }
  
  // Fall back to environment variables
  return process.env.REACT_APP_WEBSOCKET_ENDPOINT || 
         process.env.VITE_WS_URL ||
         'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/websocket';
};

const WS_ENDPOINT = getWebSocketURL();

class RealTimeDataService {
  constructor() {
    this.isConnected = false;
    this.pollingInterval = null;
    this.pollingDelay = 5000; // 5 seconds default
    this.subscriptions = new Set();
    this.listeners = new Map();
    this.lastData = new Map(); // Cache last data for each symbol
    this.authToken = null;
    
    // Connection health metrics
    this.health = {
      latency: 0,
      requestsSuccessful: 0,
      requestsFailed: 0,
      errors: 0,
      lastUpdate: null,
      connectionTime: null,
      pollingActive: false
    };
    
    console.log('🚀 Real-time data service initialized with endpoint:', WS_ENDPOINT);
  }

  /**
   * Start real-time data service with HTTP polling
   */
  async connect(authToken = null) {
    try {
      console.log('🔌 Starting real-time data service with HTTP polling');
      
      this.authToken = authToken;
      
      // Test the health endpoint first
      const healthCheck = await this.testConnection();
      if (!healthCheck.success) {
        throw new Error(`Real-time service health check failed: ${healthCheck.error}`);
      }
      
      this.isConnected = true;
      this.health.connectionTime = new Date();
      this.health.pollingActive = false;
      
      this.emit('connected', {
        timestamp: new Date(),
        endpoint: WS_ENDPOINT,
        method: 'HTTP_POLLING'
      });
      
      console.log('✅ Real-time data service connected successfully');
      return true;
      
    } catch (error) {
      console.error('❌ Real-time data service connection failed:', error);
      this.health.errors++;
      this.isConnected = false;
      throw error;
    }
  }

  /**
   * Start polling for subscribed symbols
   */
  startPolling() {
    if (this.pollingInterval || !this.isConnected) return;
    
    console.log('📡 Starting HTTP polling for real-time data');
    this.health.pollingActive = true;
    
    this.pollingInterval = setInterval(async () => {
      await this.pollForData();
    }, this.pollingDelay);
    
    // Do initial poll immediately
    this.pollForData();
  }

  /**
   * Stop polling
   */
  stopPolling() {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
      this.health.pollingActive = false;
      console.log('📡 Stopped HTTP polling');
    }
  }

  /**
   * Poll for real-time data from subscribed symbols
   */
  async pollForData() {
    if (this.subscriptions.size === 0) return;
    
    const symbols = Array.from(this.subscriptions);
    const requestStart = Date.now();
    
    try {
      console.log(`📊 Polling data for ${symbols.length} symbols:`, symbols);
      
      // Use the stream endpoint which supports multiple symbols
      const url = `${WS_ENDPOINT}/stream/${symbols.join(',')}`;
      const headers = {};
      
      if (this.authToken) {
        headers.Authorization = `Bearer ${this.authToken}`;
      }
      
      const response = await fetch(url, { headers });
      const data = await response.json();
      
      this.health.latency = Date.now() - requestStart;
      this.health.lastUpdate = new Date();
      
      if (data.success) {
        this.health.requestsSuccessful++;
        this.handleMarketDataResponse(data.data);
      } else {
        this.health.requestsFailed++;
        console.error('❌ Polling request failed:', data.message);
        this.emit('error', { message: data.message, type: 'polling_error' });
      }
      
    } catch (error) {
      this.health.requestsFailed++;
      this.health.errors++;
      console.error('❌ Polling error:', error);
      this.emit('error', { message: error.message, type: 'polling_error' });
    }
  }

  /**
   * Handle market data response from HTTP polling
   */
  handleMarketDataResponse(responseData) {
    console.log('📨 Market data received:', responseData);
    
    if (responseData.data) {
      // Process each symbol's data
      Object.entries(responseData.data).forEach(([symbol, symbolData]) => {
        if (symbolData.error) {
          console.warn(`⚠️ Error for symbol ${symbol}:`, symbolData.error);
          this.emit('symbol_error', { symbol, error: symbolData.error });
        } else {
          // Cache the data
          this.lastData.set(symbol, symbolData);
          
          // Emit market data event
          this.handleMarketData({
            type: 'market_data',
            symbol: symbol,
            data: symbolData,
            timestamp: symbolData.timestamp || Date.now()
          });
        }
      });
    }
    
    // Emit general update event
    this.emit('data_update', {
      symbols: Object.keys(responseData.data || {}),
      timestamp: Date.now(),
      statistics: responseData.statistics,
      cacheStatus: responseData.cacheStatus
    });
  }

  /**
   * Handle disconnection
   */
  disconnect() {
    console.log('🔌 Disconnecting real-time data service...');
    
    this.stopPolling();
    this.isConnected = false;
    this.authToken = null;
    this.subscriptions.clear();
    this.lastData.clear();
    
    this.emit('disconnected', {
      timestamp: new Date(),
      reason: 'Manual disconnect'
    });
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
   * Subscribe to market data for symbols
   */
  subscribe(symbols, channels = ['quotes']) {
    const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
    
    // Add to local subscriptions
    const newSymbols = [];
    symbolsArray.forEach(symbol => {
      const upperSymbol = symbol.toUpperCase();
      if (!this.subscriptions.has(upperSymbol)) {
        this.subscriptions.add(upperSymbol);
        newSymbols.push(upperSymbol);
      }
    });
    
    this.emit('subscription_requested', { symbols: symbolsArray, channels });
    
    console.log('📡 Subscribed to symbols:', symbolsArray);
    console.log('📊 Total subscriptions:', Array.from(this.subscriptions));
    
    // Start polling if we have subscriptions and are connected
    if (this.subscriptions.size > 0 && this.isConnected && !this.pollingInterval) {
      this.startPolling();
    }
    
    return {
      success: true,
      symbols: symbolsArray,
      totalSubscriptions: this.subscriptions.size
    };
  }

  /**
   * Unsubscribe from symbols
   */
  unsubscribe(symbols) {
    const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
    
    // Remove from local subscriptions
    symbolsArray.forEach(symbol => {
      this.subscriptions.delete(symbol.toUpperCase());
      this.lastData.delete(symbol.toUpperCase());
    });
    
    this.emit('unsubscription_requested', { symbols: symbolsArray });
    
    console.log('📡 Unsubscribed from symbols:', symbolsArray);
    console.log('📊 Remaining subscriptions:', Array.from(this.subscriptions));
    
    // Stop polling if no subscriptions remain
    if (this.subscriptions.size === 0) {
      this.stopPolling();
    }
    
    return {
      success: true,
      unsubscribed: symbolsArray,
      remainingSubscriptions: this.subscriptions.size
    };
  }

  /**
   * Get current subscriptions
   */
  getSubscriptions() {
    return Array.from(this.subscriptions);
  }

  /**
   * Get last cached data for a symbol
   */
  getLastData(symbol) {
    return this.lastData.get(symbol.toUpperCase());
  }

  /**
   * Get all cached data
   */
  getAllLastData() {
    const result = {};
    this.lastData.forEach((data, symbol) => {
      result[symbol] = data;
    });
    return result;
  }

  /**
   * Set polling delay (how often to poll for new data)
   */
  setPollingDelay(delayMs) {
    this.pollingDelay = delayMs;
    console.log(`📡 Polling delay updated to ${delayMs}ms`);
    
    // Restart polling with new delay if currently active
    if (this.pollingInterval) {
      this.stopPolling();
      this.startPolling();
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
      pollingDelay: this.pollingDelay,
      cachedSymbols: this.lastData.size,
      endpoint: WS_ENDPOINT
    };
  }

  /**
   * Get connection status
   */
  getStatus() {
    if (!this.isConnected) {
      return 'DISCONNECTED';
    }
    
    if (!this.health.pollingActive) {
      return 'CONNECTED_IDLE';
    }
    
    if (this.health.latency > 10000) {
      return 'POOR_CONNECTION';
    }
    
    if (this.health.latency > 3000) {
      return 'SLOW_CONNECTION';
    }
    
    return 'CONNECTED_ACTIVE';
  }

  /**
   * Test connection with backend health endpoint
   */
  async testConnection() {
    try {
      const response = await fetch(`${WS_ENDPOINT}/health`);
      const data = await response.json();
      
      return {
        success: response.ok,
        backend: data,
        realtime: this.getHealth(),
        endpoint: WS_ENDPOINT
      };
    } catch (error) {
      return {
        success: false,
        error: error.message,
        realtime: this.getHealth(),
        endpoint: WS_ENDPOINT
      };
    }
  }
}

// Create singleton instance
const realTimeDataService = new RealTimeDataService();

export default realTimeDataService;