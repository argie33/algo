/**
 * Structured Logger for CloudWatch integration
 * Provides JSON-formatted logs compatible with AWS CloudWatch Insights
 * Replaces console.log/warn/error across the application
 */

class Logger {
  constructor() {
    this.logLevel = this.parseLogLevel(process.env.LOG_LEVEL || 'INFO');
    this.levels = {
      DEBUG: 0,
      INFO: 1,
      WARN: 2,
      ERROR: 3,
      CRITICAL: 4
    };
  }

  parseLogLevel(level) {
    const levelMap = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3, CRITICAL: 4 };
    return levelMap[level?.toUpperCase()] ?? 1;
  }

  shouldLog(level) {
    return level >= this.logLevel;
  }

  /**
   * Format log message with context
   * Outputs JSON for CloudWatch Insights parsing
   */
  format(level, message, meta = {}) {
    return JSON.stringify({
      timestamp: new Date().toISOString(),
      level,
      message,
      ...meta,
      // AWS Lambda context if available
      requestId: process.env.AWS_REQUEST_ID || undefined,
      functionName: process.env.AWS_LAMBDA_FUNCTION_NAME || undefined,
      environment: process.env.NODE_ENV || 'development',
    }, null, 2);
  }

  /**
   * Log at DEBUG level (verbose development info)
   */
  debug(message, meta = {}) {
    if (this.shouldLog(0)) {
      console.log(this.format('DEBUG', message, meta));
    }
  }

  /**
   * Log at INFO level (normal operation)
   */
  info(message, meta = {}) {
    if (this.shouldLog(1)) {
      console.log(this.format('INFO', message, meta));
    }
  }

  /**
   * Log at WARN level (potential issues)
   */
  warn(message, meta = {}) {
    if (this.shouldLog(2)) {
      console.warn(this.format('WARN', message, meta));
    }
  }

  /**
   * Log at ERROR level (runtime errors)
   */
  error(message, error = null, meta = {}) {
    if (this.shouldLog(3)) {
      const errorMeta = {
        ...meta,
        error: error?.message || error,
        // Only include stack trace in development
        ...(process.env.NODE_ENV === 'development' && { stack: error?.stack })
      };
      console.error(this.format('ERROR', message, errorMeta));
    }
  }

  /**
   * Log at CRITICAL level (application-level failures)
   */
  critical(message, error = null, meta = {}) {
    if (this.shouldLog(4)) {
      const errorMeta = {
        ...meta,
        error: error?.message || error,
        stack: error?.stack // Always include stack for critical errors
      };
      console.error(this.format('CRITICAL', message, errorMeta));
    }
  }

  /**
   * Log API request
   */
  apiRequest(method, path, statusCode, duration, meta = {}) {
    this.info(`${method} ${path}`, {
      method,
      path,
      statusCode,
      duration_ms: duration,
      ...meta
    });
  }

  /**
   * Log database operation
   */
  dbQuery(operation, table, duration, rowCount = null, meta = {}) {
    this.debug(`DB: ${operation} on ${table}`, {
      operation,
      table,
      duration_ms: duration,
      ...(rowCount !== null && { rows: rowCount }),
      ...meta
    });
  }

  /**
   * Log external API call
   */
  externalCall(service, endpoint, statusCode, duration, meta = {}) {
    this.debug(`${service} ${endpoint}`, {
      service,
      endpoint,
      statusCode,
      duration_ms: duration,
      ...meta
    });
  }
}

// Export singleton instance
module.exports = new Logger();
