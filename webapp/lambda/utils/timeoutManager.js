/**
 * External API Timeout Management Utility
 * Provides standardized timeout configurations and utilities for all external service calls
 * Optimized for Lambda environment with consistent error handling
 */

// UNIFIED TIMEOUT HIERARCHY - Coordinated with UnifiedDatabaseManager
// Lambda constraint: 25s max execution time
// Timeout hierarchy: Lambda 25s > Circuit 20s > Database 18s > External APIs 15s
const TIMEOUT_CONFIGS = {
  // Lambda execution limits
  lambda: {
    max: 25000,         // Maximum Lambda execution time (with 2s buffer)
    circuit: 20000,     // Circuit breaker timeout (< lambda max)
    cleanup: 2000       // Time reserved for cleanup operations
  },

  // Database operations (must be < circuit timeout)
  database: {
    connect: 8000,      // 8 seconds - database connection (REDUCED)
    query: 12000,       // 12 seconds - standard query (INCREASED for stability)
    transaction: 18000, // 18 seconds - complex transactions (REDUCED)
    healthCheck: 5000   // 5 seconds - health checks
  },

  // External API calls (must be < database timeouts)
  api: {
    fast: 5000,         // 5 seconds - simple data requests
    standard: 10000,    // 10 seconds - standard API calls
    slow: 15000,        // 15 seconds - complex operations (REDUCED)
    upload: 15000,      // 15 seconds - file uploads (REDUCED from 30s)
    download: 20000     // 20 seconds - file downloads (REDUCED from 45s)
  },

  // Broker/Trading APIs (mission-critical, must be < api.slow)
  trading: {
    quotes: 6000,       // 6 seconds - real-time quotes (REDUCED)
    orders: 10000,      // 10 seconds - order placement (REDUCED)
    positions: 8000,    // 8 seconds - position retrieval (REDUCED)
    history: 12000,     // 12 seconds - trade history (REDUCED)
    account: 8000,      // 8 seconds - account info (REDUCED)
    portfolio: 14000,   // 14 seconds - portfolio performance (REDUCED to be < api.slow)
    performance: 14000, // 14 seconds - performance metrics (REDUCED to be < api.slow)
    standard: 8000      // 8 seconds - standard operations (REDUCED)
  },

  // Market data services (must be < trading timeouts)
  market_data: {
    realtime: 6000,     // 6 seconds - real-time data (REDUCED)
    historical: 12000,  // 12 seconds - historical data (REDUCED)
    news: 8000,         // 8 seconds - news feeds (REDUCED)
    calendar: 5000,     // 5 seconds - market calendar
    fundamental: 10000  // 10 seconds - fundamental data (REDUCED)
  },

  // Authentication services (must be fast)
  auth: {
    login: 8000,        // 8 seconds - login operations (REDUCED)
    token_verify: 3000, // 3 seconds - token verification (REDUCED)
    refresh: 5000,      // 5 seconds - token refresh (REDUCED)
    logout: 2000        // 2 seconds - logout (REDUCED)
  },

  // AWS services (must be < database timeouts)
  aws: {
    secrets: 6000,      // 6 seconds - secrets manager (REDUCED)
    cognito: 6000,      // 6 seconds - cognito operations (REDUCED)
    s3: 10000,          // 10 seconds - S3 operations (REDUCED)
    lambda: 22000       // 22 seconds - lambda invocations (REDUCED)
  }
};

/**
 * Create a promise that rejects after specified timeout with proper cleanup
 */
function createTimeoutPromise(timeoutMs, operation = 'operation') {
  let timeoutId;
  const promise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      const error = new Error(`${operation} timeout after ${timeoutMs}ms`);
      error.code = 'TIMEOUT';
      error.timeout = timeoutMs;
      error.operation = operation;
      reject(error);
    }, timeoutMs);
  });
  
  // Add cleanup method to promise
  promise.cleanup = () => {
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  };
  
  return promise;
}

