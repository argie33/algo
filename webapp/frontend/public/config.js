/**
 * Runtime Configuration
 * This file is dynamically updated during deployment to eliminate hardcoded values
 */

window.__CONFIG__ = {
  // Build Information
  BUILD_TIME: "2025-07-23T00:00:00.000Z", // Updated during build
  VERSION: "1.0.0", // Updated during build
  ENVIRONMENT: (function() {
    // Auto-detect environment based on hostname
    const hostname = window.location.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'development';
    }
    if (hostname.includes('staging') || hostname.includes('dev')) {
      return 'staging';
    }
    return 'production';
  })(),
  
  // API Configuration (NO HARDCODED URLs)
  API: {
    BASE_URL: (function() {
      // Environment-based API URL selection
      const hostname = window.location.hostname;
      
      if (hostname === 'localhost' || hostname === '127.0.0.1') {
        // Development - use local backend or mock
        return 'http://localhost:3001/api';
      }
      
      if (hostname.includes('staging') || hostname.includes('dev')) {
        // Staging environment - will be replaced during deployment
        return 'https://api-staging.protrade-analytics.com';
      }
      
      // Production - will be replaced during deployment
      return 'https://api.protrade-analytics.com';
    })(),
    VERSION: 'v1',
    TIMEOUT: 30000,
    RETRY_ATTEMPTS: 3,
    RETRY_DELAY: 1000
  },
  
  // AWS Configuration (TO BE SET DURING DEPLOYMENT)
  AWS: {
    REGION: 'us-east-1' // Will be updated during deployment
  },
  
  // Cognito Configuration (MUST BE SET DURING DEPLOYMENT)
  COGNITO: {
    USER_POOL_ID: null, // CRITICAL: Must be set via deployment script
    CLIENT_ID: null,    // CRITICAL: Must be set via deployment script
    REGION: 'us-east-1',
    DOMAIN: null, // Optional OAuth domain
    REDIRECT_SIGN_IN: window.location.origin,
    REDIRECT_SIGN_OUT: window.location.origin
  },
  
  // Database Configuration (for reference, not used by frontend)
  DATABASE: {
    HOST: null, // Set during deployment
    PORT: 5432,
    NAME: 'protrade'
  },
  
  // Feature Flags (can be toggled without rebuilding)
  FEATURES: {
    AUTHENTICATION: true,
    COGNITO_AUTH: true,
    OAUTH_AUTH: false,
    BIOMETRIC_AUTH: false,
    
    TRADING: true,
    PAPER_TRADING: true,
    REAL_TRADING: false, // Only enable in production with proper controls
    CRYPTO_TRADING: false,
    OPTIONS_TRADING: false,
    
    AI_FEATURES: true,
    AI_SIGNALS: true,
    AI_PORTFOLIO_OPTIMIZATION: true,
    AI_RISK_ANALYSIS: true,
    
    DATA_FEATURES: true,
    REALTIME_DATA: true,
    HISTORICAL_DATA: true,
    NEWS_DATA: true,
    SOCIAL_SENTIMENT: false,
    
    UI_FEATURES: true,
    DARK_MODE: true,
    CUSTOM_THEMES: false,
    MOBILE_SUPPORT: true,
    ACCESSIBILITY: true,
    
    DEVELOPMENT_FEATURES: (function() {
      return window.location.hostname === 'localhost' || 
             window.location.hostname === '127.0.0.1';
    })(),
    DEBUG_MODE: false, // Will be set to true in development
    MOCK_DATA: false,  // Will be set to true in development
    DEV_TOOLS: false   // Will be set to true in development
  },
  
  // External API Configuration (keys set via environment variables)
  EXTERNAL_APIS: {
    ALPACA: {
      BASE_URL: 'https://paper-api.alpaca.markets',
      DATA_URL: 'https://data.alpaca.markets',
      WS_URL: 'wss://stream.data.alpaca.markets',
      IS_PAPER: true // Set to false for live trading in production
    },
    POLYGON: {
      BASE_URL: 'https://api.polygon.io',
      WS_URL: 'wss://socket.polygon.io'
    },
    FMP: {
      BASE_URL: 'https://financialmodelingprep.com/api'
    },
    FINNHUB: {
      BASE_URL: 'https://finnhub.io/api/v1',
      WS_URL: 'wss://ws.finnhub.io'
    },
    ALPHA_VANTAGE: {
      BASE_URL: 'https://www.alphavantage.co'
    },
    NEWS_API: {
      BASE_URL: 'https://newsapi.org/v2'
    }
  },
  
  // Performance Configuration
  PERFORMANCE: {
    CACHE: {
      ENABLED: true,
      TTL: {
        MARKET_DATA: 60000,    // 1 minute
        PORTFOLIO: 300000,     // 5 minutes  
        NEWS: 900000,          // 15 minutes
        STATIC: 3600000        // 1 hour
      }
    },
    RATE_LIMIT: {
      ENABLED: true,
      REQUESTS_PER_MINUTE: 100,
      REQUESTS_PER_HOUR: 1000,
      REQUESTS_PER_DAY: 10000
    },
    WEBSOCKET: {
      ENABLED: true,
      RECONNECT_INTERVAL: 5000,
      MAX_RECONNECT_ATTEMPTS: 10,
      HEARTBEAT_INTERVAL: 30000
    }
  },
  
  // Security Configuration
  SECURITY: {
    ENCRYPTION_ENABLED: true,
    SESSION_TIMEOUT: 3600000, // 1 hour
    TOKEN_REFRESH_BEFORE: 300000, // 5 minutes before expiry
    MAX_CONCURRENT_SESSIONS: 3,
    CSP_ENABLED: true,
    CSP_REPORT_ONLY: false
  },
  
  // Monitoring Configuration
  MONITORING: {
    LOGGING_ENABLED: true,
    LOG_LEVEL: 'info', // debug, info, warn, error
    LOG_CONSOLE: true,
    LOG_REMOTE: false,
    ERROR_TRACKING_ENABLED: false,
    ANALYTICS_ENABLED: false
  }
};

