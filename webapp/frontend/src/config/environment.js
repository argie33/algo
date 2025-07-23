/**
 * Centralized Environment Configuration
 * Eliminates hardcoded values and provides a single source of truth for all configuration
 */

// Environment detection
export const NODE_ENV = import.meta.env.NODE_ENV || 'development';
export const IS_DEVELOPMENT = NODE_ENV === 'development';
export const IS_PRODUCTION = NODE_ENV === 'production';
export const IS_TEST = NODE_ENV === 'test';

// App Configuration
export const APP_CONFIG = {
  name: 'ProTrade Analytics',
  version: import.meta.env.VITE_APP_VERSION || '1.0.0',
  description: 'Advanced Financial Trading Platform',
  url: import.meta.env.VITE_APP_URL || window.location.origin,
  
  // Contact and Support
  support: {
    email: import.meta.env.VITE_SUPPORT_EMAIL || 'support@protrade.com',
    phone: import.meta.env.VITE_SUPPORT_PHONE || '+1-800-PROTRADE'
  }
};

// AWS Configuration
export const AWS_CONFIG = {
  region: import.meta.env.VITE_AWS_REGION || 'us-east-1',
  
  // API Gateway Configuration
  api: {
    baseUrl: import.meta.env.VITE_API_BASE_URL || 
             window.__CONFIG__?.API?.BASE_URL ||
             'https://api.protrade.com',
    version: import.meta.env.VITE_API_VERSION || 'v1',
    timeout: parseInt(import.meta.env.VITE_API_TIMEOUT) || 30000,
    retryAttempts: parseInt(import.meta.env.VITE_API_RETRY_ATTEMPTS) || 3,
    retryDelay: parseInt(import.meta.env.VITE_API_RETRY_DELAY) || 1000
  },
  
  // Cognito Configuration - will be loaded dynamically from runtime API
  cognito: {
    userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || 
               window.__CONFIG__?.COGNITO?.USER_POOL_ID ||
               window.__RUNTIME_CONFIG__?.cognito?.userPoolId ||
               null, // No fallback - must be configured
    clientId: import.meta.env.VITE_COGNITO_CLIENT_ID || 
              window.__CONFIG__?.COGNITO?.CLIENT_ID ||
              window.__RUNTIME_CONFIG__?.cognito?.clientId ||
              null, // No fallback - must be configured
    domain: import.meta.env.VITE_COGNITO_DOMAIN || 
            window.__CONFIG__?.COGNITO?.DOMAIN ||
            window.__RUNTIME_CONFIG__?.cognito?.domain ||
            '',
    redirectSignIn: import.meta.env.VITE_COGNITO_REDIRECT_SIGN_IN || 
                    window.__CONFIG__?.COGNITO?.REDIRECT_SIGN_IN ||
                    window.location.origin,
    redirectSignOut: import.meta.env.VITE_COGNITO_REDIRECT_SIGN_OUT || 
                     window.__CONFIG__?.COGNITO?.REDIRECT_SIGN_OUT ||
                     window.location.origin
  },
  
  // S3 Configuration
  s3: {
    bucket: import.meta.env.VITE_S3_BUCKET || 
            window.__CONFIG__?.S3?.BUCKET ||
            'protrade-user-data',
    region: import.meta.env.VITE_S3_REGION || 
            window.__CONFIG__?.S3?.REGION ||
            'us-east-1'
  },
  
  // Lambda Configuration
  lambda: {
    region: import.meta.env.VITE_LAMBDA_REGION || 
            window.__CONFIG__?.LAMBDA?.REGION ||
            'us-east-1'
  }
};

