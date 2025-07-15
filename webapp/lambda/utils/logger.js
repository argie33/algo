/**
 * Enhanced Logging Utility for Financial Dashboard
 * Provides structured logging with request correlation IDs, error severity classification,
 * and comprehensive performance monitoring for Lambda environment
 */

const crypto = require('crypto');

// Log levels with numeric priorities
const LOG_LEVELS = {
  DEBUG: { level: 0, name: 'DEBUG', icon: '🔍' },
  INFO: { level: 1, name: 'INFO', icon: '📝' },
  WARN: { level: 2, name: 'WARN', icon: '⚠️' },
  ERROR: { level: 3, name: 'ERROR', icon: '❌' },
  FATAL: { level: 4, name: 'FATAL', icon: '💥' }
};

// Current log level (can be overridden by environment)
const CURRENT_LOG_LEVEL = LOG_LEVELS[process.env.LOG_LEVEL?.toUpperCase()] || LOG_LEVELS.INFO;

// Performance tracking
const performanceTrackers = new Map();

/**
 * Generate a correlation ID for request tracking
 */
function generateCorrelationId() {
  return crypto.randomUUID().split('-')[0];
}

/**
 * Create structured log entry
 */
function createLogEntry(level, message, context = {}, requestId = null) {
  const timestamp = new Date().toISOString();
  const correlationId = requestId || context.requestId || generateCorrelationId();
  
  const logEntry = {
    timestamp,
    level: level.name,
    message,
    correlation_id: correlationId,
    context: {
      ...context,
      environment: process.env.NODE_ENV || 'development',
      lambda_function: process.env.AWS_LAMBDA_FUNCTION_NAME || 'local',
      lambda_version: process.env.AWS_LAMBDA_FUNCTION_VERSION || 'local',
      lambda_memory_size: process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE || 'unknown',
      region: process.env.AWS_REGION || 'unknown'
    }
  };

  // Add stack trace for errors
  if (level.level >= LOG_LEVELS.ERROR.level && context.error) {
    logEntry.error_details = {
      name: context.error.name,
      message: context.error.message,
      stack: context.error.stack,
      code: context.error.code,
      status: context.error.status,
      errno: context.error.errno
    };
  }

  return logEntry;
}

/**
 * Output log entry to console
 */
function outputLog(level, logEntry) {
  if (level.level < CURRENT_LOG_LEVEL.level) {
    return; // Skip logs below current level
  }

  const output = `${level.icon} [${logEntry.correlation_id}] ${logEntry.message}`;
  const contextOutput = Object.keys(logEntry.context).length > 0 ? 
    JSON.stringify(logEntry.context, null, 2) : '';

  switch (level.level) {
    case LOG_LEVELS.DEBUG.level:
      console.debug(output, contextOutput);
      break;
    case LOG_LEVELS.INFO.level:
      console.log(output, contextOutput);
      break;
    case LOG_LEVELS.WARN.level:
      console.warn(output, contextOutput);
      break;
    case LOG_LEVELS.ERROR.level:
    case LOG_LEVELS.FATAL.level:
      console.error(output, contextOutput);
      if (logEntry.error_details) {
        console.error('Error Details:', JSON.stringify(logEntry.error_details, null, 2));
      }
      break;
  }
}

/**
 * Core logging function
 */
function log(level, message, context = {}, requestId = null) {
  const logEntry = createLogEntry(level, message, context, requestId);
  outputLog(level, logEntry);
  return logEntry.correlation_id;
}

/**
 * Logger class for request-scoped logging
 */
class RequestLogger {
  constructor(requestId = null, initialContext = {}) {
    this.requestId = requestId || generateCorrelationId();
    this.context = { ...initialContext };
    this.startTime = Date.now();
    this.performanceMarkers = [];
  }

  /**
   * Add context that persists for this request
   */
  addContext(additionalContext) {
    this.context = { ...this.context, ...additionalContext };
  }

  /**
   * Mark a performance checkpoint
   */
  mark(label) {
    const now = Date.now();
    this.performanceMarkers.push({
      label,
      timestamp: now,
      elapsed: now - this.startTime
    });
  }

  /**
   * Get performance summary
   */
  getPerformanceSummary() {
    const totalDuration = Date.now() - this.startTime;
    return {
      total_duration_ms: totalDuration,
      markers: this.performanceMarkers,
      request_start: this.startTime,
      request_end: Date.now()
    };
  }

  // Logging methods
  debug(message, context = {}) {
    return log(LOG_LEVELS.DEBUG, message, { ...this.context, ...context }, this.requestId);
  }

  info(message, context = {}) {
    return log(LOG_LEVELS.INFO, message, { ...this.context, ...context }, this.requestId);
  }

  warn(message, context = {}) {
    return log(LOG_LEVELS.WARN, message, { ...this.context, ...context }, this.requestId);
  }

  error(message, context = {}) {
    return log(LOG_LEVELS.ERROR, message, { ...this.context, ...context }, this.requestId);
  }

  fatal(message, context = {}) {
    return log(LOG_LEVELS.FATAL, message, { ...this.context, ...context }, this.requestId);
  }

