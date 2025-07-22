/**
 * COMPLETED Real-time Data Service for Market Data
 * Uses HTTP polling to mimic WebSocket functionality for Lambda compatibility
 * NOW PROPERLY IMPLEMENTED with environment awareness and cleanup
 */

import { StandardService } from './_serviceTemplate.js';
import { initializeApi } from './api.js';

class RealTimeDataService extends StandardService {
  constructor() {
    super();
    this.isConnected = false;
    this.pollingInterval = null;
    this.pollingDelay = 5000; // 5 seconds default
    this.subscriptions = new Set();
    this.listeners = new Map();
    this.lastData = new Map(); // Cache last data for each symbol
    this.authToken = null;
    this.api = null;
    this.wsEndpoint = null;
    
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
  }

  /**
   * Apply WebSocket service specific configuration
   */
  applyDefaultConfig(config) {
    super.applyDefaultConfig(config);
    
    // WebSocket-specific defaults
    config.pollingDelay = config.pollingDelay || 5000;
    config.maxRetries = config.maxRetries || 5;
    config.connectionTimeout = config.connectionTimeout || 10000;
    
    // Derive WebSocket URL if not provided
    if (!config.WS_URL && config.API_URL) {
      config.WS_URL = `${config.API_URL}/api/websocket`;
    }
  }

  /**
   * Browser-specific initialization
   */
  async initializeForBrowser() {
    this.api = await initializeApi();
    this.wsEndpoint = this.config.WS_URL;
    
    if (!this.wsEndpoint) {
      throw new Error('WebSocket URL not configured - set WS_URL in config or ensure API_URL is available');
    }
    
    console.log(`🔌 WebSocket service initialized for: ${this.wsEndpoint}`);
  }

  /**
   * Test environment initialization
   */
  async initializeForTest() {
    this.api = await initializeApi();
    this.wsEndpoint = 'ws://test-websocket.example.com';
    console.log('🧪 WebSocket service initialized for test environment');
  }

  /**
   * Server environment initialization
   */
  async initializeForServer() {
    // No WebSocket connections in SSR
    this.wsEndpoint = null;
    console.log('🖥️ WebSocket service initialized for server (SSR mode)');
  }

  /**
   * Connect to real-time data stream
   */
  async connect() {
    if (!this.initialized) {
      await this.initialize();
    }

    if (this.isServerEnvironment()) {
      console.log('⚠️ WebSocket connections not available in server environment');
      return false;
    }

    if (this.isConnected) {
      console.log('✅ WebSocket already connected');
      return true;
    }

    try {
      this.health.connectionTime = Date.now();
      
      // Start HTTP polling (simulating WebSocket)
      await this.startPolling();
      
      this.isConnected = true;
      this.health.pollingActive = true;
      
      console.log(`✅ WebSocket service connected via HTTP polling`);
      this.notifySubscribers({ type: 'connected' });
      return true;
      
    } catch (error) {
      console.error('❌ Failed to connect WebSocket service:', error);
      this.health.errors++;
      throw error;
    }
  }

  /**
   * Start HTTP polling to simulate WebSocket
   */
  async startPolling() {
    if (this.pollingInterval) {
      this.clearTimer(this.pollingInterval);
    }

    const pollData = async () => {
      if (!this.isConnected) return;

      try {
        const startTime = Date.now();
        
        // Poll for updates from subscribed symbols
        if (this.subscriptions.size > 0) {
          const symbols = Array.from(this.subscriptions);
          const response = await this.api.get('/market/realtime', {
            params: { symbols: symbols.join(',') },
            timeout: this.config.timeout
          });

          this.health.latency = Date.now() - startTime;
          this.health.requestsSuccessful++;
          this.health.lastUpdate = Date.now();

          // Process and cache data
          if (response.data) {
            this.processRealtimeData(response.data);
          }
        }
      } catch (error) {
        this.health.requestsFailed++;
        this.health.errors++;
        console.warn('⚠️ Polling error:', error.message);
        
        // Don't throw - keep polling
      }
    };

    // Initial poll
    await pollData();
    
    // Set up interval polling
    this.pollingInterval = setInterval(pollData, this.config.pollingDelay);
    this.addTimer(this.pollingInterval);
  }