// External API Configuration
export const EXTERNAL_APIS = {
  // Alpaca Trading API
  alpaca: {
    baseUrl: import.meta.env.VITE_ALPACA_BASE_URL || 'https://paper-api.alpaca.markets',
    dataUrl: import.meta.env.VITE_ALPACA_DATA_URL || 'https://data.alpaca.markets',
    websocketUrl: import.meta.env.VITE_ALPACA_WS_URL || 'wss://stream.data.alpaca.markets',
    apiKeyId: import.meta.env.VITE_ALPACA_API_KEY_ID || null,
    secretKey: import.meta.env.VITE_ALPACA_SECRET_KEY || null,
    isPaper: import.meta.env.VITE_ALPACA_IS_PAPER !== 'false'
  },
  
  // Polygon.io Market Data
  polygon: {
    baseUrl: import.meta.env.VITE_POLYGON_BASE_URL || 'https://api.polygon.io',
    websocketUrl: import.meta.env.VITE_POLYGON_WS_URL || 'wss://socket.polygon.io',
    apiKey: import.meta.env.VITE_POLYGON_API_KEY || null
  },
  
  // Financial Modeling Prep
  fmp: {
    baseUrl: import.meta.env.VITE_FMP_BASE_URL || 'https://financialmodelingprep.com/api',
    apiKey: import.meta.env.VITE_FMP_API_KEY || null
  },
  
  // Finnhub
  finnhub: {
    baseUrl: import.meta.env.VITE_FINNHUB_BASE_URL || 'https://finnhub.io/api/v1',
    websocketUrl: import.meta.env.VITE_FINNHUB_WS_URL || 'wss://ws.finnhub.io',
    apiKey: import.meta.env.VITE_FINNHUB_API_KEY || null
  },
  
  // Alpha Vantage
  alphaVantage: {
    baseUrl: import.meta.env.VITE_ALPHA_VANTAGE_BASE_URL || 'https://www.alphavantage.co',
    apiKey: import.meta.env.VITE_ALPHA_VANTAGE_API_KEY || null
  },
  
  // News API
  newsApi: {
    baseUrl: import.meta.env.VITE_NEWS_API_BASE_URL || 'https://newsapi.org/v2',
    apiKey: import.meta.env.VITE_NEWS_API_KEY || null
  },
  
  // Yahoo Finance (unofficial)
  yahooFinance: {
    baseUrl: import.meta.env.VITE_YAHOO_FINANCE_BASE_URL || 'https://query1.finance.yahoo.com',
    // No API key required for basic endpoints
  }
};

// Database Configuration
export const DATABASE_CONFIG = {
  rds: {
    host: import.meta.env.VITE_RDS_HOST || 
          window.__CONFIG__?.DATABASE?.HOST ||
          'localhost',
    port: parseInt(import.meta.env.VITE_RDS_PORT) || 
          parseInt(window.__CONFIG__?.DATABASE?.PORT) || 
          5432,
    database: import.meta.env.VITE_RDS_DATABASE || 
              window.__CONFIG__?.DATABASE?.NAME ||
              'protrade',
    ssl: import.meta.env.VITE_RDS_SSL !== 'false'
  }
};

// Redis Configuration
export const REDIS_CONFIG = {
  host: import.meta.env.VITE_REDIS_HOST || 
        window.__CONFIG__?.REDIS?.HOST ||
        'localhost',
  port: parseInt(import.meta.env.VITE_REDIS_PORT) || 
        parseInt(window.__CONFIG__?.REDIS?.PORT) || 
        6379,
  ssl: import.meta.env.VITE_REDIS_SSL !== 'false'
};

// Feature Flags
export const FEATURES = {
  // Core Features
  authentication: {
    enabled: import.meta.env.VITE_FEATURE_AUTH !== 'false',
    methods: {
      cognito: import.meta.env.VITE_FEATURE_COGNITO !== 'false',
      oauth: import.meta.env.VITE_FEATURE_OAUTH === 'true',
      biometric: import.meta.env.VITE_FEATURE_BIOMETRIC === 'true'
    }
  },
  
  // Trading Features
  trading: {
    enabled: import.meta.env.VITE_FEATURE_TRADING !== 'false',
    paperTrading: import.meta.env.VITE_FEATURE_PAPER_TRADING !== 'false',
    realTrading: import.meta.env.VITE_FEATURE_REAL_TRADING === 'true',
    cryptoTrading: import.meta.env.VITE_FEATURE_CRYPTO_TRADING === 'true',
    optionsTrading: import.meta.env.VITE_FEATURE_OPTIONS_TRADING === 'true'
  },
  
  // Data Features
  data: {
    realTimeData: import.meta.env.VITE_FEATURE_REALTIME_DATA !== 'false',
    historicalData: import.meta.env.VITE_FEATURE_HISTORICAL_DATA !== 'false',
    newsData: import.meta.env.VITE_FEATURE_NEWS_DATA !== 'false',
    socialSentiment: import.meta.env.VITE_FEATURE_SOCIAL_SENTIMENT === 'true'
  },
  
  // AI Features
  ai: {
    enabled: import.meta.env.VITE_FEATURE_AI !== 'false',
    tradingSignals: import.meta.env.VITE_FEATURE_AI_SIGNALS !== 'false',
    portfolioOptimization: import.meta.env.VITE_FEATURE_AI_PORTFOLIO === 'true',
    riskAnalysis: import.meta.env.VITE_FEATURE_AI_RISK === 'true',
    sentimentAnalysis: import.meta.env.VITE_FEATURE_AI_SENTIMENT === 'true'
  },
  
  // Analytics Features
  analytics: {
    enabled: import.meta.env.VITE_FEATURE_ANALYTICS !== 'false',
    performance: import.meta.env.VITE_FEATURE_PERFORMANCE === 'true',
    risk: import.meta.env.VITE_FEATURE_RISK === 'true',
    backtesting: import.meta.env.VITE_FEATURE_BACKTESTING === 'true'
  },
  
  // UI Features
  ui: {
    darkMode: import.meta.env.VITE_FEATURE_DARK_MODE !== 'false',
    customThemes: import.meta.env.VITE_FEATURE_CUSTOM_THEMES === 'true',
    accessibility: import.meta.env.VITE_FEATURE_ACCESSIBILITY !== 'false',
    mobile: import.meta.env.VITE_FEATURE_MOBILE !== 'false'
  },
  
  // Development Features
  development: {
    debugMode: import.meta.env.VITE_DEBUG_MODE === 'true' || IS_DEVELOPMENT,
    mockData: import.meta.env.VITE_MOCK_DATA === 'true' || IS_DEVELOPMENT,
    testMode: import.meta.env.VITE_TEST_MODE === 'true' || IS_TEST,
    devTools: import.meta.env.VITE_DEV_TOOLS === 'true' || IS_DEVELOPMENT
  }
};

