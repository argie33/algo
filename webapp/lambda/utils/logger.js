/**
 * Comprehensive logging utility for the financial platform
 * Provides structured logging with correlation IDs and contextual information
 */

const encrypt = require("crypto");

/**
 * Log levels
 */
const LOG_LEVELS = {
  ERROR: 0,
  WARN: 1,
  INFO: 2,
  DEBUG: 3,
};

const LOG_LEVEL_NAMES = ["ERROR", "WARN", "INFO", "DEBUG"];

class Logger {
  constructor() {
    this.currentLevel = this.parseLogLevel(process.env.LOG_LEVEL || "INFO");
    this.serviceName = process.env.SERVICE_NAME || "financial-platform-api";
    this.environment = process.env.NODE_ENV || "development";
    this.version = process.env.APP_VERSION || "1.0.0";
  }

  /**
   * Parse log level from string
   */
  parseLogLevel(levelStr) {
    const level = levelStr.toUpperCase();
    return LOG_LEVELS[level] !== undefined
      ? LOG_LEVELS[level]
      : LOG_LEVELS.INFO;
  }

  /**
   * Generate correlation ID for request tracking
   */
  generateCorrelationId() {
    return encrypt.randomUUID().split("-")[0];
  }

  /**
   * Create base log entry structure
   */
  createBaseEntry(level, message, context = {}) {
    return {
      timestamp: new Date().toISOString(),
      level: LOG_LEVEL_NAMES[level],
      service: this.serviceName,
      environment: this.environment,
      version: this.version,
      message: message,
      correlationId: context.correlationId || this.generateCorrelationId(),
      ...context,
    };
  }

  /**
   * Check if level should be logged
   */
  shouldLog(level) {
    return level <= this.currentLevel;
  }

  /**
   * Output log entry
   */
  output(logEntry) {
    if (this.environment === "development") {
      // Pretty print for development
      const { timestamp, level, message, correlationId, service, environment, version, severity, ...rest } = logEntry;
      console.log(`[${timestamp}] [${level}] [${correlationId}] ${message}`);
      if (Object.keys(rest).length > 0) {
        console.log("Context:", JSON.stringify(rest, null, 2));
      }
    } else {
      // JSON format for production (structured logging)
      console.log(JSON.stringify(logEntry));
    }
  }

  /**
   * Error logging
   */
  error(message, context = {}) {
    if (!this.shouldLog(LOG_LEVELS.ERROR)) return;

    const logEntry = this.createBaseEntry(LOG_LEVELS.ERROR, message, {
      ...context,
      severity: "ERROR",
    });

    // Add error details if error object is provided
    if (context.error instanceof Error) {
      logEntry.error = {
        name: context.error.name,
        message: context.error.message,
        stack: context.error.stack,
        code: context.error.code,
      };
    }

    this.output(logEntry);
  }

  /**
   * Warning logging
   */
  warn(message, context = {}) {
    if (!this.shouldLog(LOG_LEVELS.WARN)) return;

    const logEntry = this.createBaseEntry(LOG_LEVELS.WARN, message, {
      ...context,
      severity: "WARN",
    });

    this.output(logEntry);
  }

  /**
   * Info logging
   */
  info(message, context = {}) {
    if (!this.shouldLog(LOG_LEVELS.INFO)) return;

    const logEntry = this.createBaseEntry(LOG_LEVELS.INFO, message, {
      ...context,
      severity: "INFO",
    });

    this.output(logEntry);
  }

  /**
   * Debug logging
   */
  debug(message, context = {}) {
    if (!this.shouldLog(LOG_LEVELS.DEBUG)) return;

    const logEntry = this.createBaseEntry(LOG_LEVELS.DEBUG, message, {
      ...context,
      severity: "DEBUG",
    });

    this.output(logEntry);
  }

  /**
   * Database operation logging
   */
  database(operation, context = {}) {
    this.info(`Database operation: ${operation}`, {
      ...context,
      component: "database",
      operation: operation,
    });
  }

  /**
   * API call logging
   */
  apiCall(method, url, context = {}) {
    this.info(`API call: ${method} ${url}`, {
      ...context,
      component: "api-client",
      method: method,
      url: url,
    });
  }

  /**
   * Authentication logging
   */
  auth(event, context = {}) {
    this.info(`Authentication event: ${event}`, {
      ...context,
      component: "auth",
      event: event,
    });
  }