  /**
   * Log API request start
   */
  apiRequestStart(method, path, additionalContext = {}) {
    this.addContext({
      api_method: method,
      api_path: path,
      ...additionalContext
    });
    this.mark('request_start');
    return this.info(`API request started: ${method} ${path}`, {
      user_agent: additionalContext.userAgent,
      ip: additionalContext.ip,
      auth_present: !!additionalContext.authPresent
    });
  }

  /**
   * Log API request completion
   */
  apiRequestComplete(statusCode, additionalContext = {}) {
    this.mark('request_complete');
    const performance = this.getPerformanceSummary();
    
    const level = statusCode >= 500 ? LOG_LEVELS.ERROR : 
                 statusCode >= 400 ? LOG_LEVELS.WARN : LOG_LEVELS.INFO;
    
    return log(level, `API request completed: ${statusCode}`, {
      ...this.context,
      ...additionalContext,
      status_code: statusCode,
      performance
    }, this.requestId);
  }

  /**
   * Log database operation
   */
  dbOperation(operation, table, duration = null, additionalContext = {}) {
    this.mark(`db_${operation}_${table}`);
    return this.info(`Database ${operation}: ${table}`, {
      db_operation: operation,
      db_table: table,
      duration_ms: duration,
      ...additionalContext
    });
  }

  /**
   * Log external API call
   */
  externalApiCall(service, endpoint, duration = null, additionalContext = {}) {
    this.mark(`api_${service}`);
    const level = additionalContext.error ? LOG_LEVELS.ERROR : LOG_LEVELS.INFO;
    
    return log(level, `External API call: ${service} ${endpoint}`, {
      ...this.context,
      external_service: service,
      endpoint,
      duration_ms: duration,
      ...additionalContext
    }, this.requestId);
  }

  /**
   * Log authentication events
   */
  authEvent(event, userId = null, additionalContext = {}) {
    this.mark(`auth_${event}`);
    return this.info(`Authentication ${event}`, {
      auth_event: event,
      user_id: userId ? `${userId.substring(0, 8)}...` : 'unknown',
      ...additionalContext
    });
  }
}

/**
 * Create a new request logger
 */
function createRequestLogger(requestId = null, initialContext = {}) {
  return new RequestLogger(requestId, initialContext);
}

/**
 * Middleware to add request logger to Express requests
 */
function requestLoggingMiddleware(req, res, next) {
  // Generate or use existing request ID
  const requestId = req.headers['x-request-id'] || 
                   req.headers['x-correlation-id'] || 
                   generateCorrelationId();
  
  // Create request logger
  req.logger = createRequestLogger(requestId, {
    method: req.method,
    path: req.path,
    user_agent: req.headers['user-agent'],
    ip: req.ip || req.connection.remoteAddress,
    auth_header_present: !!req.headers.authorization
  });

  // Set correlation ID header in response
  res.setHeader('X-Correlation-ID', requestId);

  // Log request start
  req.logger.apiRequestStart(req.method, req.path, {
    userAgent: req.headers['user-agent'],
    ip: req.ip,
    authPresent: !!req.headers.authorization,
    query: req.query,
    params: req.params
  });

  // Override res.json to log response
  const originalJson = res.json;
  res.json = function(body) {
    req.logger.apiRequestComplete(res.statusCode, {
      response_size: JSON.stringify(body).length,
      success: res.statusCode < 400
    });
    return originalJson.call(this, body);
  };

  next();
}

/**
 * Global error logger
 */
function logError(error, context = {}, requestId = null) {
  return log(LOG_LEVELS.ERROR, error.message || 'Unknown error occurred', {
    error,
    ...context
  }, requestId);
}

/**
 * Performance tracking utilities
 */
function startPerformanceTracking(operation, requestId = null) {
  const trackingId = `${operation}_${requestId || generateCorrelationId()}`;
  performanceTrackers.set(trackingId, {
    operation,
    startTime: Date.now(),
    requestId: requestId || generateCorrelationId()
  });
  return trackingId;
}

function endPerformanceTracking(trackingId, additionalContext = {}) {
  const tracker = performanceTrackers.get(trackingId);
  if (!tracker) {
    return null;
  }

  const duration = Date.now() - tracker.startTime;
  performanceTrackers.delete(trackingId);

  log(LOG_LEVELS.INFO, `Performance: ${tracker.operation} completed`, {
    operation: tracker.operation,
    duration_ms: duration,
    ...additionalContext
  }, tracker.requestId);

  return duration;
}

module.exports = {
  // Core logging functions
  debug: (message, context, requestId) => log(LOG_LEVELS.DEBUG, message, context, requestId),
  info: (message, context, requestId) => log(LOG_LEVELS.INFO, message, context, requestId),
  warn: (message, context, requestId) => log(LOG_LEVELS.WARN, message, context, requestId),
  error: (message, context, requestId) => log(LOG_LEVELS.ERROR, message, context, requestId),
  fatal: (message, context, requestId) => log(LOG_LEVELS.FATAL, message, context, requestId),

  // Utilities
  generateCorrelationId,
  createRequestLogger,
  requestLoggingMiddleware,
  logError,
  startPerformanceTracking,
  endPerformanceTracking,
  
  // Classes
  RequestLogger,
  
  // Constants
  LOG_LEVELS
};