// Performance Configuration
export const PERFORMANCE_CONFIG = {
  // Caching
  cache: {
    enabled: import.meta.env.VITE_CACHE_ENABLED !== 'false',
    ttl: {
      marketData: parseInt(import.meta.env.VITE_CACHE_MARKET_DATA_TTL) || 60000, // 1 minute
      portfolio: parseInt(import.meta.env.VITE_CACHE_PORTFOLIO_TTL) || 300000, // 5 minutes
      news: parseInt(import.meta.env.VITE_CACHE_NEWS_TTL) || 900000, // 15 minutes
      static: parseInt(import.meta.env.VITE_CACHE_STATIC_TTL) || 3600000 // 1 hour
    }
  },
  
  // Rate Limiting
  rateLimit: {
    enabled: import.meta.env.VITE_RATE_LIMIT_ENABLED !== 'false',
    requests: {
      perMinute: parseInt(import.meta.env.VITE_RATE_LIMIT_PER_MINUTE) || 100,
      perHour: parseInt(import.meta.env.VITE_RATE_LIMIT_PER_HOUR) || 1000,
      perDay: parseInt(import.meta.env.VITE_RATE_LIMIT_PER_DAY) || 10000
    }
  },
  
  // WebSocket Configuration
  websocket: {
    enabled: import.meta.env.VITE_WEBSOCKET_ENABLED !== 'false',
    reconnectInterval: parseInt(import.meta.env.VITE_WS_RECONNECT_INTERVAL) || 5000,
    maxReconnectAttempts: parseInt(import.meta.env.VITE_WS_MAX_RECONNECT) || 10,
    heartbeatInterval: parseInt(import.meta.env.VITE_WS_HEARTBEAT_INTERVAL) || 30000
  }
};

// Security Configuration
export const SECURITY_CONFIG = {
  // Encryption
  encryption: {
    enabled: import.meta.env.VITE_ENCRYPTION_ENABLED !== 'false',
    algorithm: import.meta.env.VITE_ENCRYPTION_ALGORITHM || 'AES-256-GCM'
  },
  
  // CSP (Content Security Policy)
  csp: {
    enabled: import.meta.env.VITE_CSP_ENABLED !== 'false',
    reportOnly: import.meta.env.VITE_CSP_REPORT_ONLY === 'true'
  },
  
  // Session Management
  session: {
    timeout: parseInt(import.meta.env.VITE_SESSION_TIMEOUT) || 3600000, // 1 hour
    renewBeforeExpiry: parseInt(import.meta.env.VITE_SESSION_RENEW_BEFORE) || 300000, // 5 minutes
    maxConcurrentSessions: parseInt(import.meta.env.VITE_MAX_CONCURRENT_SESSIONS) || 3
  }
};

