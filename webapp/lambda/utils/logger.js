/**
 * Logger Utility - Structured logging for the API
 * Provides domain-specific logging methods and output formatting
 */

const crypto = require('crypto');

const LOG_LEVELS = {
  ERROR: 0,
  WARN: 1,
  INFO: 2,
  DEBUG: 3,
};

const LEVEL_NAMES = {
  0: 'ERROR',
  1: 'WARN',
  2: 'INFO',
  3: 'DEBUG',
};

class Logger {
  constructor() {
    this.serviceName = process.env.SERVICE_NAME || 'financial-platform-api';
    this.version = process.env.APP_VERSION || '1.0.0';
    this.environment = process.env.NODE_ENV || 'development';
    this.currentLevel = this.parseLogLevel(process.env.LOG_LEVEL || 'INFO');
  }

  parseLogLevel(level) {
    if (typeof level === 'number') return level;
    return LOG_LEVELS[level.toUpperCase()] || LOG_LEVELS.INFO;
  }

  shouldLog(level) {
    return level <= this.currentLevel;
  }

  generateCorrelationId() {
    return crypto.randomUUID().split('-')[0];
  }

  createBaseEntry(level, message, context = {}) {
    return {
      timestamp: new Date().toISOString(),
      level: LEVEL_NAMES[level] || 'INFO',
      service: this.serviceName,
      version: this.version,
      environment: this.environment,
      message,
      correlationId: context.correlationId || this.generateCorrelationId(),
      ...context,
    };
  }

  output(logEntry) {
    if (this.environment === 'production') {
      console.log(JSON.stringify(logEntry));
    } else {
      const { timestamp, level, message, service } = logEntry;
      console.log(
        `[${timestamp}] [${level}] [${service}] ${message}`
      );
      // Log additional context if present
      const contextKeys = Object.keys(logEntry).filter(
        (k) => !['timestamp', 'level', 'message', 'service', 'version', 'environment', 'correlationId'].includes(k)
      );
      if (contextKeys.length > 0) {
        const context = {};
        contextKeys.forEach((k) => {
          context[k] = logEntry[k];
        });
        console.log(JSON.stringify(context, null, 2));
      }
    }
  }

  log(level, message, context = {}) {
    if (!this.shouldLog(level)) return;
    const entry = this.createBaseEntry(level, message, context);
    this.output(entry);
  }

  error(message, context = {}) {
    this.log(LOG_LEVELS.ERROR, message, context);
  }

  warn(message, context = {}) {
    this.log(LOG_LEVELS.WARN, message, context);
  }

  info(message, context = {}) {
    this.log(LOG_LEVELS.INFO, message, context);
  }

  debug(message, context = {}) {
    this.log(LOG_LEVELS.DEBUG, message, context);
  }

  auth(event, context = {}) {
    this.info(event, { type: 'auth', ...context });
  }

  security(event, context = {}) {
    this.warn(event, { type: 'security', ...context });
  }

  userAction(userId, action, context = {}) {
    this.info(action, { type: 'user_action', userId: userId || 'anonymous', ...context });
  }

  database(query, context = {}) {
    this.debug(query, { type: 'database', ...context });
  }

  apiCall(method, path, context = {}) {
    this.info(`${method} ${path}`, { type: 'api_call', ...context });
  }

  performance(operation, durationMs, context = {}) {
    const level = durationMs > 5000 ? LOG_LEVELS.WARN : LOG_LEVELS.INFO;
    if (this.shouldLog(level)) {
      this.log(level, `${operation} completed in ${durationMs}ms`, {
        type: 'performance',
        operation,
        duration_ms: durationMs,
        ...context,
      });
    }
  }

  startup(context = {}) {
    this.info('Application starting', { type: 'lifecycle', event: 'startup', ...context });
  }

  shutdown(context = {}) {
    this.info('Application shutting down', { type: 'lifecycle', event: 'shutdown', ...context });
  }

  configLoaded(config) {
    this.info('Configuration loaded', {
      type: 'lifecycle',
      config: this.sanitizeConfig(config),
    });
  }

  sanitizeConfig(obj) {
    if (!obj) return obj;
    if (typeof obj !== 'object') return obj;

    if (Array.isArray(obj)) {
      return obj.map((item) => this.sanitizeConfig(item));
    }

    const sanitized = {};
    const sensitiveKeyPattern = /key|secret|password|token|credential/i;

    for (const [key, value] of Object.entries(obj)) {
      if (sensitiveKeyPattern.test(key)) {
        sanitized[key] = '[REDACTED]';
      } else if (typeof value === 'object' && value !== null) {
        sanitized[key] = this.sanitizeConfig(value);
      } else {
        sanitized[key] = value;
      }
    }

    return sanitized;
  }

  requestMiddleware() {
    return (req, res, next) => {
      req.correlationId = req.headers['x-correlation-id'] || this.generateCorrelationId();
      req.logger = this;

      // Log request
      this.apiCall(req.method, req.path, {
        correlationId: req.correlationId,
        ip: req.ip,
        userId: req.user?.sub,
      });

      // Override res.json to log responses
      const originalJson = res.json;
      res.json = function (data) {
        const duration = Date.now() - req.startTime;
        if (res.statusCode >= 400) {
          req.logger.warn(`${req.method} ${req.path} - ${res.statusCode}`, {
            type: 'api_call',
            correlationId: req.correlationId,
            status: res.statusCode,
            duration_ms: duration,
          });
        }
        return originalJson.call(this, data);
      };

      req.startTime = Date.now();
      next();
    };
  }

  errorMiddleware() {
    return (err, req, res, next) => {
      this.error(`Unhandled error in ${req.method} ${req.path}`, {
        correlationId: req.correlationId,
        error: err.message,
        stack: err.stack,
      });
      next(err);
    };
  }

  child(additionalContext) {
    const childLogger = Object.create(this);
    childLogger.defaultContext = additionalContext;

    const originalLog = this.log;
    childLogger.log = function (level, message, context = {}) {
      return originalLog.call(this, level, message, {
        ...this.defaultContext,
        ...context,
      });
    };

    return childLogger;
  }
}

// Export singleton and class
const loggerInstance = new Logger();
module.exports = loggerInstance;
module.exports.Logger = Logger;
