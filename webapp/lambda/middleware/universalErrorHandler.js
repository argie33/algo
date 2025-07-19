/**
 * Universal Error Handler - Comprehensive Error Handling Strategy
 * Provides consistent error handling across all routes and services
 */

// Import logger with fallback for testing
let getLogger;
try {
  const loggerModule = require('../utils/logger');
  getLogger = loggerModule.getLogger || (() => ({
    info: console.log,
    warn: console.warn,
    error: console.error
  }));
} catch (error) {
  // Fallback logger for testing
  getLogger = () => ({
    info: console.log,
    warn: console.warn,
    error: console.error,
    getCorrelationId: () => 'test-correlation-id'
  });
}

/**
 * Universal async route wrapper - ensures all async routes have proper error handling
 */
function asyncHandler(fn) {
  return (req, res, next) => {
    const promise = fn(req, res, next);
    
    if (promise && typeof promise.catch === 'function') {
      promise.catch((error) => {
        // Enhance error with request context
        error.requestContext = {
          method: req.method,
          path: req.path,
          params: req.params,
          query: req.query,
          userAgent: req.headers['user-agent'],
          correlationId: req.correlationId,
          userId: req.user?.sub,
          timestamp: new Date().toISOString()
        };
        
        next(error);
      });
    }
    
    return promise;
  };
}

/**
 * Enhanced error context collector
 */
function enrichErrorContext(error, req, additionalContext = {}) {
  const logger = getLogger();
  const timestamp = Date.now();
  
  return {
    // Core error information
    name: error.name,
    message: error.message,
    stack: error.stack,
    
    // Request context
    request: {
      method: req.method,
      path: req.path,
      params: req.params,
      query: req.query,
      headers: {
        'user-agent': req.headers['user-agent'],
        'content-type': req.headers['content-type'],
        'origin': req.headers.origin
      },
      correlationId: req.correlationId,
      timestamp: new Date().toISOString()
    },
    
    // User context (if available)
    user: req.user ? {
      id: req.user.sub,
      email: req.user.email,
      roles: req.user.roles
    } : null,
    
    // Performance context
    performance: {
      requestStartTime: req.startTime,
      duration: req.startTime ? timestamp - req.startTime : null
    },
    
    // Additional context
    ...additionalContext,
    
    // Error categorization
    category: categorizeError(error),
    severity: determineSeverity(error),
    recoverable: isRecoverable(error)
  };
}

/**
 * Categorize errors for better handling
 */
function categorizeError(error) {
  const message = error.message?.toLowerCase() || '';
  const code = error.code || error.status;
  
  // Circuit breaker errors (check first to prioritize over database)
  if (message.includes('circuit breaker')) {
    return 'CIRCUIT_BREAKER_ERROR';
  }
  
  // Database errors (check before timeout to prioritize database-specific timeouts)
  if (error.name === 'DatabaseError' || message.includes('database') || message.includes('postgresql')) {
    return 'DATABASE_ERROR';
  }
  
  // Timeout errors (more specific patterns)
  if (error.name === 'TimeoutError' || 
      (message.includes('timeout') && !message.includes('database')) ||
      message.includes('timed out') ||
      message.includes('request timeout')) {
    return 'TIMEOUT_ERROR';
  }
  
  // Authentication errors
  if (code === 401 || message.includes('unauthorized') || message.includes('token') || message.includes('jwt')) {
    return 'AUTHENTICATION_ERROR';
  }
  
  // Authorization errors
  if (code === 403 || message.includes('forbidden') || message.includes('permission')) {
    return 'AUTHORIZATION_ERROR';
  }
  
  // Validation errors
  if (code === 400 || message.includes('validation') || message.includes('invalid')) {
    return 'VALIDATION_ERROR';
  }
  
  // External service errors (more specific patterns)
  if (message.includes('alpaca') || 
      message.includes('external service') || 
      (message.includes('api') && !message.includes('api key'))) {
    return 'EXTERNAL_SERVICE_ERROR';
  }
  
  // Rate limiting errors
  if (code === 429 || message.includes('rate limit') || message.includes('too many')) {
    return 'RATE_LIMIT_ERROR';
  }
  
  // Business logic errors
  if (code >= 400 && code < 500) {
    return 'BUSINESS_LOGIC_ERROR';
  }
  
  // Server errors
  if (code >= 500) {
    return 'SERVER_ERROR';
  }
  
  return 'UNKNOWN_ERROR';
}

