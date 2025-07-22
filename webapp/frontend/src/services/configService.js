/**
 * UNIFIED CONFIGURATION SERVICE
 * Completes the "started but not finished" configuration system
 * 
 * PRIORITY ORDER (highest to lowest):
 * 1. Runtime config (window.__CONFIG__) - allows production overrides
 * 2. Environment variables (process.env, import.meta.env) - build-time config
 * 3. Default values - fallback for all environments
 */

import { StandardService } from './_serviceTemplate.js';

class ConfigService extends StandardService {
  constructor() {
    super();
    this.configCache = new Map();
    this.watchers = new Map();
    this.validationRules = new Map();
    this.required = new Set();
  }

  /**
   * Initialize configuration service
   */
  async initializeForBrowser() {
    await this.loadConfiguration();
    this.setupConfigWatcher();
    console.log('🔧 Configuration service initialized for browser');
  }

  async initializeForTest() {
    await this.loadConfiguration();
    console.log('🧪 Configuration service initialized for test environment');
  }

  async initializeForServer() {
    await this.loadConfiguration();
    console.log('🖥️ Configuration service initialized for server (SSR)');
  }

  /**
   * Load configuration from all sources with proper priority
   */
  async loadConfiguration() {
    const config = {};

    // 1. Start with defaults (lowest priority)
    this.applyDefaults(config);

    // 2. Apply environment variables (medium priority)
    this.applyEnvironmentVariables(config);

    // 3. Apply runtime config (highest priority)
    this.applyRuntimeConfig(config);

    // 4. Validate required configuration
    this.validateConfiguration(config);

    // 5. Cache the configuration
    this.configCache.clear();
    Object.entries(config).forEach(([key, value]) => {
      this.configCache.set(key, value);
    });

    console.log('✅ Configuration loaded:', this.getSafeConfigForLogging());
  }

  /**
   * Apply default configuration values
   */
  applyDefaults(config) {
    // API Configuration
    config.API_URL = 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev';
    config.API_TIMEOUT = 30000;
    config.API_RETRIES = 3;

    // WebSocket Configuration  
    config.WS_URL = null; // Will be derived from API_URL if not set
    config.WS_RECONNECT_DELAY = 5000;
    config.WS_MAX_RETRIES = 5;

    // Feature Flags
    config.FEATURES_REALTIME_DATA = true;
    config.FEATURES_ANALYTICS = true;
    config.FEATURES_SPEECH = true;
    config.FEATURES_OFFLINE_MODE = false;

    // Performance Settings
    config.CACHE_TTL = 300000; // 5 minutes
    config.POLLING_INTERVAL = 5000;
    config.BATCH_SIZE = 100;

    // Debug Settings
    config.DEBUG_MODE = false;
    config.LOG_LEVEL = 'warn';
    config.PERFORMANCE_MONITORING = false;

    // Environment Detection
    config.ENVIRONMENT = this.detectEnvironment();
  }

  /**
   * Apply environment variables (process.env, import.meta.env)
   */
  applyEnvironmentVariables(config) {
    const envMappings = {
      // API Configuration
      'API_URL': ['VITE_API_URL', 'REACT_APP_API_URL', 'API_URL'],
      'API_TIMEOUT': ['VITE_API_TIMEOUT', 'API_TIMEOUT'],
      'API_RETRIES': ['VITE_API_RETRIES', 'API_RETRIES'],

      // WebSocket Configuration
      'WS_URL': ['VITE_WS_URL', 'REACT_APP_WEBSOCKET_ENDPOINT', 'WS_URL'],
      'WS_RECONNECT_DELAY': ['VITE_WS_RECONNECT_DELAY', 'WS_RECONNECT_DELAY'],

      // Feature Flags  
      'FEATURES_REALTIME_DATA': ['VITE_ENABLE_REALTIME', 'ENABLE_REALTIME'],
      'FEATURES_ANALYTICS': ['VITE_ENABLE_ANALYTICS', 'ENABLE_ANALYTICS'],
      'FEATURES_SPEECH': ['VITE_ENABLE_SPEECH', 'ENABLE_SPEECH'],

      // Performance
      'CACHE_TTL': ['VITE_CACHE_TTL', 'CACHE_TTL'],
      'POLLING_INTERVAL': ['VITE_POLLING_INTERVAL', 'POLLING_INTERVAL'],

      // Debug
      'DEBUG_MODE': ['VITE_DEBUG', 'DEBUG', 'NODE_ENV'],
      'LOG_LEVEL': ['VITE_LOG_LEVEL', 'LOG_LEVEL'],
    };

    Object.entries(envMappings).forEach(([configKey, envKeys]) => {
      for (const envKey of envKeys) {
        let value = this.getEnvironmentVariable(envKey);
        
        if (value !== null && value !== undefined) {
          // Special handling for specific keys
          if (configKey === 'DEBUG_MODE' && envKey === 'NODE_ENV') {
            value = value === 'development';
          } else if (typeof config[configKey] === 'boolean') {
            value = this.parseBoolean(value);
          } else if (typeof config[configKey] === 'number') {
            value = parseInt(value, 10);
          }
          
          config[configKey] = value;
          break; // Use first available value
        }
      }
    });
  }

