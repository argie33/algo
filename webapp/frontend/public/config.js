/**
 * Production Runtime Configuration
 * Generated automatically during deployment - DO NOT EDIT MANUALLY
 * Generated: 2025-07-23T16:27:50Z
 */

window.__CONFIG__ = {
  // Build Information
  BUILD_TIME: "2025-07-23T16:27:50Z",
  VERSION: "1.0.0",
  ENVIRONMENT: "dev",
  
  // API Configuration
  API: {
    BASE_URL: "https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev",
    VERSION: "v1",
    TIMEOUT: 30000,
    RETRY_ATTEMPTS: 3,
    RETRY_DELAY: 1000
  },
  
  // AWS Configuration
  AWS: {
    REGION: "us-east-1"
  },
  
  // Cognito Configuration
  COGNITO: {
    USER_POOL_ID: "us-east-1_ZqooNeQtV",
    CLIENT_ID: "243r98prucoickch12djkahrhk",
    REGION: "us-east-1",
    DOMAIN: "",
    REDIRECT_SIGN_IN: "${window.location.origin}",
    REDIRECT_SIGN_OUT: "${window.location.origin}"
  },
  
  // Feature Flags
  FEATURES: {
    AUTHENTICATION: true,
    COGNITO_AUTH: true,
    OAUTH_AUTH: false,
    BIOMETRIC_AUTH: false,
    
    TRADING: true,
    PAPER_TRADING: true,
    REAL_TRADING: false,
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
    
    DEVELOPMENT_FEATURES: false,
    DEBUG_MODE: false,
    MOCK_DATA: false,
    DEV_TOOLS: false
  },
  
  // External API Configuration
  EXTERNAL_APIS: {
    ALPACA: {
      BASE_URL: "https://paper-api.alpaca.markets",
      DATA_URL: "https://data.alpaca.markets",
      WS_URL: "wss://stream.data.alpaca.markets",
      IS_PAPER: true
    },
    POLYGON: {
      BASE_URL: "https://api.polygon.io",
      WS_URL: "wss://socket.polygon.io"
    },
    FMP: {
      BASE_URL: "https://financialmodelingprep.com/api"
    },
    FINNHUB: {
      BASE_URL: "https://finnhub.io/api/v1",
      WS_URL: "wss://ws.finnhub.io"
    }
  },
  
  // Performance Configuration
  PERFORMANCE: {
    CACHE: {
      ENABLED: true,
      TTL: {
        MARKET_DATA: 60000,
        PORTFOLIO: 300000,
        NEWS: 900000,
        STATIC: 3600000
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
    SESSION_TIMEOUT: 3600000,
    TOKEN_REFRESH_BEFORE: 300000,
    MAX_CONCURRENT_SESSIONS: 3,
    CSP_ENABLED: true,
    CSP_REPORT_ONLY: false
  },
  
  // Monitoring Configuration
  MONITORING: {
    LOGGING_ENABLED: true,
    LOG_LEVEL: "info",
    LOG_CONSOLE: true,
    LOG_REMOTE: false,
    ERROR_TRACKING_ENABLED: false,
    ANALYTICS_ENABLED: false
  }
};

// Environment-specific overrides
if (window.__CONFIG__.ENVIRONMENT === 'development') {
  window.__CONFIG__.FEATURES.DEBUG_MODE = true;
  window.__CONFIG__.FEATURES.MOCK_DATA = true;
  window.__CONFIG__.FEATURES.DEV_TOOLS = true;
  window.__CONFIG__.MONITORING.LOG_LEVEL = 'debug';
  window.__CONFIG__.SECURITY.CSP_REPORT_ONLY = true;
}

// Validation
window.__CONFIG__.validate = function() {
  const errors = [];
  const warnings = [];
  
  if (this.FEATURES.AUTHENTICATION && this.FEATURES.COGNITO_AUTH) {
    if (!this.COGNITO.USER_POOL_ID) {
      errors.push('COGNITO.USER_POOL_ID is required');
    }
    if (!this.COGNITO.CLIENT_ID) {
      errors.push('COGNITO.CLIENT_ID is required');
    }
  }
  
  if (!this.API.BASE_URL) {
    errors.push('API.BASE_URL is required');
  }
  
  return { errors, warnings, isValid: errors.length === 0 };
};

// Auto-validate
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