/**
 * Determine error severity
 */
function determineSeverity(error) {
  const category = categorizeError(error);
  const code = error.code || error.status;
  
  // Critical severity
  if (['DATABASE_ERROR', 'SERVER_ERROR'].includes(category)) {
    return 'CRITICAL';
  }
  
  // High severity
  if (['EXTERNAL_SERVICE_ERROR', 'CIRCUIT_BREAKER_ERROR'].includes(category)) {
    return 'HIGH';
  }
  
  // Medium severity
  if (['AUTHENTICATION_ERROR', 'AUTHORIZATION_ERROR', 'TIMEOUT_ERROR'].includes(category)) {
    return 'MEDIUM';
  }
  
  // Low severity
  if (['VALIDATION_ERROR', 'RATE_LIMIT_ERROR', 'BUSINESS_LOGIC_ERROR'].includes(category)) {
    return 'LOW';
  }
  
  return 'UNKNOWN';
}

/**
 * Determine if error is recoverable
 */
function isRecoverable(error) {
  const category = categorizeError(error);
  
  // Recoverable errors
  const recoverableCategories = [
    'TIMEOUT_ERROR',
    'RATE_LIMIT_ERROR', 
    'EXTERNAL_SERVICE_ERROR',
    'CIRCUIT_BREAKER_ERROR'
  ];
  
  return recoverableCategories.includes(category);
}

/**
 * Generate user-friendly error messages
 */
function generateUserMessage(error, category) {
  const userMessages = {
    'DATABASE_ERROR': 'We\'re experiencing technical difficulties. Please try again in a few moments.',
    'AUTHENTICATION_ERROR': 'Your session has expired. Please log in again.',
    'AUTHORIZATION_ERROR': 'You don\'t have permission to perform this action.',
    'VALIDATION_ERROR': 'Please check your input and try again.',
    'EXTERNAL_SERVICE_ERROR': 'Our trading partner is temporarily unavailable. Please try again shortly.',
    'RATE_LIMIT_ERROR': 'You\'ve made too many requests. Please wait a moment before trying again.',
    'TIMEOUT_ERROR': 'The request took too long to complete. Please try again.',
    'CIRCUIT_BREAKER_ERROR': 'This service is temporarily unavailable for maintenance.',
    'BUSINESS_LOGIC_ERROR': error.message || 'Invalid operation.',
    'SERVER_ERROR': 'We\'re experiencing technical issues. Our team has been notified.',
    'UNKNOWN_ERROR': 'An unexpected error occurred. Please try again.'
  };
  
  return userMessages[category] || userMessages['UNKNOWN_ERROR'];
}

/**
 * Enhanced error response formatter
 */
function formatErrorResponse(error, req, additionalContext = {}) {
  const enrichedContext = enrichErrorContext(error, req, additionalContext);
  const category = enrichedContext.category;
  const severity = enrichedContext.severity;
  
  // Determine response status code
  let statusCode = error.status || error.code || 500;
  
  // Override status codes based on category
  const statusCodeMapping = {
    'AUTHENTICATION_ERROR': 401,
    'AUTHORIZATION_ERROR': 403,
    'VALIDATION_ERROR': 400,
    'RATE_LIMIT_ERROR': 429,
    'DATABASE_ERROR': 503,
    'EXTERNAL_SERVICE_ERROR': 503,
    'CIRCUIT_BREAKER_ERROR': 503,
    'TIMEOUT_ERROR': 504,
    'SERVER_ERROR': 500
  };
  
  statusCode = statusCodeMapping[category] || statusCode;
  
  // Generate response
  const response = {
    success: false,
    error: {
      code: category,
      message: generateUserMessage(error, category),
      severity: severity.toLowerCase(),
      recoverable: enrichedContext.recoverable,
      correlationId: req.correlationId
    },
    timestamp: enrichedContext.request.timestamp
  };
  
  // Add details in development environment
  if (process.env.NODE_ENV === 'development') {
    response.error.details = {
      originalMessage: error.message,
      stack: error.stack,
      context: enrichedContext
    };
  }
  
  // Add retry information for recoverable errors
  if (enrichedContext.recoverable) {
    response.error.retryAfter = getRetryDelay(category);
    response.error.recovery = getRecoveryInstructions(category);
  }
  
  return { statusCode, response };
}

/**
 * Get retry delay for recoverable errors
 */
