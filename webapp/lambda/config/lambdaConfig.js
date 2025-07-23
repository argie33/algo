/**
 * Lambda-Optimized Configuration - SuperClaude's Performance Fix
 * Addresses cold start and timeout issues
 */

const isLambda = !!process.env.AWS_LAMBDA_FUNCTION_NAME;
const environment = process.env.NODE_ENV || 'production';

/**
 * Lambda-optimized timeouts accounting for cold starts
 */
const timeoutConfig = {
  // Base timeouts (increased for Lambda cold starts)
  database: {
    cold: 15000,    // 15s for cold start
    warm: 8000,     // 8s for warm instances
    query: 5000     // 5s for individual queries
  },
  
  // External API timeouts
  external: {
    alpaca: 20000,      // 20s for trading API
    news: 12000,        // 12s for news APIs
    sentiment: 10000,   // 10s for sentiment analysis
    general: 15000      // 15s for general external APIs
  },
  
  // Lambda-specific timeouts
  lambda: {
    total: 890000,      // 14min 50s (Lambda max is 15min)
    healthCheck: 10000, // 10s for health checks
    startup: 30000,     // 30s for cold start initialization
    cleanup: 5000       // 5s for cleanup operations
  },
  
  // Circuit breaker settings
  circuitBreaker: {
    failureThreshold: 5,        // Open after 5 failures
    recoveryTimeout: 60000,     // 1 minute recovery time
    monitoringPeriod: 300000,   // 5 minute monitoring window
    halfOpenMaxCalls: 3         // Max calls in half-open state
  }
};

/**
 * Database connection pool configuration for Lambda
 */
const databaseConfig = {
  // Connection pool settings optimized for Lambda
  pool: {
    max: isLambda ? 5 : 10,             // Fewer connections in Lambda
    min: isLambda ? 1 : 2,              // Minimum connections
    acquireTimeoutMillis: timeoutConfig.database.cold,
    createTimeoutMillis: timeoutConfig.database.cold + 5000,
    destroyTimeoutMillis: 5000,
    idleTimeoutMillis: isLambda ? 60000 : 30000,  // Longer idle for Lambda
    reapIntervalMillis: 10000,          // Less frequent reaping
    createRetryIntervalMillis: 500,     // Longer retry interval
    keepAlive: true,
    keepAliveInitialDelayMillis: 15000
  },
  
  // Connection retry configuration
  retry: {
    attempts: 3,
    delay: 1000,
    backoff: 'exponential'
  }
};

/**
 * Memory and resource management
 */
const resourceConfig = {
  // Memory management
  memory: {
    maxHeapUsed: isLambda ? 0.8 : 0.9,    // 80% max in Lambda
    gcInterval: 30000,                     // 30s GC interval
    memoryWarningThreshold: 0.75           // Warning at 75%
  },
  
  // Request handling
  request: {
    maxConcurrent: isLambda ? 10 : 50,    // Fewer concurrent in Lambda
    queueTimeout: 30000,                   // 30s queue timeout
    bodyLimit: '2mb'                       // 2MB body limit
  }
};

/**
 * Error handling configuration
 */
const errorConfig = {
  // HTTP status code mappings
  statusCodes: {
    timeout: 504,           // Gateway timeout
    circuitOpen: 503,       // Service unavailable
    dbConnection: 503,      // Service unavailable
    validation: 400,        // Bad request
    authentication: 401,    // Unauthorized
    authorization: 403,     // Forbidden
    notFound: 404,         // Not found
    internal: 500          // Internal server error
  },
  
  // Error response configuration
  response: {
    includeStack: environment === 'development',
    includeDiagnostics: environment !== 'production',
    correlationId: true,
    timestamp: true
  }
};

/**
 * Feature flags for gradual rollout
 */
const featureFlags = {
  enhancedCors: true,
  circuitBreaker: true,
  requestQueuing: true,
  memoryMonitoring = true,
  performanceLogging: environment !== 'production'
};

/**
 * Get timeout based on Lambda state (cold vs warm)
 */
function getTimeout(operation, category = 'database') {
  const config = timeoutConfig[category];
  if (!config) return timeoutConfig.lambda.total;
  
  // Detect cold start (simple heuristic)
  const isColdStart = process.uptime() < 30; // Less than 30s uptime
  
  if (category === 'database') {
    return isColdStart ? config.cold : config.warm;
  }
  
  return config[operation] || config.general || 15000;
}

/**
 * Get configuration for specific environment
 */
function getConfig() {
  return {
    timeouts: timeoutConfig,
    database: databaseConfig,
    resources: resourceConfig,
    errors: errorConfig,
    features: featureFlags,
    environment: {
      isLambda,
      environment,
      region: process.env.AWS_REGION || 'us-east-1',
      functionName: process.env.AWS_LAMBDA_FUNCTION_NAME || 'unknown'
    }
  };
}

module.exports = {
  timeoutConfig,
  databaseConfig,
  resourceConfig,
  errorConfig,
  featureFlags,
  getTimeout,
  getConfig,
  isLambda
};