  /**
   * Apply runtime configuration (window.__CONFIG__)
   */
  applyRuntimeConfig(config) {
    if (this.isServerEnvironment()) return; // No window in SSR

    try {
      if (typeof window !== 'undefined' && window.__CONFIG__) {
        const runtimeConfig = window.__CONFIG__;
        
        // Direct mappings
        if (runtimeConfig.API_URL) config.API_URL = runtimeConfig.API_URL;
        if (runtimeConfig.WS_URL) config.WS_URL = runtimeConfig.WS_URL;
        if (runtimeConfig.DEBUG_MODE !== undefined) config.DEBUG_MODE = runtimeConfig.DEBUG_MODE;
        
        // Feature flags
        if (runtimeConfig.features) {
          Object.entries(runtimeConfig.features).forEach(([key, value]) => {
            const configKey = `FEATURES_${key.toUpperCase()}`;
            if (config.hasOwnProperty(configKey)) {
              config[configKey] = value;
            }
          });
        }

        console.log('🔧 Applied runtime configuration overrides');
      }
    } catch (error) {
      console.warn('⚠️ Failed to apply runtime configuration:', error);
    }
  }

  /**
   * Get environment variable from all possible sources
   */
  getEnvironmentVariable(key) {
    // Try import.meta.env first (Vite)
    if (typeof import !== 'undefined' && import.meta?.env?.[key]) {
      return import.meta.env[key];
    }

    // Try process.env (Node.js)
    if (typeof process !== 'undefined' && process.env?.[key]) {
      return process.env[key];
    }

    return null;
  }

  /**
   * Parse boolean values from strings
   */
  parseBoolean(value) {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'string') {
      return value.toLowerCase() === 'true' || value === '1';
    }
    return Boolean(value);
  }

  /**
   * Detect current environment
   */
  detectEnvironment() {
    if (this.isTestEnvironment()) return 'test';
    if (this.isServerEnvironment()) return 'server';
    
    // Check for development indicators
    if (this.getEnvironmentVariable('NODE_ENV') === 'development') return 'development';
    if (this.getEnvironmentVariable('VITE_DEV') === 'true') return 'development';
    if (typeof window !== 'undefined' && window.location?.hostname === 'localhost') return 'development';
    
    return 'production';
  }

  /**
   * Validate required configuration
   */
  validateConfiguration(config) {
    // Mark required fields
    this.required.add('API_URL');
    
    // Check required fields
    const missing = [];
    this.required.forEach(key => {
      if (!config[key] || config[key] === '') {
        missing.push(key);
      }
    });

    if (missing.length > 0) {
      throw new Error(`Missing required configuration: ${missing.join(', ')}`);
    }

    // Validate specific values
    if (config.API_URL && !this.isValidUrl(config.API_URL)) {
      throw new Error(`Invalid API_URL: ${config.API_URL}`);
    }

    // Derive WS_URL if not set
    if (!config.WS_URL && config.API_URL) {
      config.WS_URL = `${config.API_URL}/websocket`;
    }
  }

  /**
   * Validate URL format
   */
  isValidUrl(url) {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Get configuration value
   */
  get(key, defaultValue = null) {
    if (!this.initialized) {
      console.warn(`⚠️ Configuration not initialized, using default for ${key}`);
      return defaultValue;
    }
    
    return this.configCache.get(key) ?? defaultValue;
  }

  /**
   * Get all configuration (safe for logging)
   */
  getSafeConfigForLogging() {
    const config = {};
    this.configCache.forEach((value, key) => {
      // Mask sensitive values
      if (key.includes('API_KEY') || key.includes('SECRET') || key.includes('TOKEN')) {
        config[key] = '***masked***';
      } else {
        config[key] = value;
      }
    });
    return config;
  }

  /**
   * Watch for configuration changes
   */
  watch(key, callback) {
    if (!this.watchers.has(key)) {
      this.watchers.set(key, new Set());
    }
    this.watchers.get(key).add(callback);
    
    // Return unwatch function
    return () => {
      this.watchers.get(key)?.delete(callback);
    };
  }

  /**
   * Set up configuration file watcher (browser only)
   */
  setupConfigWatcher() {
    if (!this.isBrowserEnvironment()) return;

    // Watch for window.__CONFIG__ changes
    if (typeof window !== 'undefined') {
      const checkConfigChanges = () => {
        // Simple polling approach - could be enhanced with MutationObserver
        setTimeout(() => {
          if (this.isConnected) {
            this.loadConfiguration().catch(console.error);
            checkConfigChanges();
          }
        }, 30000); // Check every 30 seconds
      };
      
      checkConfigChanges();
    }
  }

  /**
   * Enhanced cleanup
   */
  async cleanup() {
    this.configCache.clear();
    this.watchers.clear();
    this.validationRules.clear();
    this.required.clear();
    
    await super.cleanup();
  }

  /**
   * Configuration health check
   */
  async healthCheck() {
    const baseHealth = await super.healthCheck();
    if (!baseHealth.healthy) return baseHealth;

    const requiredPresent = Array.from(this.required).every(key => 
      this.configCache.has(key) && this.configCache.get(key)
    );

    return {
      healthy: requiredPresent,
      environment: this.getEnvironment(),
      configCount: this.configCache.size,
      requiredCount: this.required.size,
      reason: requiredPresent ? 'All required config present' : 'Missing required configuration'
    };
  }
}

// Factory function
let configServiceInstance = null;

const getConfigService = async () => {
  if (!configServiceInstance) {
    configServiceInstance = new ConfigService();
    await configServiceInstance.initialize();
  }
  return configServiceInstance;
};

// Cleanup
if (typeof process !== 'undefined') {
  process.on('exit', () => {
    if (configServiceInstance) configServiceInstance.cleanup();
  });
} else if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    if (configServiceInstance) configServiceInstance.cleanup();
  });
}

export default getConfigService;
export { ConfigService };