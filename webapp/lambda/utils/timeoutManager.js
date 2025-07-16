/**
 * External API Timeout Management Utility
 * Provides standardized timeout configurations and utilities for all external service calls
 * Optimized for Lambda environment with consistent error handling
 */

// Standard timeout configurations for different service types
const TIMEOUT_CONFIGS = {
  // Database operations
  database: {
    connect: 15000,     // 15 seconds - database connection
    query: 10000,       // 10 seconds - standard query
    transaction: 30000, // 30 seconds - complex transactions
    healthCheck: 5000   // 5 seconds - health checks
  },

  // External API calls
  api: {
    fast: 5000,         // 5 seconds - simple data requests
    standard: 10000,    // 10 seconds - standard API calls
    slow: 15000,        // 15 seconds - complex operations
    upload: 30000,      // 30 seconds - file uploads
    download: 45000     // 45 seconds - file downloads
  },

  // Broker/Trading APIs (mission-critical)
  trading: {
    quotes: 8000,       // 8 seconds - real-time quotes
    orders: 12000,      // 12 seconds - order placement
    positions: 10000,   // 10 seconds - position retrieval
    history: 15000,     // 15 seconds - trade history
    account: 10000      // 10 seconds - account info
  },

  // Market data services
  market_data: {
    realtime: 8000,     // 8 seconds - real-time data
    historical: 15000,  // 15 seconds - historical data
    news: 10000,        // 10 seconds - news feeds
    calendar: 5000,     // 5 seconds - market calendar
    fundamental: 12000  // 12 seconds - fundamental data
  },

  // Authentication services
  auth: {
    login: 10000,       // 10 seconds - login operations
    token_verify: 5000, // 5 seconds - token verification
    refresh: 8000,      // 8 seconds - token refresh
    logout: 3000        // 3 seconds - logout
  },

  // AWS services
  aws: {
    secrets: 10000,     // 10 seconds - secrets manager
    cognito: 8000,      // 8 seconds - cognito operations
    s3: 15000,          // 15 seconds - S3 operations
    lambda: 25000       // 25 seconds - lambda invocations
  }
};

/**
 * Create a promise that rejects after specified timeout
 */
function createTimeoutPromise(timeoutMs, operation = 'operation') {
  return new Promise((_, reject) => {
    setTimeout(() => {
      const error = new Error(`${operation} timeout after ${timeoutMs}ms`);
      error.code = 'TIMEOUT';
      error.timeout = timeoutMs;
      error.operation = operation;
      reject(error);
    }, timeoutMs);
  });
}

/**
 * Wrap a promise with timeout functionality
 */
function withTimeout(promise, timeoutMs, operation = 'operation') {
  return Promise.race([
    promise,
    createTimeoutPromise(timeoutMs, operation)
  ]);
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
 * Get timeout for specific service and operation
 */
function getTimeout(service, operation = 'standard') {
  const serviceConfig = TIMEOUT_CONFIGS[service];
  if (!serviceConfig) {
    console.warn(`Unknown service '${service}', using default timeout`);
    return TIMEOUT_CONFIGS.api.standard;
  }

  const timeout = serviceConfig[operation];
  if (!timeout) {
    console.warn(`Unknown operation '${operation}' for service '${service}', using standard timeout`);
    return serviceConfig.standard || TIMEOUT_CONFIGS.api.standard;
  }

  return timeout;
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
 * Create a timeout-aware fetch wrapper
 */
function createTimeoutFetch(defaultTimeout = 10000) {
  return async (url, options = {}) => {
    const timeout = options.timeout || defaultTimeout;
    const controller = new AbortController();
    
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      
      if (error.name === 'AbortError') {
        const timeoutError = new Error(`Fetch timeout after ${timeout}ms`);
        timeoutError.code = 'TIMEOUT';
        timeoutError.timeout = timeout;
        throw timeoutError;
      }
      
      throw error;
    }
  };
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
  TIMEOUT_CONFIGS
};