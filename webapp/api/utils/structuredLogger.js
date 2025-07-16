/**
 * Structured Logger - Comprehensive logging for all system components
 * Provides consistent logging format with correlation IDs and context
 */

const crypto = require('crypto');

class StructuredLogger {
  constructor(service = 'financial-platform', component = 'unknown') {
    this.service = service;
    this.component = component;
    this.correlationId = this.generateCorrelationId();
    this.startTime = Date.now();
  }

  generateCorrelationId() {
    return crypto.randomUUID().split('-')[0];
  }

  createLogEntry(level, message, context = {}) {
    const timestamp = new Date().toISOString();
    const duration = Date.now() - this.startTime;
    
    return {
      timestamp,
      level: level.toUpperCase(),
      message,
      service: this.service,
      component: this.component,
      correlationId: this.correlationId,
      duration_ms: duration,
      context: {
        ...context,
        environment: process.env.NODE_ENV || 'unknown',
        aws_region: process.env.AWS_REGION || 'unknown',
        lambda_function: process.env.AWS_LAMBDA_FUNCTION_NAME || 'unknown',
        lambda_version: process.env.AWS_LAMBDA_FUNCTION_VERSION || 'unknown'
      }
    };
  }

  debug(message, context = {}) {
    if (process.env.NODE_ENV === 'development') {
      const logEntry = this.createLogEntry('DEBUG', message, context);
      console.log(JSON.stringify(logEntry, null, 2));
    }
  }

  info(message, context = {}) {
    const logEntry = this.createLogEntry('INFO', message, context);
    console.log(JSON.stringify(logEntry));
  }

  warn(message, context = {}) {
    const logEntry = this.createLogEntry('WARN', message, context);
    console.warn(JSON.stringify(logEntry));
  }

  error(message, error = null, context = {}) {
    const logEntry = this.createLogEntry('ERROR', message, {
      ...context,
      error: error ? {
        message: error.message,
        stack: error.stack,
        code: error.code,
        name: error.name
      } : null
    });
    console.error(JSON.stringify(logEntry));
  }

  fatal(message, error = null, context = {}) {
    const logEntry = this.createLogEntry('FATAL', message, {
      ...context,
      error: error ? {
        message: error.message,
        stack: error.stack,
        code: error.code,
        name: error.name
      } : null
    });
    console.error(JSON.stringify(logEntry));
  }

  // Database operation logging
  dbOperation(operation, query, params = [], duration = 0, rowCount = 0, error = null) {
    const context = {
      database: {
        operation,
        query_preview: query ? query.substring(0, 100) + '...' : 'N/A',
        params_count: params.length,
        duration_ms: duration,
        row_count: rowCount,
        error: error ? {
          message: error.message,
          code: error.code
        } : null
      }
    };

    if (error) {
      this.error(`Database operation failed: ${operation}`, error, context);
    } else {
      this.info(`Database operation completed: ${operation}`, context);
    }
  }

  // External API call logging
  apiCall(service, endpoint, method = 'GET', statusCode = 0, duration = 0, error = null) {
    const context = {
      external_api: {
        service,
        endpoint,
        method,
        status_code: statusCode,
        duration_ms: duration,
        error: error ? {
          message: error.message,
          code: error.code
        } : null
      }
    };

    if (error || statusCode >= 400) {
      this.error(`External API call failed: ${service}/${endpoint}`, error, context);
    } else {
      this.info(`External API call completed: ${service}/${endpoint}`, context);
    }
  }

  // Authentication and authorization logging
  authEvent(event, userId = null, outcome = 'success', details = {}) {
    const context = {
      authentication: {
        event,
        user_id: userId,
        outcome,
        details
      }
    };

    if (outcome === 'success') {
      this.info(`Authentication event: ${event}`, context);
    } else {
      this.warn(`Authentication event failed: ${event}`, context);
    }
  }

  // Performance tracking
  performance(operation, duration, metrics = {}) {
    const context = {
      performance: {
        operation,
        duration_ms: duration,
        metrics
      }
    };

    if (duration > 5000) {
      this.warn(`Slow operation detected: ${operation}`, context);
    } else {
      this.info(`Performance tracking: ${operation}`, context);
    }
  }

