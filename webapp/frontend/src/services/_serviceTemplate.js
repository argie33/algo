/**
 * STANDARDIZED SERVICE TEMPLATE
 * Use this pattern for all services to ensure:
 * - Lazy initialization (no module-level side effects)
 * - Environment awareness (browser/SSR/test compatibility)
 * - Proper cleanup (timers, connections, subscribers)
 * - Consistent API patterns
 */

class StandardService {
  constructor() {
    this.initialized = false;
    this.timers = new Set();
    this.connections = new Set();
    this.subscribers = new Set();
    this.config = null;
  }

  /**
   * Lazy initialization - called on first use
   */
  async initialize() {
    if (this.initialized) return this;
    
    try {
      // Get configuration safely
      this.config = await this.getConfig();
      
      // Environment-specific initialization
      if (this.isServerEnvironment()) {
        await this.initializeForServer();
      } else if (this.isTestEnvironment()) {
        await this.initializeForTest();
      } else {
        await this.initializeForBrowser();
      }
      
      this.initialized = true;
      console.log(`✅ ${this.constructor.name} initialized for ${this.getEnvironment()}`);
      return this;
    } catch (error) {
      console.error(`❌ Failed to initialize ${this.constructor.name}:`, error);
      throw error;
    }
  }

  /**
   * Safe configuration loading with fallbacks
   */
  async getConfig() {
    const config = {};
    
    // 1. Try window config (runtime)
    if (typeof window !== 'undefined' && window.__CONFIG__) {
      Object.assign(config, window.__CONFIG__);
    }
    
    // 2. Try environment variables  
    if (typeof process !== 'undefined' && process.env) {
      // Map relevant env vars to config
      if (process.env.VITE_API_URL) config.API_URL = process.env.VITE_API_URL;
      if (process.env.VITE_WS_URL) config.WS_URL = process.env.VITE_WS_URL;
    }
    
    // 3. Apply defaults
    this.applyDefaultConfig(config);
    
    return config;
  }

  /**
   * Apply service-specific default configuration
   * Override in subclasses
   */
  applyDefaultConfig(config) {
    // Base defaults
    config.timeout = config.timeout || 5000;
    config.retries = config.retries || 3;
  }

  /**
   * Environment detection utilities
   */
  isServerEnvironment() {
    return typeof window === 'undefined';
  }

  isTestEnvironment() {
    return process.env.NODE_ENV === 'test';
  }

  isBrowserEnvironment() {
    return typeof window !== 'undefined' && process.env.NODE_ENV !== 'test';
  }

  getEnvironment() {
    if (this.isServerEnvironment()) return 'server';
    if (this.isTestEnvironment()) return 'test';
    return 'browser';
  }

  /**
   * Environment-specific initialization methods
   * Override in subclasses as needed
   */
  async initializeForServer() {
    // Server-side initialization (SSR)
  }

  async initializeForTest() {
    // Test environment initialization (mocked services, etc.)
  }

  async initializeForBrowser() {
    // Browser initialization (real connections, timers, etc.)
  }

  /**
   * Timer management - prevents memory leaks
   */
  addTimer(timerId) {
    this.timers.add(timerId);
    return timerId;
  }

  clearTimer(timerId) {
    clearTimeout(timerId);
    clearInterval(timerId);
    this.timers.delete(timerId);
  }

  clearAllTimers() {
    this.timers.forEach(id => {
      clearTimeout(id);
      clearInterval(id);
    });
    this.timers.clear();
  }

  /**
   * Connection management - prevents hanging connections  
   */
  addConnection(connection) {
    this.connections.add(connection);
    return connection;
  }

  closeConnection(connection) {
    if (connection.close) connection.close();
    if (connection.disconnect) connection.disconnect();
    if (connection.abort) connection.abort();
    this.connections.delete(connection);
  }

  closeAllConnections() {
    this.connections.forEach(conn => this.closeConnection(conn));
    this.connections.clear();
  }

  /**
   * Subscriber management - prevents memory leaks
   */
  addSubscriber(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }

  notifySubscribers(data) {
    this.subscribers.forEach(callback => {
      try {
        callback(data);
      } catch (error) {
        console.error(`Subscriber error in ${this.constructor.name}:`, error);
      }
    });
  }

  /**
   * Cleanup - call when service is no longer needed
   */
  async cleanup() {
    console.log(`🧹 Cleaning up ${this.constructor.name}...`);
    
    this.clearAllTimers();
    this.closeAllConnections();
    this.subscribers.clear();
    
    this.initialized = false;
  }

  /**
   * Service health check
   */
  async healthCheck() {
    if (!this.initialized) {
      return { healthy: false, reason: 'Not initialized' };
    }
    
    return { healthy: true, environment: this.getEnvironment() };
  }
}

/**
 * Factory function pattern - use this for service exports
 */
let serviceInstance = null;

const getStandardService = async () => {
  if (!serviceInstance) {
    serviceInstance = new StandardService();
    await serviceInstance.initialize();
  }
  return serviceInstance;
};

// Cleanup on process exit (Node.js) or page unload (browser)
if (typeof process !== 'undefined') {
  process.on('exit', () => {
    if (serviceInstance) serviceInstance.cleanup();
  });
} else if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    if (serviceInstance) serviceInstance.cleanup();
  });
}

export default getStandardService;
export { StandardService };