/**
 * Wrap a promise with timeout functionality and proper cleanup
 */
function withTimeout(promise, timeoutMs, operation = 'operation') {
  const timeoutPromise = createTimeoutPromise(timeoutMs, operation);
  
  const racePromise = Promise.race([
    promise.then(result => {
      // Clear timeout on success
      if (timeoutPromise.cleanup) {
        timeoutPromise.cleanup();
      }
      return result;
    }).catch(error => {
      // Clear timeout on error
      if (timeoutPromise.cleanup) {
        timeoutPromise.cleanup();
      }
      throw error;
    }),
    timeoutPromise
  ]);
  
  // Add cleanup method to race promise
  racePromise.cleanup = () => {
    if (timeoutPromise.cleanup) {
      timeoutPromise.cleanup();
    }
  };
  
  return racePromise;
}

/**
 * Create a timeout wrapper for async functions
 */
function createTimeoutWrapper(timeoutMs, operation = 'operation') {
  return (asyncFunction) => {
    return async (...args) => {
      return withTimeout(asyncFunction(...args), timeoutMs, operation);
    };
  };
}

/**
 * Execute multiple operations with individual timeouts
 */
async function executeWithTimeouts(operations) {
  const results = await Promise.allSettled(
    operations.map(({ promise, timeout, operation }) => 
      withTimeout(promise, timeout, operation)
    )
  );

  return results.map((result, index) => ({
    operation: operations[index].operation,
    timeout: operations[index].timeout,
    status: result.status,
    value: result.status === 'fulfilled' ? result.value : undefined,
    error: result.status === 'rejected' ? result.reason : undefined
  }));
}

/**
 * Standardized external API call wrapper with timeout and retry logic
 */