  // User action logging
  userAction(action, userId, details = {}) {
    const context = {
      user_action: {
        action,
        user_id: userId,
        details
      }
    };

    this.info(`User action: ${action}`, context);
  }

  // System event logging
  systemEvent(event, severity = 'info', details = {}) {
    const context = {
      system_event: {
        event,
        severity,
        details
      }
    };

    switch (severity) {
      case 'critical':
        this.fatal(`System event: ${event}`, null, context);
        break;
      case 'error':
        this.error(`System event: ${event}`, null, context);
        break;
      case 'warning':
        this.warn(`System event: ${event}`, context);
        break;
      default:
        this.info(`System event: ${event}`, context);
    }
  }

  // Lambda lifecycle events
  lambdaStart(event, context) {
    this.info('Lambda function started', {
      lambda: {
        event_type: event?.httpMethod || 'unknown',
        path: event?.path || 'unknown',
        source_ip: event?.requestContext?.identity?.sourceIp || 'unknown',
        user_agent: event?.headers?.['user-agent'] || 'unknown',
        request_id: context?.awsRequestId || 'unknown',
        remaining_time: context?.getRemainingTimeInMillis?.() || 0
      }
    });
  }

  lambdaEnd(duration, statusCode, error = null) {
    const context = {
      lambda: {
        duration_ms: duration,
        status_code: statusCode,
        error: error ? {
          message: error.message,
          stack: error.stack
        } : null
      }
    };

    if (error) {
      this.error('Lambda function ended with error', error, context);
    } else {
      this.info('Lambda function completed successfully', context);
    }
  }

  // Circuit breaker logging
  circuitBreaker(service, state, failure_count = 0, details = {}) {
    const context = {
      circuit_breaker: {
        service,
        state,
        failure_count,
        details
      }
    };

    switch (state) {
      case 'open':
        this.error(`Circuit breaker opened for ${service}`, null, context);
        break;
      case 'half-open':
        this.warn(`Circuit breaker half-open for ${service}`, context);
        break;
      case 'closed':
        this.info(`Circuit breaker closed for ${service}`, context);
        break;
      default:
        this.info(`Circuit breaker state change: ${service}`, context);
    }
  }

  // Create child logger with additional context
  child(additionalContext = {}) {
    const childLogger = new StructuredLogger(this.service, this.component);
    childLogger.correlationId = this.correlationId;
    childLogger.additionalContext = {
      ...this.additionalContext,
      ...additionalContext
    };
    return childLogger;
  }

  // Set correlation ID for request tracing
  setCorrelationId(correlationId) {
    this.correlationId = correlationId;
  }

  // Get current correlation ID
  getCorrelationId() {
    return this.correlationId;
  }

  // Format error for logging
  formatError(error) {
    return {
      message: error.message,
      stack: error.stack,
      code: error.code,
      name: error.name,
      timestamp: new Date().toISOString()
    };
  }
}

// Factory function to create logger instances
function createLogger(service, component) {
  return new StructuredLogger(service, component);
}

// Express middleware for request logging
function requestLoggingMiddleware(req, res, next) {
  const logger = createLogger('financial-platform', 'express');
  const startTime = Date.now();

  // Generate correlation ID for request
  const correlationId = req.headers['x-correlation-id'] || crypto.randomUUID().split('-')[0];
  logger.setCorrelationId(correlationId);

  // Add correlation ID to response headers
  res.setHeader('X-Correlation-ID', correlationId);

  // Log request start
  logger.info('HTTP request started', {
    request: {
      method: req.method,
      url: req.url,
      path: req.path,
      query: req.query,
      user_agent: req.get('User-Agent'),
      origin: req.get('Origin'),
      content_type: req.get('Content-Type'),
      content_length: req.get('Content-Length'),
      source_ip: req.ip
    }
  });

  // Attach logger to request object
  req.logger = logger;

  // Log response
  const originalSend = res.send;
  res.send = function(data) {
    const duration = Date.now() - startTime;
    
    logger.info('HTTP request completed', {
      response: {
        status_code: res.statusCode,
        duration_ms: duration,
        response_size: data ? data.length : 0
      }
    });

    return originalSend.call(this, data);
  };

  next();
}

module.exports = {
  StructuredLogger,
  createLogger,
  requestLoggingMiddleware
};