function getRetryDelay(category) {
  const retryDelays = {
    'TIMEOUT_ERROR': 5000,        // 5 seconds
    'RATE_LIMIT_ERROR': 60000,    // 1 minute
    'EXTERNAL_SERVICE_ERROR': 30000, // 30 seconds
    'CIRCUIT_BREAKER_ERROR': 60000   // 1 minute
  };
  
  return retryDelays[category] || 10000;
}

/**
 * Get recovery instructions for users
 */
function getRecoveryInstructions(category) {
  const instructions = {
    'TIMEOUT_ERROR': 'Try refreshing the page or reducing the data range.',
    'RATE_LIMIT_ERROR': 'Please wait a moment before making more requests.',
    'EXTERNAL_SERVICE_ERROR': 'Check our status page for updates on partner services.',
    'CIRCUIT_BREAKER_ERROR': 'This service will be restored automatically. Please check back soon.'
  };
  
  return instructions[category];
}

/**
 * Log error with enhanced context
 */
function logError(error, req, additionalContext = {}) {
  const logger = req.logger || getLogger();
  const enrichedContext = enrichErrorContext(error, req, additionalContext);
  
  // Log based on severity
  switch (enrichedContext.severity) {
    case 'CRITICAL':
      logger.error('Critical error occurred', enrichedContext);
      break;
    case 'HIGH':
      logger.error('High severity error', enrichedContext);
      break;
    case 'MEDIUM':
      logger.warn('Medium severity error', enrichedContext);
      break;
    case 'LOW':
      logger.info('Low severity error', enrichedContext);
      break;
    default:
      logger.error('Unknown severity error', enrichedContext);
  }
  
  // Additional alerting for critical errors
  if (enrichedContext.severity === 'CRITICAL') {
    // TODO: Integrate with alerting system (e.g., CloudWatch Alarms, PagerDuty)
    console.error('🚨 CRITICAL ERROR ALERT:', {
      correlationId: req.correlationId,
      error: error.message,
      user: enrichedContext.user?.id,
      path: enrichedContext.request.path
    });
  }
}

/**
 * Express middleware for enhanced error handling
 */
function errorHandlerMiddleware(error, req, res, next) {
  // Log the error with enhanced context
  logError(error, req);
  
  // Format error response
  const { statusCode, response } = formatErrorResponse(error, req);
  
  // Send response
  res.status(statusCode).json(response);
}

/**
 * Database error handler with fallback strategies
 */
async function handleDatabaseError(error, operation, fallbackFn = null) {
  const logger = getLogger();
  
  logger.error('Database operation failed', {
    operation,
    error: error.message,
    category: categorizeError(error)
  });
  
  // Attempt fallback if provided
  if (fallbackFn && typeof fallbackFn === 'function') {
    try {
      logger.warn('Attempting fallback strategy for database operation', { operation });
      const fallbackResult = await fallbackFn();
      logger.info('Fallback strategy succeeded', { operation });
      return fallbackResult;
    } catch (fallbackError) {
      logger.error('Fallback strategy failed', {
        operation,
        originalError: error.message,
        fallbackError: fallbackError.message
      });
    }
  }
  
  // Re-throw original error if no fallback or fallback failed
  throw error;
}

/**
 * External service error handler with retry logic
 */
async function handleExternalServiceError(error, serviceName, operation, retryCount = 0, maxRetries = 3) {
  const logger = getLogger();
  
  logger.error('External service error', {
    service: serviceName,
    operation,
    error: error.message,
    retryCount,
    maxRetries
  });
  
  // Check if error is retryable
  const retryableErrors = ['TIMEOUT_ERROR', 'RATE_LIMIT_ERROR', 'SERVER_ERROR'];
  const category = categorizeError(error);
  
  if (retryableErrors.includes(category) && retryCount < maxRetries) {
    const delay = Math.min(1000 * Math.pow(2, retryCount), 30000); // Exponential backoff, max 30s
    
    logger.warn('Retrying external service call', {
      service: serviceName,
      operation,
      retryCount: retryCount + 1,
      delayMs: delay
    });
    
    await new Promise(resolve => setTimeout(resolve, delay));
    throw { ...error, retryCount: retryCount + 1 };
  }
  
  throw error;
}

module.exports = {
  asyncHandler,
  enrichErrorContext,
  categorizeError,
  determineSeverity,
  isRecoverable,
  generateUserMessage,
  formatErrorResponse,
  logError,
  errorHandlerMiddleware,
  handleDatabaseError,
  handleExternalServiceError
};