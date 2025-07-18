/**
 * SQL Injection Protection Middleware
 * Comprehensive protection against SQL injection attacks
 */

class SQLInjectionProtection {
  constructor() {
    // Dangerous SQL patterns that could indicate injection attempts
    this.dangerousPatterns = [
      // Union-based injection
      /(\b(union|UNION)\s+(all\s+)?(select|SELECT))/i,
      
      // Boolean-based blind injection
      /(\b(and|AND|or|OR)\s+[\d\w\s]*=[\d\w\s]*)/i,
      
      // Time-based blind injection
      /(sleep\s*\(|waitfor\s+delay|pg_sleep\s*\()/i,
      
      // Stacked queries
      /;\s*(drop|DROP|delete|DELETE|insert|INSERT|update|UPDATE|create|CREATE)/i,
      
      // Information schema queries
      /(information_schema|INFORMATION_SCHEMA)/i,
      
      // Comment-based injection
      /(\/\*|\*\/|--|\#)/,
      
      // Function calls that shouldn't be in user input
      /(char\s*\(|ascii\s*\(|substring\s*\(|mid\s*\()/i,
      
      // Hex encoding attempts
      /(0x[0-9a-f]+)/i,
      
      // SQL keywords that shouldn't be in user input
      /\b(alter|ALTER|exec|EXEC|execute|EXECUTE|cast|CAST|convert|CONVERT)\b/i
    ];

    // Allowed field names for dynamic queries (whitelist)
    this.allowedUserFields = new Set([
      'first_name',
      'last_name', 
      'email',
      'phone',
      'notification_preferences',
      'theme_preferences',
      'timezone',
      'language',
      'currency_preference'
    ]);

    // Allowed API key providers
    this.allowedProviders = new Set([
      'alpaca',
      'polygon', 
      'finnhub',
      'yahoo',
      'alpha_vantage'
    ]);

    // Allowed symbols pattern (alphanumeric + common symbols)
    this.allowedSymbolPattern = /^[A-Z0-9\.\-_]{1,10}$/;
  }

  /**
   * Validate input against SQL injection patterns
   */
  validateInput(input, fieldName = 'unknown') {
    if (!input || typeof input !== 'string') {
      return { valid: true, sanitized: input };
    }

    // Check against dangerous patterns
    for (const pattern of this.dangerousPatterns) {
      if (pattern.test(input)) {
        console.warn(`🚨 SQL injection attempt detected in field '${fieldName}': ${input.substring(0, 100)}`);
        return {
          valid: false,
          error: 'Invalid input detected',
          risk: 'HIGH',
          pattern: pattern.toString(),
          field: fieldName
        };
      }
    }

    // Basic sanitization
    const sanitized = input
      .replace(/[\x00-\x1F\x7F]/g, '') // Remove control characters
      .trim();

    return { valid: true, sanitized };
  }

  /**
   * Validate field names for dynamic queries
   */
  validateFieldName(fieldName, allowedFields = this.allowedUserFields) {
    if (!fieldName || typeof fieldName !== 'string') {
      return false;
    }

    // Must be in whitelist
    if (!allowedFields.has(fieldName)) {
      console.warn(`🚨 Unauthorized field access attempt: ${fieldName}`);
      return false;
    }

    // Additional pattern validation
    if (!/^[a-z_][a-z0-9_]*$/.test(fieldName)) {
      console.warn(`🚨 Invalid field name pattern: ${fieldName}`);
      return false;
    }

    return true;
  }

  /**
   * Validate API provider names
   */
  validateProvider(provider) {
    if (!provider || typeof provider !== 'string') {
      return false;
    }

    return this.allowedProviders.has(provider.toLowerCase());
  }

  /**
   * Validate stock symbols
   */
  validateSymbol(symbol) {
    if (!symbol || typeof symbol !== 'string') {
      return false;
    }

    return this.allowedSymbolPattern.test(symbol.toUpperCase());
  }

  /**
   * Sanitize environment variable usage
   */
  sanitizeEnvVar(varName, value) {
    // Validate environment variable name
    if (!/^[A-Z_][A-Z0-9_]*$/.test(varName)) {
      throw new Error(`Invalid environment variable name: ${varName}`);
    }

    // Sanitize value based on expected type
    if (varName.includes('PASSWORD') || varName.includes('SECRET') || varName.includes('KEY')) {
      // Never log sensitive values
      return '[REDACTED]';
    }

    // Basic sanitization for non-sensitive values
    if (typeof value === 'string') {
      return value.replace(/[\x00-\x1F\x7F]/g, '').trim();
    }

    return value;
  }

  /**
   * Create secure parameterized query builder
   */
  buildSecureQuery(baseQuery, conditions = {}, allowedFields = null) {
    const params = [];
    const whereClause = [];
    let paramIndex = 1;

    // Use provided allowed fields or default user fields
    const validFields = allowedFields || this.allowedUserFields;

    for (const [field, value] of Object.entries(conditions)) {
      // Validate field name
      if (!this.validateFieldName(field, validFields)) {
        throw new Error(`Invalid field name: ${field}`);
      }

      // Validate field value
      const validation = this.validateInput(String(value), field);
      if (!validation.valid) {
        throw new Error(`Invalid value for field ${field}: ${validation.error}`);
      }

      whereClause.push(`${field} = $${paramIndex}`);
      params.push(validation.sanitized);
      paramIndex++;
    }

    // Construct final query
    let finalQuery = baseQuery;
    if (whereClause.length > 0) {
      if (baseQuery.toLowerCase().includes('where')) {
        finalQuery += ` AND ${whereClause.join(' AND ')}`;
      } else {
        finalQuery += ` WHERE ${whereClause.join(' AND ')}`;
      }
    }

    return { query: finalQuery, params };
  }

  /**
   * Middleware function for Express
   */
  middleware() {
    return (req, res, next) => {
      // Validate all request parameters
      this.validateRequestParams(req);
      
      // Add security methods to request
      req.sqlSecurity = {
        validateInput: this.validateInput.bind(this),
        validateFieldName: this.validateFieldName.bind(this),
        validateProvider: this.validateProvider.bind(this),
        validateSymbol: this.validateSymbol.bind(this),
        buildSecureQuery: this.buildSecureQuery.bind(this)
      };

      next();
    };
  }

  /**
   * Validate all request parameters
   */
  validateRequestParams(req) {
    const validateObject = (obj, path = '') => {
      for (const [key, value] of Object.entries(obj)) {
        const fullPath = path ? `${path}.${key}` : key;
        
        if (typeof value === 'string') {
          const validation = this.validateInput(value, fullPath);
          if (!validation.valid) {
            // Log security event
            console.warn(`🚨 SQL injection attempt in ${fullPath}:`, {
              ip: req.ip,
              userAgent: req.headers['user-agent'],
              path: req.path,
              field: fullPath,
              pattern: validation.pattern,
              risk: validation.risk
            });
            
            throw new Error('Invalid input detected');
          }
        } else if (typeof value === 'object' && value !== null) {
          validateObject(value, fullPath);
        }
      }
    };

    // Validate query parameters
    if (req.query && Object.keys(req.query).length > 0) {
      validateObject(req.query, 'query');
    }

    // Validate body parameters
    if (req.body && Object.keys(req.body).length > 0) {
      validateObject(req.body, 'body');
    }

    // Validate route parameters
    if (req.params && Object.keys(req.params).length > 0) {
      validateObject(req.params, 'params');
    }
  }

  /**
   * Log security events
   */
  logSecurityEvent(event) {
    const securityLog = {
      timestamp: new Date().toISOString(),
      type: 'SQL_INJECTION_ATTEMPT',
      severity: event.risk || 'MEDIUM',
      details: event,
      source: 'SQLInjectionProtection'
    };

    console.warn('🚨 SECURITY EVENT:', JSON.stringify(securityLog));
    
    // In production, also send to security monitoring system
    // securityMonitor.alert(securityLog);
  }
}

module.exports = SQLInjectionProtection;