  /**
   * Process incoming real-time data
   */
  processRealtimeData(data) {
    if (Array.isArray(data)) {
      data.forEach(item => this.processDataItem(item));
    } else {
      this.processDataItem(data);
    }
  }

  /**
   * Process individual data item
   */
  processDataItem(item) {
    if (!item.symbol) return;

    // Cache the data
    this.lastData.set(item.symbol, {
      ...item,
      timestamp: Date.now()
    });

    // Notify listeners
    const listeners = this.listeners.get(item.symbol) || new Set();
    listeners.forEach(callback => {
      try {
        callback(item);
      } catch (error) {
        console.error(`Listener error for ${item.symbol}:`, error);
      }
    });

    // Notify general subscribers
    this.notifySubscribers({
      type: 'data',
      symbol: item.symbol,
      data: item
    });
  }

  /**
   * Subscribe to symbol updates
   */
  subscribe(symbol, callback) {
    if (!this.listeners.has(symbol)) {
      this.listeners.set(symbol, new Set());
    }
    
    this.listeners.get(symbol).add(callback);
    this.subscriptions.add(symbol);
    
    console.log(`📊 Subscribed to ${symbol}`);
    
    // Return unsubscribe function
    return () => this.unsubscribe(symbol, callback);
  }

  /**
   * Unsubscribe from symbol updates
   */
  unsubscribe(symbol, callback) {
    if (this.listeners.has(symbol)) {
      this.listeners.get(symbol).delete(callback);
      
      // Clean up if no more listeners
      if (this.listeners.get(symbol).size === 0) {
        this.listeners.delete(symbol);
        this.subscriptions.delete(symbol);
        console.log(`📊 Unsubscribed from ${symbol}`);
      }
    }
  }

  /**
   * Get last known data for symbol
   */
  getLastData(symbol) {
    return this.lastData.get(symbol) || null;
  }

  /**
   * Get connection health metrics
   */
  getHealthMetrics() {
    return {
      ...this.health,
      isConnected: this.isConnected,
      subscriptionCount: this.subscriptions.size,
      listenerCount: Array.from(this.listeners.values()).reduce((total, set) => total + set.size, 0)
    };
  }

  /**
   * Disconnect from real-time data stream
   */
  async disconnect() {
    if (!this.isConnected) return;

    console.log('🔌 Disconnecting WebSocket service...');
    
    this.isConnected = false;
    this.health.pollingActive = false;
    
    // Clear polling
    if (this.pollingInterval) {
      this.clearTimer(this.pollingInterval);
      this.pollingInterval = null;
    }
    
    this.notifySubscribers({ type: 'disconnected' });
    console.log('✅ WebSocket service disconnected');
  }

  /**
   * Enhanced cleanup
   */
  async cleanup() {
    await this.disconnect();
    
    // Clear all data
    this.subscriptions.clear();
    this.listeners.clear();
    this.lastData.clear();
    
    // Reset health metrics
    this.health = {
      latency: 0,
      requestsSuccessful: 0,
      requestsFailed: 0,
      errors: 0,
      lastUpdate: null,
      connectionTime: null,
      pollingActive: false
    };
    
    await super.cleanup();
  }

  /**
   * Enhanced health check
   */
  async healthCheck() {
    const baseHealth = await super.healthCheck();
    
    if (!baseHealth.healthy) return baseHealth;
    
    const isHealthy = this.isConnected && 
                     this.health.errors < 10 && 
                     (this.health.lastUpdate === null || Date.now() - this.health.lastUpdate < 30000);
    
    return {
      healthy: isHealthy,
      environment: this.getEnvironment(),
      metrics: this.getHealthMetrics(),
      reason: isHealthy ? 'Service healthy' : 'Connection issues detected'
    };
  }
}

// Factory function with proper cleanup
let serviceInstance = null;

const getRealTimeDataService = async () => {
  if (!serviceInstance) {
    serviceInstance = new RealTimeDataService();
    await serviceInstance.initialize();
  }
  return serviceInstance;
};

// Cleanup on exit
if (typeof process !== 'undefined') {
  process.on('exit', () => {
    if (serviceInstance) serviceInstance.cleanup();
  });
} else if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    if (serviceInstance) serviceInstance.cleanup();
  });
}

export default getRealTimeDataService;
export { RealTimeDataService };