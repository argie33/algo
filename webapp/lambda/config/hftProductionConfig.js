/**
 * HFT Production Configuration
 * Production settings for High Frequency Trading system
 */

const config = {
  // Environment settings
  environment: process.env.NODE_ENV || 'development',
  
  // Database configuration
  database: {
    host: process.env.DB_HOST || 'localhost',
    port: process.env.DB_PORT || 5432,
    database: process.env.DB_NAME || 'financial_webapp',
    user: process.env.DB_USER || 'postgres',
    password: process.env.DB_PASSWORD,
    ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false,
    pool: {
      min: 2,
      max: 20,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 2000
    }
  },

  // Alpaca API configuration
  alpaca: {
    // Production endpoints
    baseUrl: 'https://api.alpaca.markets',
    dataUrl: 'https://data.alpaca.markets',
    websocketUrl: 'wss://stream.data.alpaca.markets/v2/iex',
    
    // Paper trading endpoints (for testing)
    paperBaseUrl: 'https://paper-api.alpaca.markets',
    paperDataUrl: 'https://data.alpaca.markets', // Same for both
    paperWebsocketUrl: 'wss://stream.data.alpaca.markets/v2/iex',
    
    // Rate limits (requests per minute)
    rateLimits: {
      orders: 200,
      data: 200,
      account: 200
    },
    
    // Connection settings
    timeout: 30000, // 30 seconds
    retryAttempts: 3,
    retryDelay: 1000 // 1 second
  },

  // WebSocket configuration
  websocket: {
    // Connection settings
    connectionTimeout: 10000, // 10 seconds
    heartbeatInterval: 30000, // 30 seconds
    reconnectDelay: 5000, // 5 seconds
    maxReconnectAttempts: 10,
    
    // Message handling
    messageTimeout: 5000, // 5 seconds
    maxMessageSize: 65536, // 64KB
    compressionEnabled: true,
    
    // Providers
    providers: {
      alpaca: {
        url: process.env.ALPACA_WS_URL || 'wss://stream.data.alpaca.markets/v2/iex',
        priority: 1,
        maxSymbols: 300
      },
      polygon: {
        url: process.env.POLYGON_WS_URL || 'wss://socket.polygon.io/stocks',
        priority: 2,
        maxSymbols: 100
      },
      finnhub: {
        url: process.env.FINNHUB_WS_URL || 'wss://ws.finnhub.io',
        priority: 3,
        maxSymbols: 50
      }
    }
  },

  // HFT engine settings
  hft: {
    // Performance thresholds
    maxLatencyMs: 50, // Maximum acceptable latency
    targetLatencyMs: 25, // Target latency for HFT
    maxExecutionTimeMs: 100, // Maximum order execution time
    
    // Risk management
    maxPositionsPerUser: 10,
    maxDailyLossPerUser: 5000, // USD
    maxPositionSize: 10000, // USD
    emergencyStopThreshold: 0.1, // 10% account loss
    
    // Strategy limits
    maxStrategiesPerUser: 5,
    maxSymbolsPerStrategy: 20,
    
    // Execution settings
    defaultTimeInForce: 'IOC', // Immediate or Cancel
    allowMarketOrders: true,
    allowLimitOrders: true,
    requirePositionLimits: true,
    
    // Data requirements
    minDataPoints: 20, // Minimum historical data points
    dataValidityMs: 5000, // Data considered stale after 5 seconds
    
    // Circuit breakers
    circuitBreaker: {
      enabled: true,
      failureThreshold: 5, // Failures before circuit opens
      resetTimeoutMs: 60000, // 1 minute
      halfOpenMaxCalls: 3
    }
  },

  // Position synchronization
  positionSync: {
    enabled: true,
    intervalMs: 30000, // 30 seconds
    batchSize: 50,
    maxDiscrepancyPercent: 1, // 1% variance allowed
    alertThresholdPercent: 5, // 5% variance triggers alert
    retryAttempts: 3
  },

  // AI recommendation engine
  ai: {
    enabled: true,
    models: {
      momentum: {
        enabled: true,
        confidence: 0.75,
        lookbackPeriod: 20
      },
      meanReversion: {
        enabled: true,
        confidence: 0.68,
        lookbackPeriod: 50
      },
      volumeAnalysis: {
        enabled: true,
        confidence: 0.72,
        lookbackPeriod: 30
      },
      sentiment: {
        enabled: false, // Disabled in production until API integration
        confidence: 0.65
      }
    },
    maxRecommendations: 20,
    minConfidence: 0.6,
    cacheTimeoutMs: 300000 // 5 minutes
  },

  // Logging configuration
  logging: {
    level: process.env.LOG_LEVEL || 'info',
    format: 'json',
    
    // Log retention
    maxFiles: 30,
    maxSize: '100MB',
    
    // Log categories
    categories: {
      hft: 'info',
      websocket: 'warn',
      database: 'warn',
      api: 'info',
      performance: 'info'
    },
    
    // Performance logging
    logExecutionTimes: true,
    logDatabaseQueries: false, // Disable in production for performance
    logWebSocketMessages: false // Disable to prevent log spam
  },

  // Security settings
  security: {
    // API keys encryption
    apiKeyEncryption: {
      algorithm: 'aes-256-gcm',
      keyRotationDays: 90
    },
    
    // JWT settings
    jwt: {
      expirationHours: 24,
      refreshExpirationDays: 30
    },
    
    // Rate limiting
    rateLimiting: {
      windowMs: 60000, // 1 minute
      maxRequests: 100,
      skipSuccessfulRequests: false
    },
    
    // CORS settings
    cors: {
      origin: process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:3000'],
      credentials: true
    }
  },

  // Monitoring and alerts
  monitoring: {
    // Performance metrics
    collectMetrics: true,
    metricsIntervalMs: 60000, // 1 minute
    
    // Health checks
    healthCheck: {
      enabled: true,
      intervalMs: 30000, // 30 seconds
      timeoutMs: 10000 // 10 seconds
    },
    
    // Alerts
    alerts: {
      enabled: true,
      channels: {
        email: process.env.ALERT_EMAIL,
        webhook: process.env.ALERT_WEBHOOK_URL
      },
      thresholds: {
        highLatency: 100, // ms
        highErrorRate: 0.05, // 5%
        lowSuccessRate: 0.9, // 90%
        connectionFailures: 5
      }
    }
  },

  // AWS configuration
  aws: {
    region: process.env.AWS_REGION || 'us-east-1',
    
    // Secrets Manager
    secretsManager: {
      enabled: true,
      secretPrefix: 'hft/',
      refreshIntervalMs: 3600000 // 1 hour
    },
    
    // CloudWatch
    cloudWatch: {
      enabled: true,
      namespace: 'HFT/TradingSystem',
      logGroup: '/aws/lambda/hft-trading'
    },
    
    // SNS for alerts
    sns: {
      enabled: true,
      topicArn: process.env.SNS_ALERT_TOPIC_ARN
    }
  },

  // Cache configuration
  cache: {
    // Redis settings (if available)
    redis: {
      enabled: process.env.REDIS_URL ? true : false,
      url: process.env.REDIS_URL,
      keyPrefix: 'hft:',
      defaultTTL: 300 // 5 minutes
    },
    
    // In-memory cache fallback
    memory: {
      maxSize: 1000,
      ttlMs: 300000 // 5 minutes
    }
  },

  // Feature flags
  features: {
    paperTradingMode: process.env.PAPER_TRADING_MODE === 'true',
    enablePositionSync: true,
    enableAIRecommendations: true,
    enableRealTimeData: true,
    enableRiskManagement: true,
    enablePerformanceTracking: true,
    enableWebSocketFallback: true,
    enableCircuitBreaker: true
  }
};