// Monitoring Configuration
export const MONITORING_CONFIG = {
  // Logging
  logging: {
    enabled: import.meta.env.VITE_LOGGING_ENABLED !== 'false',
    level: import.meta.env.VITE_LOG_LEVEL || (IS_DEVELOPMENT ? 'debug' : 'info'),
    console: import.meta.env.VITE_LOG_CONSOLE !== 'false',
    remote: import.meta.env.VITE_LOG_REMOTE === 'true'
  },
  
  // Error Tracking
  errorTracking: {
    enabled: import.meta.env.VITE_ERROR_TRACKING === 'true',
    dsn: import.meta.env.VITE_SENTRY_DSN || null,
    environment: NODE_ENV
  },
  
  // Analytics
  analytics: {
    enabled: import.meta.env.VITE_ANALYTICS_ENABLED === 'true',
    trackingId: import.meta.env.VITE_GA_TRACKING_ID || null
  }
};

// Validation Functions
export const validateConfig = () => {
  const errors = [];
  const warnings = [];
  
  // Required AWS Configuration
  if (!AWS_CONFIG.cognito.userPoolId) {
    errors.push('AWS Cognito User Pool ID is required (VITE_COGNITO_USER_POOL_ID)');
  }
  
  if (!AWS_CONFIG.cognito.clientId) {
    errors.push('AWS Cognito Client ID is required (VITE_COGNITO_CLIENT_ID)');
  }
  
  // API Configuration
  if (!AWS_CONFIG.api.baseUrl || AWS_CONFIG.api.baseUrl === 'https://api.protrade.com') {
    warnings.push('Using default API base URL - set VITE_API_BASE_URL for production');
  }
  
  // External API Keys
  if (!EXTERNAL_APIS.alpaca.apiKeyId && FEATURES.trading.enabled) {
    warnings.push('Alpaca API key not configured - trading features may not work');
  }
  
  if (!EXTERNAL_APIS.polygon.apiKey && FEATURES.data.realTimeData) {
    warnings.push('Polygon API key not configured - real-time data may not work');
  }
  
  return { errors, warnings };
};

// Helper Functions
export const getApiUrl = (endpoint = '') => {
  const baseUrl = AWS_CONFIG.api.baseUrl.replace(/\/$/, ''); // Remove trailing slash
  const version = AWS_CONFIG.api.version;
  const cleanEndpoint = endpoint.replace(/^\//, ''); // Remove leading slash
  
  return `${baseUrl}/${version}/${cleanEndpoint}`;
};

export const getExternalApiUrl = (provider, endpoint = '') => {
  const config = EXTERNAL_APIS[provider];
  if (!config) {
    throw new Error(`Unknown API provider: ${provider}`);
  }
  
  const baseUrl = config.baseUrl.replace(/\/$/, '');
  const cleanEndpoint = endpoint.replace(/^\//, '');
  
  return `${baseUrl}/${cleanEndpoint}`;
};

export const isFeatureEnabled = (featurePath) => {
  const keys = featurePath.split('.');
  let current = FEATURES;
  
  for (const key of keys) {
    if (current[key] === undefined) {
      return false;
    }
    current = current[key];
  }
  
  return current === true;
};

// Development Helpers
export const logConfig = () => {
  if (IS_DEVELOPMENT && FEATURES.development.debugMode) {
    console.group('📋 Environment Configuration');
    console.log('Environment:', NODE_ENV);
    console.log('App Config:', APP_CONFIG);
    console.log('AWS Config:', AWS_CONFIG);
    console.log('Features:', FEATURES);
    console.log('Performance:', PERFORMANCE_CONFIG);
    console.groupEnd();
    
    const { errors, warnings } = validateConfig();
    
    if (errors.length > 0) {
      console.group('❌ Configuration Errors');
      errors.forEach(error => console.error(error));
      console.groupEnd();
    }
    
    if (warnings.length > 0) {
      console.group('⚠️ Configuration Warnings');
      warnings.forEach(warning => console.warn(warning));
      console.groupEnd();
    }
  }
};

// Initialize configuration logging in development
if (IS_DEVELOPMENT) {
  setTimeout(logConfig, 100);
}

export default {
  NODE_ENV,
  IS_DEVELOPMENT,
  IS_PRODUCTION,
  IS_TEST,
  APP_CONFIG,
  AWS_CONFIG,
  EXTERNAL_APIS,
  DATABASE_CONFIG,
  REDIS_CONFIG,
  FEATURES,
  PERFORMANCE_CONFIG,
  SECURITY_CONFIG,
  MONITORING_CONFIG,
  validateConfig,
  getApiUrl,
  getExternalApiUrl,
  isFeatureEnabled,
  logConfig
};