  /**
   * Performance logging
   */
  performance(operation, duration, context = {}) {
    const level = duration > 5000 ? LOG_LEVELS.WARN : LOG_LEVELS.INFO;
    const message = `Performance: ${operation} completed in ${duration}ms`;

    if (level === LOG_LEVELS.WARN) {
      this.warn(message, {
        ...context,
        component: "performance",
        operation: operation,
        duration_ms: duration,
        slow_operation: true,
      });
    } else {
      this.info(message, {
        ...context,
        component: "performance",
        operation: operation,
        duration_ms: duration,
      });
    }
  }

  /**
   * Security event logging
   */
  security(event, context = {}) {
    this.warn(`Security event: ${event}`, {
      ...context,
      component: "security",
      event: event,
      severity: "SECURITY",
    });
  }

  /**
   * User action logging
   */
  userAction(userId, action, context = {}) {
    this.info(`User action: ${action}`, {
      ...context,
      component: "user-action",
      userId: userId ? `${userId.substring(0, 8)}...` : "anonymous",
      action: action,
    });
  }

  /**
   * Request logging middleware
   */
  requestMiddleware() {
    return (req, res, next) => {
      const correlationId = this.generateCorrelationId();
      const startTime = Date.now();

      // Add correlation ID to request
      req.correlationId = correlationId;

      // Log incoming request
      this.info("Incoming request", {
        correlationId: correlationId,
        component: "http-request",
        method: req.method,
        url: req.url,
        path: req.path,
        userAgent: req.headers["user-agent"],
        ip: req.ip,
        hasAuth: !!req.headers.authorization,
      });

      // Override res.json to log responses
      const originalJson = res.json;
      res.json = function (body) {
        const duration = Date.now() - startTime;

        // Log response
        req.logger.info("Request completed", {
          correlationId: correlationId,
          component: "http-response",
          method: req.method,
          url: req.url,
          statusCode: res.statusCode,
          duration_ms: duration,
          success: res.statusCode < 400,
        });

        return originalJson.call(this, body);
      };

      // Add logger to request object
      req.logger = this;

      next();
    };
  }

  /**
   * Error handling middleware
   */
  errorMiddleware() {
    return (error, req, res, next) => {
      this.error("Request error", {
        correlationId: req.correlationId,
        component: "error-handler",
        error: error,
        method: req.method,
        url: req.url,
        userAgent: req.headers["user-agent"],
        ip: req.ip,
      });

      next(error);
    };
  }

  /**
   * Create child logger with additional context
   */
  child(context = {}) {
    const childLogger = Object.create(this);
    childLogger.defaultContext = { ...this.defaultContext, ...context };

    // Override methods to include default context
    ["error", "warn", "info", "debug"].forEach((method) => {
      childLogger[method] = (message, additionalContext = {}) => {
        this[method](message, {
          ...childLogger.defaultContext,
          ...additionalContext,
        });
      };
    });

    return childLogger;
  }

  /**
   * Log application startup
   */
  startup(context = {}) {
    this.info("Application starting", {
      ...context,
      component: "startup",
      nodeVersion: process.version,
      pid: process.pid,
      memory: process.memoryUsage(),
    });
  }

  /**
   * Log application shutdown
   */
  shutdown(context = {}) {
    this.info("Application shutting down", {
      ...context,
      component: "shutdown",
      uptime: process.uptime(),
    });
  }

  /**
   * Log configuration loaded
   */
  configLoaded(config, context = {}) {
    // Don't log sensitive configuration values
    const sanitizedConfig = this.sanitizeConfig(config);

    this.info("Configuration loaded", {
      ...context,
      component: "config",
      config: sanitizedConfig,
    });
  }

  /**
   * Sanitize configuration for logging (remove sensitive values)
   */
  sanitizeConfig(config) {
    const sensitive = ["password", "secret", "key", "token", "credential"];
    const sanitized = {};

    for (const [key, value] of Object.entries(config)) {
      const isSensitive = sensitive.some((word) =>
        key.toLowerCase().includes(word)
      );

      if (isSensitive) {
        sanitized[key] = "[REDACTED]";
      } else if (typeof value === "object" && value !== null) {
        sanitized[key] = this.sanitizeConfig(value);
      } else {
        sanitized[key] = value;
      }
    }

    return sanitized;
  }
}

// Export singleton instance
const logger = new Logger();

/**
 * Factory function to create logger instances
 */
function createLogger(serviceName, component) {
  if (serviceName) {
    return logger.child({ serviceName, component });
  }
  return logger;
}

module.exports = logger;
module.exports.createLogger = createLogger;