async function callExternalApi(config) {
  const {
    apiCall,           // Function that returns a promise
    service,           // Service name (e.g., 'alpaca', 'cognito')
    operation,         // Operation name (e.g., 'getQuotes', 'login')
    timeout,           // Timeout in milliseconds
    retries = 0,       // Number of retries
    retryDelay = 1000, // Delay between retries
    logger = null,     // Optional logger instance
    requestId = null   // Optional request ID for correlation
  } = config;

  const operationName = `${service}.${operation}`;
  let lastError;

  for (let attempt = 0; attempt <= retries; attempt++) {
    const startTime = Date.now();
    
    try {
      if (logger) {
        logger.info(`External API call started: ${operationName}`, {
          attempt: attempt + 1,
          maxAttempts: retries + 1,
          timeout,
          service,
          operation
        });
      }

      const result = await withTimeout(apiCall(), timeout, operationName);
      const duration = Date.now() - startTime;

      if (logger) {
        logger.info(`External API call succeeded: ${operationName}`, {
          duration,
          attempt: attempt + 1,
          service,
          operation
        });
      }

      return {
        success: true,
        result,
        duration,
        attempts: attempt + 1,
        service,
        operation
      };

    } catch (error) {
      const duration = Date.now() - startTime;
      lastError = error;

      if (logger) {
        logger.warn(`External API call failed: ${operationName}`, {
          error: error.message,
          duration,
          attempt: attempt + 1,
          maxAttempts: retries + 1,
          service,
          operation,
          errorCode: error.code,
          isTimeout: error.code === 'TIMEOUT'
        });
      }

      // If this was the last attempt, break
      if (attempt === retries) {
        break;
      }

      // Wait before retry (with exponential backoff)
      const delay = retryDelay * Math.pow(2, attempt);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }

  // All attempts failed
  const totalDuration = Date.now() - (Date.now() - (retries + 1) * 1000); // Approximate
  
  if (logger) {
    logger.error(`External API call failed after all attempts: ${operationName}`, {
      error: lastError.message,
      totalAttempts: retries + 1,
      totalDuration,
      service,
      operation
    });
  }

  return {
    success: false,
    error: lastError,
    attempts: retries + 1,
    service,
    operation
  };
}

/**
 * Get timeout for specific service and operation with hierarchy validation
 */
function getTimeout(service, operation = 'standard') {
  const serviceConfig = TIMEOUT_CONFIGS[service];
  if (!serviceConfig) {
    console.warn(`⚠️ Unknown service '${service}', using default timeout`);
    return TIMEOUT_CONFIGS.api.standard;
  }

  const timeout = serviceConfig[operation];
  if (!timeout) {
    console.warn(`⚠️ Unknown operation '${operation}' for service '${service}', using standard timeout`);
    return serviceConfig.standard || TIMEOUT_CONFIGS.api.standard;
  }

  // Validate timeout doesn't exceed Lambda limits
  if (timeout > TIMEOUT_CONFIGS.lambda.max) {
    console.warn(`⚠️ Timeout ${timeout}ms exceeds Lambda limit ${TIMEOUT_CONFIGS.lambda.max}ms, reducing`);
    return TIMEOUT_CONFIGS.lambda.max - TIMEOUT_CONFIGS.lambda.cleanup;
  }

  return timeout;
}

/**
 * Get coordinated timeouts for database operations
 */
function getDatabaseTimeouts() {
  return {
    connection: TIMEOUT_CONFIGS.database.connect,
    query: TIMEOUT_CONFIGS.database.query,
    transaction: TIMEOUT_CONFIGS.database.transaction,
    healthCheck: TIMEOUT_CONFIGS.database.healthCheck,
    circuit: TIMEOUT_CONFIGS.lambda.circuit
  };
}

/**
 * Get timeout hierarchy for debugging and validation
 */
function getTimeoutHierarchy() {
  return {
    lambda: TIMEOUT_CONFIGS.lambda.max,
    circuit: TIMEOUT_CONFIGS.lambda.circuit,
    database: TIMEOUT_CONFIGS.database.transaction,
    api: TIMEOUT_CONFIGS.api.slow,
    trading: Math.max(...Object.values(TIMEOUT_CONFIGS.trading)),
    cleanup: TIMEOUT_CONFIGS.lambda.cleanup
  };
}

/**
 * Validate timeout hierarchy - ensures no timeouts exceed their parents
 */
function validateTimeoutHierarchy() {
  const issues = [];
  const hierarchy = getTimeoutHierarchy();
  
  // Check circuit breaker doesn't exceed Lambda
  if (hierarchy.circuit >= hierarchy.lambda) {
    issues.push(`Circuit timeout (${hierarchy.circuit}ms) >= Lambda timeout (${hierarchy.lambda}ms)`);
  }
  
  // Check database doesn't exceed circuit
  if (hierarchy.database >= hierarchy.circuit) {
    issues.push(`Database timeout (${hierarchy.database}ms) >= Circuit timeout (${hierarchy.circuit}ms)`);
  }
  
  // Check API doesn't exceed database
  if (hierarchy.api >= hierarchy.database) {
    issues.push(`API timeout (${hierarchy.api}ms) >= Database timeout (${hierarchy.database}ms)`);
  }
  
  // Check trading doesn't exceed API
  if (hierarchy.trading >= hierarchy.api) {
    issues.push(`Trading timeout (${hierarchy.trading}ms) >= API timeout (${hierarchy.api}ms)`);
  }
  
  if (issues.length > 0) {
    console.error('❌ Timeout hierarchy validation failed:', issues);
    return { valid: false, issues };
  }
  
  console.log('✅ Timeout hierarchy validation passed');
  return { valid: true, hierarchy };
}

/**
 * Database operation wrapper with standardized timeouts
 */
async function withDatabaseTimeout(operation, operationType = 'query', logger = null) {
  const timeout = getTimeout('database', operationType);
  const operationName = `database.${operationType}`;
  
  if (logger) {
    logger.debug(`Database operation started: ${operationName}`, { timeout });
  }

  const startTime = Date.now();
  
  try {
    const result = await withTimeout(operation, timeout, operationName);
    const duration = Date.now() - startTime;
    
    if (logger) {
      logger.debug(`Database operation completed: ${operationName}`, { duration });
    }
    
    return result;
  } catch (error) {
    const duration = Date.now() - startTime;
    
    if (logger) {
      logger.error(`Database operation failed: ${operationName}`, {
        error: error.message,
        duration,
        isTimeout: error.code === 'TIMEOUT'
      });
    }
    
    throw error;
  }
}

/**
 * Trading API wrapper with standardized timeouts and error handling
 */
async function withTradingTimeout(operation, operationType = 'standard', logger = null) {
  const timeout = getTimeout('trading', operationType);
  const operationName = `trading.${operationType}`;
  
  return callExternalApi({
    apiCall: operation,
    service: 'trading',
    operation: operationType,
    timeout,
    retries: 1, // Trading operations get one retry
    retryDelay: 500,
    logger
  });
}

/**
 * Market data API wrapper with standardized timeouts
 */
async function withMarketDataTimeout(operation, operationType = 'realtime', logger = null) {
  const timeout = getTimeout('market_data', operationType);
  const operationName = `market_data.${operationType}`;
  
  return callExternalApi({
    apiCall: operation,
    service: 'market_data',
    operation: operationType,
    timeout,
    retries: 2, // Market data gets more retries
    retryDelay: 1000,
    logger
  });
}

/**
 * AWS service wrapper with standardized timeouts
 */
async function withAwsTimeout(operation, operationType = 'standard', logger = null) {
  const timeout = getTimeout('aws', operationType);
  const operationName = `aws.${operationType}`;
  
  return callExternalApi({
    apiCall: operation,
    service: 'aws',
    operation: operationType,
    timeout,
    retries: 1,
    retryDelay: 1000,
    logger
  });
}

/**
 * Authentication service wrapper with standardized timeouts
 */
async function withAuthTimeout(operation, operationType = 'login', logger = null) {
  const timeout = getTimeout('auth', operationType);
  const operationName = `auth.${operationType}`;
  
  return callExternalApi({
    apiCall: operation,
    service: 'auth',
    operation: operationType,
    timeout,
    retries: 1,
    retryDelay: 500,
    logger
  });
}

/**
 * Create a timeout-aware fetch wrapper with proper cleanup
 */
function createTimeoutFetch(defaultTimeout = 10000) {
  const activeFetches = new Set();
  
  const fetchWithTimeout = async (url, options = {}) => {
    const timeout = options.timeout || defaultTimeout;
    const controller = new AbortController();
    
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    activeFetches.add(timeoutId);
    
    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      activeFetches.delete(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      activeFetches.delete(timeoutId);
      
      if (error.name === 'AbortError') {
        const timeoutError = new Error(`Fetch timeout after ${timeout}ms`);
        timeoutError.code = 'TIMEOUT';
        timeoutError.timeout = timeout;
        throw timeoutError;
      }
      
      throw error;
    }
  };
  
  // Add cleanup method
  fetchWithTimeout.cleanup = () => {
    for (const timeoutId of activeFetches) {
      clearTimeout(timeoutId);
    }
    activeFetches.clear();
  };
  
  return fetchWithTimeout;
}

module.exports = {
  // Core timeout utilities
  withTimeout,
  createTimeoutPromise,
  createTimeoutWrapper,
  executeWithTimeouts,
  
  // Service-specific wrappers
  withDatabaseTimeout,
  withTradingTimeout,
  withMarketDataTimeout,
  withAwsTimeout,
  withAuthTimeout,
  
  // External API utilities
  callExternalApi,
  createTimeoutFetch,
  
  // Configuration utilities
  getTimeout,
  getDatabaseTimeouts,
  getTimeoutHierarchy,
  validateTimeoutHierarchy,
  TIMEOUT_CONFIGS
};