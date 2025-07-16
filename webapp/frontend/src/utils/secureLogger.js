// Secure Logging Utility
// Prevents accidental exposure of sensitive data in logs

const SENSITIVE_PATTERNS = [
  // API Keys
  /[A-Z0-9]{20,}/g,  // Alpaca-style keys
  /pk_[a-zA-Z0-9]{20,}/g,  // Private keys
  /sk_[a-zA-Z0-9]{20,}/g,  // Secret keys
  
  // Tokens
  /eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*/g,  // JWT tokens
  /Bearer\s+[A-Za-z0-9-._~+/]+=*/g,  // Bearer tokens
  
  // Credit cards
  /\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b/g,
  
  // SSN
  /\b\d{3}-\d{2}-\d{4}\b/g,
  
  // Email (basic pattern for debugging)
  /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g,
  
  // Phone numbers
  /\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g,
  
  // Common password patterns
  /password["\s]*[:=]["\s]*[^"\s]+/gi,
  /secret["\s]*[:=]["\s]*[^"\s]+/gi,
  /key["\s]*[:=]["\s]*[^"\s]+/gi,
];

const SENSITIVE_FIELDS = [
  'password',
  'apiKey',
  'apiSecret',
  'secret',
  'token',
  'accessToken',
  'refreshToken',
  'authorization',
  'encrypted_api_key',
  'encrypted_api_secret',
  'key_iv',
  'key_auth_tag',
  'user_salt',
  'ssn',
  'creditCard',
  'cvv'
];

class SecureLogger {
  constructor(isDevelopment = process.env.NODE_ENV === 'development') {
    this.isDevelopment = isDevelopment;
    this.logLevel = isDevelopment ? 'debug' : 'warn';
  }

  // Sanitize a single value
  sanitizeValue(value) {
    if (typeof value !== 'string') {
      return value;
    }

    let sanitized = value;
    
    // Replace sensitive patterns
    SENSITIVE_PATTERNS.forEach(pattern => {
      sanitized = sanitized.replace(pattern, (match) => {
        if (match.length <= 4) return '***';
        return match.substring(0, 2) + '*'.repeat(Math.max(4, match.length - 4)) + match.substring(match.length - 2);
      });
    });

    return sanitized;
  }

  // Sanitize an object recursively
  sanitizeObject(obj, depth = 0) {
    if (depth > 10) return '[Max Depth Reached]'; // Prevent infinite recursion
    if (obj === null || obj === undefined) return obj;
    
    if (typeof obj === 'string') {
      return this.sanitizeValue(obj);
    }
    
    if (typeof obj === 'number' || typeof obj === 'boolean') {
      return obj;
    }
    
    if (Array.isArray(obj)) {
      return obj.map(item => this.sanitizeObject(item, depth + 1));
    }
    
    if (typeof obj === 'object') {
      const sanitized = {};
      
      for (const [key, value] of Object.entries(obj)) {
        const keyLower = key.toLowerCase();
        
        // Check if this is a sensitive field
        const isSensitiveField = SENSITIVE_FIELDS.some(field => 
          keyLower.includes(field.toLowerCase())
        );
        
        if (isSensitiveField) {
          sanitized[key] = typeof value === 'string' && value.length > 0 
            ? `[${value.length} chars]` 
            : '[REDACTED]';
        } else {
          sanitized[key] = this.sanitizeObject(value, depth + 1);
        }
      }
      
      return sanitized;
    }
    
    return obj;
  }

  // Log with sanitization
  log(level, message, ...args) {
    const sanitizedArgs = args.map(arg => this.sanitizeObject(arg));
    
    // In production, limit logging levels
    if (!this.isDevelopment && level === 'debug') {
      return;
    }
    
    const timestamp = new Date().toISOString();
    const logMessage = typeof message === 'string' 
      ? this.sanitizeValue(message) 
      : this.sanitizeObject(message);
    
    const logEntry = {
      timestamp,
      level,
      message: logMessage,
      data: sanitizedArgs.length > 0 ? sanitizedArgs : undefined
    };
    
    // Use appropriate console method
    switch (level) {
      case 'error':
        console.error(`[${timestamp}] ERROR:`, logMessage, ...sanitizedArgs);
        break;
      case 'warn':
        console.warn(`[${timestamp}] WARN:`, logMessage, ...sanitizedArgs);
        break;
      case 'info':
        console.info(`[${timestamp}] INFO:`, logMessage, ...sanitizedArgs);
        break;
      case 'debug':
        if (this.isDevelopment) {
          console.debug(`[${timestamp}] DEBUG:`, logMessage, ...sanitizedArgs);
        }
        break;
      default:
        console.log(`[${timestamp}] LOG:`, logMessage, ...sanitizedArgs);
    }
    
    // In production, you might want to send logs to a monitoring service
    if (!this.isDevelopment && level === 'error') {
      // this.sendToMonitoringService(logEntry);
    }
  }

  debug(message, ...args) {
    this.log('debug', message, ...args);
  }

  info(message, ...args) {
    this.log('info', message, ...args);
  }

  warn(message, ...args) {
    this.log('warn', message, ...args);
  }

  error(message, ...args) {
    this.log('error', message, ...args);
  }

  // Audit logging for sensitive operations
  audit(operation, userId, details = {}) {
    const auditEntry = {
      operation,
      userId: userId || 'unknown',
      timestamp: new Date().toISOString(),
      details: this.sanitizeObject(details),
      userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'server',
      ip: details.ip || 'unknown'
    };
    
    console.info(`[AUDIT] ${operation} by ${userId}:`, auditEntry);
    
    // In production, send audit logs to a secure audit service
    // this.sendToAuditService(auditEntry);
  }

  // Test if a string contains sensitive data
  containsSensitiveData(str) {
    if (typeof str !== 'string') return false;
    
    return SENSITIVE_PATTERNS.some(pattern => pattern.test(str));
  }

  // Safe JSON stringify that handles circular references and sensitive data
  safeStringify(obj, space = 2) {
    const seen = new Set();
    
    return JSON.stringify(this.sanitizeObject(obj), (key, value) => {
      if (typeof value === 'object' && value !== null) {
        if (seen.has(value)) {
          return '[Circular Reference]';
        }
        seen.add(value);
      }
      return value;
    }, space);
  }
}

// Create singleton instance
const secureLogger = new SecureLogger();

// Export both the class and singleton
export default secureLogger;
export { SecureLogger };

// Convenience functions for backward compatibility
export const debug = (...args) => secureLogger.debug(...args);
export const info = (...args) => secureLogger.info(...args);
export const warn = (...args) => secureLogger.warn(...args);
export const error = (...args) => secureLogger.error(...args);
export const audit = (...args) => secureLogger.audit(...args);