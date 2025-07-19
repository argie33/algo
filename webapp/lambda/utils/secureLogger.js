/**
 * Secure Logger Utility
 * Prevents sensitive data exposure in logs for financial applications
 */

class SecureLogger {
  constructor() {
    // Sensitive patterns to redact from logs
    this.sensitivePatterns = [
      // API Keys and Tokens
      { pattern: /AKIAIO[A-Z0-9]{14,}/gi, replacement: '[AWS_ACCESS_KEY_REDACTED]' },
      { pattern: /pk_[a-zA-Z0-9]{48}/gi, replacement: '[ALPACA_KEY_REDACTED]' },
      { pattern: /sk_[a-zA-Z0-9]{48}/gi, replacement: '[ALPACA_SECRET_REDACTED]' },
      { pattern: /[A-Za-z0-9+/]{40,}={0,2}/g, replacement: '[BASE64_TOKEN_REDACTED]' },
      
      // JWT Tokens
      { pattern: /eyJ[A-Za-z0-9+/=]{100,}/g, replacement: '[JWT_TOKEN_REDACTED]' },
      
      // Database Passwords (common patterns)
      { pattern: /password['"]*\s*[:=]\s*['"][^'"]{8,}['"]/gi, replacement: 'password="[REDACTED]"' },
      { pattern: /pwd['"]*\s*[:=]\s*['"][^'"]{8,}['"]/gi, replacement: 'pwd="[REDACTED]"' },
      
      // AWS ARNs
      { pattern: /arn:aws:[a-zA-Z0-9-]+:[a-zA-Z0-9-]*:\d{12}:[a-zA-Z0-9-/:]+/g, replacement: '[AWS_ARN_REDACTED]' },
      
      // IP Addresses (internal networks)
      { pattern: /\b(10|172|192)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/g, replacement: '[INTERNAL_IP_REDACTED]' },
      
      // Email addresses
      { pattern: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g, replacement: '[EMAIL_REDACTED]' },
      
      // Credit card patterns (basic)
      { pattern: /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/g, replacement: '[CARD_NUMBER_REDACTED]' },
      
      // SSN patterns
      { pattern: /\b\d{3}-?\d{2}-?\d{4}\b/g, replacement: '[SSN_REDACTED]' },
      
      // Phone numbers
      { pattern: /\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g, replacement: '[PHONE_REDACTED]' },
      
      // Process.env variables (selective)
      { pattern: /(DB_PASSWORD|API_KEY|SECRET|TOKEN|PRIVATE_KEY)['"]*\s*[:=]\s*['"][^'"]*['"]/gi, replacement: '$1="[REDACTED]"' }
    ];

    // Sensitive field names to redact
    this.sensitiveFields = new Set([
      'password', 'secret', 'token', 'key', 'apikey', 'api_key',
      'auth', 'authorization', 'credential', 'private', 'confidential',
      'ssn', 'social_security', 'credit_card', 'card_number', 'cvv',
      'pin', 'account_number', 'routing_number', 'bank_account',
      'jwt', 'bearer', 'oauth', 'session_id', 'csrf_token'
    ]);

    // Environment-based log level control
    this.logLevel = this.getLogLevel();
    this.isProduction = process.env.NODE_ENV === 'production';
    this.isDevelopment = process.env.NODE_ENV === 'development';
  }

  /**
   * Get appropriate log level based on environment
   */
  getLogLevel() {
    const env = process.env.NODE_ENV || 'development';
    const levels = {
      production: ['error', 'warn'],
      staging: ['error', 'warn', 'info'],
      development: ['error', 'warn', 'info', 'debug'],
      test: ['error']
    };
    return levels[env] || levels.development;
  }

  /**
   * Sanitize any value to remove sensitive data
   */
  sanitize(data, maxDepth = 3) {
    if (maxDepth <= 0) return '[MAX_DEPTH_REACHED]';

    if (typeof data === 'string') {
      return this.sanitizeString(data);
    }

    if (typeof data === 'object' && data !== null) {
      if (Array.isArray(data)) {
        return data.map(item => this.sanitize(item, maxDepth - 1));
      }

      const sanitized = {};
      for (const [key, value] of Object.entries(data)) {
        if (this.isSensitiveField(key)) {
          sanitized[key] = '[REDACTED]';
        } else {
          sanitized[key] = this.sanitize(value, maxDepth - 1);
        }
      }
      return sanitized;
    }

    return data;
  }

  /**
   * Sanitize string content
   */
  sanitizeString(str) {
    if (!str || typeof str !== 'string') return str;

    let sanitized = str;
    for (const { pattern, replacement } of this.sensitivePatterns) {
      sanitized = sanitized.replace(pattern, replacement);
    }

    return sanitized;
  }

  /**
   * Check if field name is sensitive
   */
  isSensitiveField(fieldName) {
    if (!fieldName || typeof fieldName !== 'string') return false;
    
    const lower = fieldName.toLowerCase();
    return this.sensitiveFields.has(lower) || 
           [...this.sensitiveFields].some(sensitive => lower.includes(sensitive));
  }

  /**
   * Redact user identifiers for privacy
   */
  redactUserId(userId) {
    if (!userId) return '[NO_USER_ID]';
    if (typeof userId !== 'string') return '[INVALID_USER_ID]';
    
    // Show first 4 characters only
    if (userId.length <= 8) return '[USER_ID_REDACTED]';
    return `${userId.substring(0, 4)}...${userId.substring(userId.length - 4)}`;
  }

  /**
   * Redact correlation IDs partially for tracking
   */
  redactCorrelationId(correlationId) {
    if (!correlationId) return '[NO_CORRELATION_ID]';
    if (typeof correlationId !== 'string') return '[INVALID_CORRELATION_ID]';
    
    // Show first 8 characters for correlation
    return correlationId.length > 12 ? `${correlationId.substring(0, 8)}...` : correlationId;
  }

  /**
   * Create secure log entry
   */
  createLogEntry(level, message, data = null, context = {}) {
    const timestamp = new Date().toISOString();
    const logEntry = {
      timestamp,
      level: level.toUpperCase(),
      message: this.sanitizeString(message),
      service: 'financial-platform',
      environment: process.env.NODE_ENV || 'unknown'
    };

    // Add correlation ID if provided
    if (context.correlationId) {
      logEntry.correlationId = this.redactCorrelationId(context.correlationId);
    }

    // Add user ID if provided (redacted)
    if (context.userId) {
      logEntry.userId = this.redactUserId(context.userId);
    }

    // Add component/module context
    if (context.component) {
      logEntry.component = context.component;
    }

    // Add operation context
    if (context.operation) {
      logEntry.operation = context.operation;
    }

    // Sanitize and add data if provided
    if (data !== null && data !== undefined) {
      logEntry.data = this.sanitize(data);
    }

    return logEntry;
  }

  /**
   * Check if log level should be output
   */
  shouldLog(level) {
    return this.logLevel.includes(level.toLowerCase());
  }

  /**
   * Secure debug logging
   */
  debug(message, data = null, context = {}) {
    if (!this.shouldLog('debug')) return;
    
    const logEntry = this.createLogEntry('debug', message, data, context);
    console.debug('🔍 [DEBUG]', JSON.stringify(logEntry));
  }

  /**
   * Secure info logging
   */
  info(message, data = null, context = {}) {
    if (!this.shouldLog('info')) return;
    
    const logEntry = this.createLogEntry('info', message, data, context);
    console.log('ℹ️  [INFO]', JSON.stringify(logEntry));
  }

  /**
   * Secure warning logging
   */
  warn(message, data = null, context = {}) {
    if (!this.shouldLog('warn')) return;
    
    const logEntry = this.createLogEntry('warn', message, data, context);
    console.warn('⚠️  [WARN]', JSON.stringify(logEntry));
  }

  /**
   * Secure error logging
   */
  error(message, error = null, context = {}) {
    if (!this.shouldLog('error')) return;
    
    let errorData = null;
    if (error) {
      errorData = {
        name: error.name,
        message: this.sanitizeString(error.message),
        ...(this.isDevelopment && { stack: error.stack })
      };
    }
    
    const logEntry = this.createLogEntry('error', message, errorData, context);
    console.error('❌ [ERROR]', JSON.stringify(logEntry));
  }

  /**
   * Secure security event logging (always logs regardless of level)
   */
  security(eventType, message, data = null, context = {}) {
    const logEntry = this.createLogEntry('security', message, data, {
      ...context,
      eventType,
      severity: context.severity || 'MEDIUM'
    });
    
    console.warn('🚨 [SECURITY]', JSON.stringify(logEntry));
    
    // In production, also send to security monitoring system
    if (this.isProduction) {
      this.sendToSecurityMonitoring(logEntry);
    }
  }

  /**
   * Send security events to monitoring system (placeholder)
   */
  sendToSecurityMonitoring(logEntry) {
    // TODO: Implement integration with security monitoring system
    // Example: AWS CloudWatch, Splunk, DataDog, etc.
    console.warn('🔒 Security event logged for monitoring:', {
      timestamp: logEntry.timestamp,
      eventType: logEntry.eventType,
      severity: logEntry.severity
    });
  }

  /**
   * Audit database operations
   */
  auditDatabase(operation, table, userId, details = {}) {
    this.security('DATABASE_OPERATION', `Database ${operation} on ${table}`, {
      operation,
      table,
      details: this.sanitize(details)
    }, {
      userId,
      component: 'database',
      severity: 'LOW'
    });
  }

  /**
   * Audit authentication events
   */
  auditAuth(eventType, userId, details = {}) {
    this.security('AUTHENTICATION', `Auth event: ${eventType}`, {
      eventType,
      details: this.sanitize(details)
    }, {
      userId,
      component: 'authentication',
      severity: eventType.includes('fail') ? 'HIGH' : 'MEDIUM'
    });
  }

  /**
   * Log API key operations (always redacted)
   */
  auditApiKey(operation, userId, provider) {
    this.security('API_KEY_OPERATION', `API key ${operation}`, {
      operation,
      provider
    }, {
      userId,
      component: 'api-key-service',
      severity: 'MEDIUM'
    });
  }
}

// Create singleton instance
const secureLogger = new SecureLogger();

// Export both the class and singleton for flexibility
module.exports = {
  SecureLogger,
  secureLogger,
  
  // Convenience methods for quick usage
  debug: (message, data, context) => secureLogger.debug(message, data, context),
  info: (message, data, context) => secureLogger.info(message, data, context),
  warn: (message, data, context) => secureLogger.warn(message, data, context),
  error: (message, error, context) => secureLogger.error(message, error, context),
  security: (eventType, message, data, context) => secureLogger.security(eventType, message, data, context),
  
  // Audit methods
  auditDatabase: (operation, table, userId, details) => secureLogger.auditDatabase(operation, table, userId, details),
  auditAuth: (eventType, userId, details) => secureLogger.auditAuth(eventType, userId, details),
  auditApiKey: (operation, userId, provider) => secureLogger.auditApiKey(operation, userId, provider),
  
  // Utility methods
  sanitize: (data) => secureLogger.sanitize(data),
  redactUserId: (userId) => secureLogger.redactUserId(userId)
};