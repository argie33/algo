// Security Service
// Comprehensive input validation, rate limiting, and security monitoring

const crypto = require('crypto');

class SecurityService {
  constructor() {
    this.rateLimiters = new Map();
    this.securityEvents = [];
    this.blockedIPs = new Set();
    this.suspiciousPatterns = [
      /(<script[^>]*>.*?<\/script>)/gi,  // XSS attempts
      /(union\s+select)/gi,              // SQL injection
      /(drop\s+table)/gi,                // SQL injection
      /(exec\s*\()/gi,                   // Command injection
      /(\.\.\/)|(\.\.\\)/gi,             // Path traversal
      /(eval\s*\()/gi,                   // Code injection
      /(javascript:)/gi,                 // JavaScript protocol
      /(data:text\/html)/gi,             // Data URI XSS
      /(on\w+\s*=)/gi                    // Event handler injection
    ];
    
    this.validationSchemas = {
      symbol: /^[A-Z]{1,5}$/,
      email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
      password: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/,
      uuid: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
      apiKey: /^[A-Za-z0-9_-]{20,64}$/,
      amount: /^\d+(\.\d{1,2})?$/,
      percentage: /^(100|[1-9]?\d)(\.\d{1,2})?$/,
      date: /^\d{4}-\d{2}-\d{2}$/,
      timestamp: /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/
    };

    this.rateLimitConfigs = {
      'auth': { requests: 10, window: 15 * 60 * 1000, blockDuration: 30 * 60 * 1000 }, // 10 requests per 15 min
      'api': { requests: 1000, window: 60 * 60 * 1000, blockDuration: 10 * 60 * 1000 }, // 1000 requests per hour
      'upload': { requests: 20, window: 60 * 60 * 1000, blockDuration: 60 * 60 * 1000 }, // 20 uploads per hour
      'sensitive': { requests: 5, window: 60 * 1000, blockDuration: 5 * 60 * 1000 } // 5 requests per minute
    };
  }

  // Comprehensive input validation
  validateInput(input, schema, options = {}) {
    const { required = true, maxLength = 1000, allowNull = false } = options;

    // Null/undefined check
    if (input === null || input === undefined) {
      if (allowNull) return { valid: true, sanitized: null };
      if (required) return { valid: false, error: 'Field is required' };
      return { valid: true, sanitized: null };
    }

    // Convert to string for validation
    const stringInput = String(input);

    // Length check
    if (stringInput.length > maxLength) {
      return { 
        valid: false, 
        error: `Input too long: ${stringInput.length} > ${maxLength}` 
      };
    }

    // Check for suspicious patterns
    const suspiciousMatch = this.detectSuspiciousPatterns(stringInput);
    if (suspiciousMatch) {
      this.logSecurityEvent('SUSPICIOUS_INPUT', {
        pattern: suspiciousMatch,
        input: stringInput.substring(0, 100),
        timestamp: new Date().toISOString()
      });
      return { 
        valid: false, 
        error: 'Input contains potentially malicious content' 
      };
    }

    // Schema validation
    if (schema && this.validationSchemas[schema]) {
      const regex = this.validationSchemas[schema];
      if (!regex.test(stringInput)) {
        return { 
          valid: false, 
          error: `Input does not match required format for ${schema}` 
        };
      }
    }

    // Sanitize input
    const sanitized = this.sanitizeInput(stringInput);

    return { 
      valid: true, 
      sanitized,
      original: stringInput 
    };
  }

  // Detect suspicious patterns
  detectSuspiciousPatterns(input) {
    for (const pattern of this.suspiciousPatterns) {
      const match = input.match(pattern);
      if (match) {
        return match[0];
      }
    }
    return null;
  }

  // Sanitize input
  sanitizeInput(input) {
    return input
      .replace(/[<>\"']/g, '') // Remove potentially dangerous characters
      .replace(/\0/g, '') // Remove null bytes
      .replace(/\r\n|\r|\n/g, ' ') // Replace line breaks with spaces
      .trim()
      .substring(0, 10000); // Limit length
  }

  // Validate object against schema
  validateObject(obj, schema) {
    const errors = [];
    const sanitized = {};

    Object.entries(schema).forEach(([field, fieldSchema]) => {
      const value = obj[field];
      const validation = this.validateInput(
        value, 
        fieldSchema.type, 
        fieldSchema.options || {}
      );

      if (!validation.valid) {
        errors.push({
          field,
          error: validation.error,
          value: typeof value === 'string' ? value.substring(0, 50) : value
        });
      } else {
        sanitized[field] = validation.sanitized;
      }
    });

    return {
      valid: errors.length === 0,
      errors,
      sanitized
    };
  }

  // Rate limiting
  checkRateLimit(identifier, category = 'api', req = null) {
    const config = this.rateLimitConfigs[category];
    const now = Date.now();
    const windowStart = now - config.window;

    // Check if IP is blocked
    if (this.blockedIPs.has(identifier)) {
      this.logSecurityEvent('BLOCKED_ACCESS_ATTEMPT', {
        identifier,
        category,
        ip: req?.ip,
        userAgent: req?.get('User-Agent'),
        timestamp: new Date().toISOString()
      });
      return {
        allowed: false,
        reason: 'IP temporarily blocked',
        retryAfter: config.blockDuration
      };
    }

    // Get or create rate limiter for this identifier
    if (!this.rateLimiters.has(identifier)) {
      this.rateLimiters.set(identifier, {
        requests: [],
        violations: 0,
        lastViolation: null
      });
    }

    const limiter = this.rateLimiters.get(identifier);

    // Remove old requests outside the window
    limiter.requests = limiter.requests.filter(timestamp => timestamp > windowStart);

    // Check if limit exceeded
    if (limiter.requests.length >= config.requests) {
      limiter.violations++;
      limiter.lastViolation = now;

      // Block IP after multiple violations
      if (limiter.violations >= 3) {
        this.blockedIPs.add(identifier);
        setTimeout(() => {
          this.blockedIPs.delete(identifier);
        }, config.blockDuration);

        this.logSecurityEvent('IP_BLOCKED', {
          identifier,
          category,
          violations: limiter.violations,
          ip: req?.ip,
          timestamp: new Date().toISOString()
        });
      }

      this.logSecurityEvent('RATE_LIMIT_EXCEEDED', {
        identifier,
        category,
        requests: limiter.requests.length,
        limit: config.requests,
        window: config.window,
        violations: limiter.violations,
        timestamp: new Date().toISOString()
      });

      return {
        allowed: false,
        reason: 'Rate limit exceeded',
        retryAfter: config.window,
        requests: limiter.requests.length,
        limit: config.requests
      };
    }

    // Add current request
    limiter.requests.push(now);

    return {
      allowed: true,
      requests: limiter.requests.length,
      limit: config.requests,
      windowReset: now + config.window
    };
  }

  // Security headers middleware
  getSecurityHeaders() {
    return {
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'X-XSS-Protection': '1; mode=block',
      'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
      'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://api.* wss://*",
      'Referrer-Policy': 'strict-origin-when-cross-origin',
      'Permissions-Policy': 'geolocation=(), microphone=(), camera=()'
    };
  }

  // Generate CSRF token
  generateCSRFToken(sessionId) {
    const timestamp = Date.now().toString();
    const randomBytes = crypto.randomBytes(16).toString('hex');
    const payload = `${sessionId}-${timestamp}-${randomBytes}`;
    
    return crypto
      .createHash('sha256')
      .update(payload)
      .digest('hex');
  }

  // Validate CSRF token
  validateCSRFToken(token, sessionId, maxAge = 3600000) { // 1 hour default
    if (!token || typeof token !== 'string') {
      return false;
    }

    try {
      // In a real implementation, you'd store and validate against stored tokens
      // This is a simplified version
      const isValidFormat = /^[a-f0-9]{64}$/.test(token);
      return isValidFormat;
    } catch (error) {
      return false;
    }
  }

  // Log security events
  logSecurityEvent(type, details) {
    const event = {
      id: crypto.randomUUID(),
      type,
      timestamp: new Date().toISOString(),
      details,
      severity: this.getEventSeverity(type)
    };

    this.securityEvents.push(event);

    // Keep only recent events (last 1000)
    if (this.securityEvents.length > 1000) {
      this.securityEvents = this.securityEvents.slice(-1000);
    }

    // Log to console for monitoring
    console.log(`[SECURITY] ${type}:`, details);

    return event;
  }

  // Get event severity
  getEventSeverity(type) {
    const severityMap = {
      'SUSPICIOUS_INPUT': 'HIGH',
      'RATE_LIMIT_EXCEEDED': 'MEDIUM',
      'IP_BLOCKED': 'HIGH',
      'BLOCKED_ACCESS_ATTEMPT': 'HIGH',
      'AUTHENTICATION_FAILURE': 'HIGH',
      'AUTHORIZATION_FAILURE': 'MEDIUM',
      'DATA_VALIDATION_FAILURE': 'LOW',
      'UNUSUAL_ACTIVITY': 'MEDIUM'
    };
    return severityMap[type] || 'LOW';
  }

  // Password strength validation
  validatePassword(password) {
    const checks = {
      length: password.length >= 8,
      lowercase: /[a-z]/.test(password),
      uppercase: /[A-Z]/.test(password),
      number: /\d/.test(password),
      special: /[@$!%*?&]/.test(password),
      noCommonPatterns: !this.containsCommonPatterns(password)
    };

    const score = Object.values(checks).filter(Boolean).length;
    let strength = 'WEAK';
    
    if (score >= 5) strength = 'STRONG';
    else if (score >= 4) strength = 'MODERATE';

    return {
      valid: score >= 4,
      strength,
      score,
      checks,
      suggestions: this.getPasswordSuggestions(checks)
    };
  }

  // Check for common password patterns
  containsCommonPatterns(password) {
    const commonPatterns = [
      /123456/,
      /password/i,
      /qwerty/i,
      /admin/i,
      /letmein/i,
      /welcome/i,
      /123abc/i
    ];

    return commonPatterns.some(pattern => pattern.test(password));
  }

  // Get password improvement suggestions
  getPasswordSuggestions(checks) {
    const suggestions = [];
    
    if (!checks.length) suggestions.push('Use at least 8 characters');
    if (!checks.lowercase) suggestions.push('Include lowercase letters');
    if (!checks.uppercase) suggestions.push('Include uppercase letters');
    if (!checks.number) suggestions.push('Include numbers');
    if (!checks.special) suggestions.push('Include special characters (@$!%*?&)');
    if (!checks.noCommonPatterns) suggestions.push('Avoid common patterns or dictionary words');

    return suggestions;
  }

  // Monitor for unusual activity patterns
  detectUnusualActivity(userId, activity) {
    const userKey = `user_${userId}`;
    const now = Date.now();
    const windowSize = 60 * 60 * 1000; // 1 hour
    
    if (!this.rateLimiters.has(userKey)) {
      this.rateLimiters.set(userKey, {
        requests: [],
        activities: [],
        locations: new Set(),
        userAgents: new Set()
      });
    }

    const userData = this.rateLimiters.get(userKey);
    
    // Track activity
    userData.activities.push({
      type: activity.type,
      timestamp: now,
      ip: activity.ip,
      userAgent: activity.userAgent,
      location: activity.location
    });

    // Clean old activities
    userData.activities = userData.activities.filter(a => a.timestamp > now - windowSize);

    // Detect unusual patterns
    const patterns = this.analyzeActivityPatterns(userData.activities);
    
    if (patterns.unusual) {
      this.logSecurityEvent('UNUSUAL_ACTIVITY', {
        userId,
        patterns,
        activityCount: userData.activities.length,
        timestamp: new Date().toISOString()
      });
    }

    return patterns;
  }

  // Analyze activity patterns for anomalies
  analyzeActivityPatterns(activities) {
    if (activities.length < 5) {
      return { unusual: false, score: 0 };
    }

    let score = 0;
    const checks = {
      highFrequency: false,
      multipleLocations: false,
      multipleUserAgents: false,
      offHours: false,
      rapidRequests: false
    };

    // Check for high frequency
    if (activities.length > 100) {
      checks.highFrequency = true;
      score += 30;
    }

    // Check for multiple IP addresses
    const uniqueIPs = new Set(activities.map(a => a.ip));
    if (uniqueIPs.size > 3) {
      checks.multipleLocations = true;
      score += 25;
    }

    // Check for multiple user agents
    const uniqueUserAgents = new Set(activities.map(a => a.userAgent));
    if (uniqueUserAgents.size > 2) {
      checks.multipleUserAgents = true;
      score += 20;
    }

    // Check for off-hours activity (assuming business hours 9-17 UTC)
    const offHoursActivities = activities.filter(a => {
      const hour = new Date(a.timestamp).getUTCHours();
      return hour < 9 || hour > 17;
    });
    if (offHoursActivities.length > activities.length * 0.7) {
      checks.offHours = true;
      score += 15;
    }

    // Check for rapid consecutive requests
    const rapidRequests = activities.filter((a, i) => {
      if (i === 0) return false;
      return a.timestamp - activities[i - 1].timestamp < 1000; // Less than 1 second apart
    });
    if (rapidRequests.length > 10) {
      checks.rapidRequests = true;
      score += 20;
    }

    return {
      unusual: score > 50,
      score,
      checks,
      riskLevel: score > 70 ? 'HIGH' : score > 50 ? 'MEDIUM' : 'LOW'
    };
  }

  // Get security metrics
  getSecurityMetrics(timeWindow = 3600000) { // 1 hour default
    const now = Date.now();
    const windowStart = now - timeWindow;
    
    const recentEvents = this.securityEvents.filter(
      event => new Date(event.timestamp).getTime() > windowStart
    );

    const eventCounts = recentEvents.reduce((counts, event) => {
      counts[event.type] = (counts[event.type] || 0) + 1;
      return counts;
    }, {});

    const severityCounts = recentEvents.reduce((counts, event) => {
      counts[event.severity] = (counts[event.severity] || 0) + 1;
      return counts;
    }, {});

    return {
      timeWindow,
      totalEvents: recentEvents.length,
      eventTypes: eventCounts,
      severityBreakdown: severityCounts,
      blockedIPs: this.blockedIPs.size,
      activeRateLimiters: this.rateLimiters.size,
      topEvents: Object.entries(eventCounts)
        .sort(([,a], [,b]) => b - a)
        .slice(0, 5),
      recentHighSeverityEvents: recentEvents
        .filter(e => e.severity === 'HIGH')
        .slice(-10),
      timestamp: new Date().toISOString()
    };
  }

  // Clear old data to prevent memory leaks
  cleanup() {
    const now = Date.now();
    const maxAge = 24 * 60 * 60 * 1000; // 24 hours

    // Clean old rate limiter data
    for (const [key, limiter] of this.rateLimiters.entries()) {
      if (limiter.requests) {
        limiter.requests = limiter.requests.filter(timestamp => 
          now - timestamp < maxAge
        );
      }
      if (limiter.activities) {
        limiter.activities = limiter.activities.filter(activity =>
          now - activity.timestamp < maxAge
        );
      }
      
      // Remove empty limiters
      if (limiter.requests?.length === 0 && limiter.activities?.length === 0) {
        this.rateLimiters.delete(key);
      }
    }

    // Clean old security events
    const cutoff = new Date(now - maxAge).toISOString();
    this.securityEvents = this.securityEvents.filter(
      event => event.timestamp > cutoff
    );

    console.log(`Security service cleanup completed. Active limiters: ${this.rateLimiters.size}, Events: ${this.securityEvents.length}`);
  }

  // Middleware factory
  createSecurityMiddleware() {
    return {
      // Rate limiting middleware
      rateLimit: (category = 'api') => (req, res, next) => {
        const identifier = req.ip || req.connection.remoteAddress;
        const result = this.checkRateLimit(identifier, category, req);
        
        if (!result.allowed) {
          return res.status(429).json({
            success: false,
            error: 'Rate limit exceeded',
            message: result.reason,
            retryAfter: result.retryAfter
          });
        }
        
        // Add rate limit headers
        res.set({
          'X-RateLimit-Limit': result.limit,
          'X-RateLimit-Remaining': result.limit - result.requests,
          'X-RateLimit-Reset': new Date(result.windowReset).toISOString()
        });
        
        next();
      },

      // Security headers middleware
      securityHeaders: (req, res, next) => {
        const headers = this.getSecurityHeaders();
        res.set(headers);
        next();
      },

      // Input validation middleware
      validateInput: (schema) => (req, res, next) => {
        const validation = this.validateObject(req.body, schema);
        
        if (!validation.valid) {
          return res.status(400).json({
            success: false,
            error: 'Validation failed',
            details: validation.errors
          });
        }
        
        req.validatedBody = validation.sanitized;
        next();
      }
    };
  }
}

module.exports = SecurityService;