// Development Environment Overrides
if (window.__CONFIG__.ENVIRONMENT === 'development') {
  // Override settings for local development
  window.__CONFIG__.FEATURES.DEBUG_MODE = true;
  window.__CONFIG__.FEATURES.MOCK_DATA = true;
  window.__CONFIG__.FEATURES.DEV_TOOLS = true;
  window.__CONFIG__.MONITORING.LOG_LEVEL = 'debug';
  window.__CONFIG__.SECURITY.CSP_REPORT_ONLY = true;
  
  // Use development Cognito pool if available, otherwise disable
  if (!window.__CONFIG__.COGNITO.USER_POOL_ID) {
    console.warn('⚠️ No Cognito configuration found for development');
    // Don't set dummy values - let the app handle gracefully
  }
}

// Validation function
window.__CONFIG__.validate = function() {
  const errors = [];
  const warnings = [];
  
  // Check required Cognito configuration
  if (this.FEATURES.AUTHENTICATION && this.FEATURES.COGNITO_AUTH) {
    if (!this.COGNITO.USER_POOL_ID) {
      errors.push('COGNITO.USER_POOL_ID is required when authentication is enabled');
    }
    if (!this.COGNITO.CLIENT_ID) {
      errors.push('COGNITO.CLIENT_ID is required when authentication is enabled');
    }
  }
  
  // Check API configuration
  if (!this.API.BASE_URL || this.API.BASE_URL.includes('example.com')) {
    warnings.push('API.BASE_URL should be set to the actual API endpoint');
  }
  
  // Environment-specific checks
  if (this.ENVIRONMENT === 'production') {
    if (this.FEATURES.DEBUG_MODE) {
      warnings.push('DEBUG_MODE should be disabled in production');
    }
    if (this.FEATURES.MOCK_DATA) {
      warnings.push('MOCK_DATA should be disabled in production');
    }
    if (this.MONITORING.LOG_LEVEL === 'debug') {
      warnings.push('LOG_LEVEL should not be debug in production');
    }
  }
  
  return { errors, warnings, isValid: errors.length === 0 };
};

// Auto-validate configuration
setTimeout(() => {
  const validation = window.__CONFIG__.validate();
  
  if (validation.errors.length > 0) {
    console.error('❌ Configuration Errors:', validation.errors);
  }
  
  if (validation.warnings.length > 0) {
    console.warn('⚠️ Configuration Warnings:', validation.warnings);
  }
  
  if (validation.isValid) {
    console.log('✅ Configuration validated successfully');
  }
}, 100);