// Environment-specific overrides
if (config.environment === 'production') {
  // Production-specific settings
  config.logging.level = 'warn';
  config.logging.logDatabaseQueries = false;
  config.logging.logWebSocketMessages = false;
  
  config.hft.maxLatencyMs = 25; // Stricter latency in production
  config.hft.targetLatencyMs = 10;
  
  config.features.paperTradingMode = false; // Disable paper trading in production
}

if (config.environment === 'development') {
  // Development-specific settings
  config.logging.level = 'debug';
  config.logging.logDatabaseQueries = true;
  config.logging.logWebSocketMessages = true;
  
  config.features.paperTradingMode = true; // Enable paper trading in development
  
  // Relaxed limits for development
  config.hft.maxLatencyMs = 100;
  config.hft.targetLatencyMs = 50;
}

if (config.environment === 'test') {
  // Test-specific settings
  config.database.database = 'financial_webapp_test';
  config.positionSync.enabled = false;
  config.monitoring.alerts.enabled = false;
  config.features.enableRealTimeData = false;
}

// Validation
function validateConfig() {
  const required = [
    'database.host',
    'database.database'
  ];
  
  for (const path of required) {
    const value = path.split('.').reduce((obj, key) => obj && obj[key], config);
    if (!value) {
      throw new Error(`Required configuration missing: ${path}`);
    }
  }
  
  // Validate numeric values
  if (config.hft.maxLatencyMs <= 0) {
    throw new Error('HFT max latency must be positive');
  }
  
  if (config.hft.maxPositionsPerUser <= 0) {
    throw new Error('Max positions per user must be positive');
  }
}

// Export configuration
module.exports = {
  ...config,
  validate: validateConfig,
  
  // Helper functions
  isDevelopment: () => config.environment === 'development',
  isProduction: () => config.environment === 'production',
  isTest: () => config.environment === 'test',
  
  // Get provider config
  getProviderConfig: (provider) => config.websocket.providers[provider],
  
  // Get alert threshold
  getAlertThreshold: (metric) => config.monitoring.alerts.thresholds[metric],
  
  // Check feature flag
  isFeatureEnabled: (feature) => config.features[feature] === true
};