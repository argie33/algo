/**
 * Unified CORS Manager - Environment-Aware CORS Handling
 * 
 * FEATURES:
 * ✅ Environment-specific CORS rules (production vs development)
 * ✅ API Gateway integration (works with existing CORS)
 * ✅ Security-first approach (no wildcards in production)
 * ✅ Error-safe CORS headers (always set before errors)
 * ✅ Centralized CORS configuration
 * ✅ Request/response validation
 */

// CORS Configuration by Environment
const CORS_CONFIGURATIONS = {
  production: {
    // Strict production CORS - specific origins only
    origins: [
      'https://your-production-domain.com',
      'https://www.your-production-domain.com',
      // Add your actual production domains here
    ],
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
    allowedHeaders: [
      'Content-Type',
      'Authorization', 
      'X-Requested-With',
      'X-Session-ID',
      'Accept',
      'Origin',
      'Cache-Control',
      'Pragma'
    ],
    exposedHeaders: [
      'Content-Length',
      'Content-Type', 
      'X-Request-ID',
      'X-Correlation-ID'
    ],
    credentials: true,
    maxAge: 86400, // 24 hours
    optionsSuccessStatus: 200
  },

  development: {
    // Relaxed development CORS - allow all for easier development
    origins: true, // Allow all origins in development
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'],
    allowedHeaders: [
      'Content-Type',
      'Authorization',
      'X-Requested-With', 
      'X-Session-ID',
      'Accept',
      'Origin',
      'Cache-Control',
      'Pragma',
      'X-Custom-Header' // Additional headers for development
    ],
    exposedHeaders: [
      'Content-Length',
      'Content-Type',
      'X-Request-ID',
      'X-Correlation-ID',
      'X-Debug-Info'
    ],
    credentials: true,
    maxAge: 0, // No caching in development
    optionsSuccessStatus: 200
  },

  test: {
    // Test environment CORS
    origins: ['http://localhost:3000', 'http://localhost:5173'],
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With'],
    exposedHeaders: ['Content-Length', 'Content-Type', 'X-Request-ID'],
    credentials: true,
    maxAge: 3600,
    optionsSuccessStatus: 200
  }
};

// Origin Validator
class OriginValidator {
  constructor(allowedOrigins) {
    this.allowedOrigins = allowedOrigins;
    this.originCache = new Map();
    this.cacheMaxSize = 1000;
  }

  isOriginAllowed(origin) {
    if (!origin) return false;

    // Check cache first
    if (this.originCache.has(origin)) {
      return this.originCache.get(origin);
    }

    let allowed = false;

    if (this.allowedOrigins === true) {
      // Allow all origins (development mode)
      allowed = true;
    } else if (Array.isArray(this.allowedOrigins)) {
      // Check against allowed origins list
      allowed = this.allowedOrigins.includes(origin);
      
      // Also check for localhost in development/test
      if (!allowed && this.isLocalhost(origin)) {
        const env = process.env.NODE_ENV;
        allowed = env === 'development' || env === 'test';
      }
    } else if (typeof this.allowedOrigins === 'function') {
      // Custom origin validation function
      allowed = this.allowedOrigins(origin);
    }

    // Cache the result
    this.cacheOrigin(origin, allowed);
    
    return allowed;
  }

  isLocalhost(origin) {
    try {
      const url = new URL(origin);
      return url.hostname === 'localhost' || 
             url.hostname === '127.0.0.1' ||
             url.hostname.endsWith('.localhost');
    } catch {
      return false;
    }
  }

  cacheOrigin(origin, allowed) {
    // Prevent cache from growing too large
    if (this.originCache.size >= this.cacheMaxSize) {
      // Remove oldest entries
      const oldestKeys = Array.from(this.originCache.keys()).slice(0, 100);
      oldestKeys.forEach(key => this.originCache.delete(key));
    }

    this.originCache.set(origin, allowed);
  }

  getStats() {
    return {
      cacheSize: this.originCache.size,
      allowedType: typeof this.allowedOrigins,
      isWildcard: this.allowedOrigins === true
    };
  }
}

// Main CORS Manager
class CorsManager {
  constructor() {
    this.environment = this.detectEnvironment();
    this.config = this.buildCorsConfig();
    this.originValidator = new OriginValidator(this.config.origins);
    
    console.log(`🌐 CORS Manager initialized for ${this.environment} environment`);
    this.logConfiguration();
  }

  detectEnvironment() {
    const nodeEnv = process.env.NODE_ENV;
    
    // Explicit environment detection
    if (nodeEnv === 'production') return 'production';
    if (nodeEnv === 'test') return 'test';
    if (nodeEnv === 'development') return 'development';
    
    // Default to production for security
    console.warn('⚠️ NODE_ENV not set, defaulting to production CORS mode');
    return 'production';
  }

  buildCorsConfig() {
    const baseConfig = CORS_CONFIGURATIONS[this.environment];
    
    if (!baseConfig) {
      console.error(`❌ No CORS configuration for environment: ${this.environment}`);
      return CORS_CONFIGURATIONS.production; // Fail-safe to production
    }

    // Override with environment-specific settings if available
    const envOverrides = {};
    
    // Check for environment variable overrides
    if (process.env.CORS_ORIGINS) {
      envOverrides.origins = process.env.CORS_ORIGINS.split(',').map(o => o.trim());
    }
    
    if (process.env.CORS_CREDENTIALS) {
      envOverrides.credentials = process.env.CORS_CREDENTIALS === 'true';
    }

    return { ...baseConfig, ...envOverrides };
  }

  logConfiguration() {
    console.log('🌐 CORS Configuration:', {
      environment: this.environment,
      origins: this.config.origins === true ? 'ALL (development)' : 
               Array.isArray(this.config.origins) ? this.config.origins.length + ' specific origins' :
               'custom function',
      methods: this.config.methods.length,
      credentials: this.config.credentials,
      maxAge: this.config.maxAge
    });
  }

  // Main CORS middleware - works with API Gateway
  middleware() {
    return (req, res, next) => {
      try {
        // Only set CORS headers if API Gateway hasn't already set them
        if (!this.hasApiGatewayCors(res)) {
          this.setCorsHeaders(req, res);
        } else {
          console.log('📡 Using API Gateway CORS headers');
        }

        // Handle preflight OPTIONS requests
        if (req.method === 'OPTIONS') {
          return this.handlePreflight(req, res);
        }

        next();
      } catch (error) {
        console.error('❌ CORS middleware error:', error);
        // Fail-safe: set basic CORS headers
        this.setFallbackCorsHeaders(res);
        next();
      }
    };
  }

  hasApiGatewayCors(res) {
    // Check if API Gateway has already set CORS headers
    return res.get('Access-Control-Allow-Origin') || 
           res.get('access-control-allow-origin');
  }

  setCorsHeaders(req, res) {
    const origin = req.headers.origin;
    
    // Validate and set origin
    if (this.originValidator.isOriginAllowed(origin)) {
      res.setHeader('Access-Control-Allow-Origin', origin);
    } else if (this.config.origins === true) {
      // Development mode - allow all
      res.setHeader('Access-Control-Allow-Origin', origin || '*');
    } else {
      // Production mode - deny unauthorized origins
      console.warn(`⚠️ Unauthorized origin blocked: ${origin}`);
      // Don't set Access-Control-Allow-Origin header
    }

    // Set other CORS headers
    res.setHeader('Access-Control-Allow-Methods', this.config.methods.join(', '));
    res.setHeader('Access-Control-Allow-Headers', this.config.allowedHeaders.join(', '));
    res.setHeader('Access-Control-Expose-Headers', this.config.exposedHeaders.join(', '));
    
    if (this.config.credentials) {
      res.setHeader('Access-Control-Allow-Credentials', 'true');
    }
    
    if (this.config.maxAge > 0) {
      res.setHeader('Access-Control-Max-Age', this.config.maxAge.toString());
    }

    // Add security headers
    res.setHeader('Vary', 'Origin, Access-Control-Request-Method, Access-Control-Request-Headers');
  }

  setFallbackCorsHeaders(res) {
    // Emergency fallback CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  }

  handlePreflight(req, res) {
    const origin = req.headers.origin;
    const requestMethod = req.headers['access-control-request-method'];
    const requestHeaders = req.headers['access-control-request-headers'];

    console.log(`🔍 CORS preflight: ${origin} → ${requestMethod}`);

    // Validate origin
    if (!this.originValidator.isOriginAllowed(origin)) {
      console.warn(`❌ Preflight rejected for origin: ${origin}`);
      return res.status(403).json({
        error: 'CORS policy violation',
        message: 'Origin not allowed'
      });
    }

    // Validate method
    if (requestMethod && !this.config.methods.includes(requestMethod)) {
      console.warn(`❌ Preflight rejected for method: ${requestMethod}`);
      return res.status(403).json({
        error: 'CORS policy violation', 
        message: 'Method not allowed'
      });
    }

    // Validate headers
    if (requestHeaders) {
      const requestedHeaders = requestHeaders.split(',').map(h => h.trim().toLowerCase());
      const allowedHeaders = this.config.allowedHeaders.map(h => h.toLowerCase());
      
      const unauthorizedHeaders = requestedHeaders.filter(h => !allowedHeaders.includes(h));
      if (unauthorizedHeaders.length > 0) {
        console.warn(`❌ Preflight rejected for headers: ${unauthorizedHeaders.join(', ')}`);
        return res.status(403).json({
          error: 'CORS policy violation',
          message: 'Headers not allowed'
        });
      }
    }

    // Send successful preflight response
    res.status(this.config.optionsSuccessStatus).end();
  }

  // Error handler integration - always sets CORS before sending errors
  handleError(error, req, res, next) {
    try {
      // CRITICAL: Always set CORS headers before sending error response
      if (!this.hasApiGatewayCors(res)) {
        this.setCorsHeaders(req, res);
      }

      // Determine error status and message
      const status = error.status || error.statusCode || 500;
      const message = error.message || 'Internal Server Error';
      
      // Create error response
      const errorResponse = {
        error: {
          type: error.name || 'Error',
          message: message,
          status: status,
          timestamp: new Date().toISOString(),
          requestId: req.headers['x-request-id'] || 'unknown'
        }
      };

      // Add debug info in development
      if (this.environment === 'development') {
        errorResponse.error.debug = {
          stack: error.stack,
          origin: req.headers.origin,
          corsApplied: true
        };
      }

      console.error(`🚨 CORS Error Handler: ${status} ${message}`);
      res.status(status).json(errorResponse);

    } catch (handlerError) {
      console.error('❌ CORS error handler failed:', handlerError);
      
      // Last resort: send basic error with fallback CORS
      this.setFallbackCorsHeaders(res);
      res.status(500).json({
        error: {
          type: 'InternalServerError',
          message: 'An unexpected error occurred',
          timestamp: new Date().toISOString()
        }
      });
    }
  }

  // Validate CORS request
  validateRequest(req) {
    const origin = req.headers.origin;
    const method = req.method;

    const validation = {
      valid: true,
      errors: [],
      warnings: []
    };

    // Check origin
    if (origin && !this.originValidator.isOriginAllowed(origin)) {
      validation.valid = false;
      validation.errors.push(`Origin '${origin}' not allowed`);
    }

    // Check method
    if (!this.config.methods.includes(method)) {
      validation.valid = false;
      validation.errors.push(`Method '${method}' not allowed`);
    }

    // Check for potential issues
    if (!origin && req.headers.referer) {
      validation.warnings.push('Request has referer but no origin header');
    }

    return validation;
  }

  // Get CORS status for monitoring
  getStatus() {
    return {
      environment: this.environment,
      config: {
        ...this.config,
        origins: Array.isArray(this.config.origins) ? 
          `${this.config.origins.length} specific origins` : 
          this.config.origins
      },
      originValidator: this.originValidator.getStats(),
      timestamp: new Date().toISOString()
    };
  }

  // Update CORS configuration (for runtime updates)
  updateConfiguration(newConfig) {
    console.log('🔄 Updating CORS configuration...');
    
    this.config = { ...this.config, ...newConfig };
    this.originValidator = new OriginValidator(this.config.origins);
    
    console.log('✅ CORS configuration updated');
    this.logConfiguration();
  }

  // Add allowed origin (for dynamic updates)
  addAllowedOrigin(origin) {
    if (Array.isArray(this.config.origins)) {
      if (!this.config.origins.includes(origin)) {
        this.config.origins.push(origin);
        this.originValidator = new OriginValidator(this.config.origins);
        console.log(`✅ Added allowed origin: ${origin}`);
      }
    } else {
      console.warn('⚠️ Cannot add origin: origins not configured as array');
    }
  }

  // Remove allowed origin
  removeAllowedOrigin(origin) {
    if (Array.isArray(this.config.origins)) {
      const index = this.config.origins.indexOf(origin);
      if (index > -1) {
        this.config.origins.splice(index, 1);
        this.originValidator = new OriginValidator(this.config.origins);
        console.log(`✅ Removed allowed origin: ${origin}`);
      }
    } else {
      console.warn('⚠️ Cannot remove origin: origins not configured as array');
    }
  }
}

// Create singleton instance
const corsManager = new CorsManager();

// Export middleware functions
const corsMiddleware = () => corsManager.middleware();

const corsErrorHandler = (error, req, res, next) => {
  corsManager.handleError(error, req, res, next);
};

const getCorsStatus = (req, res) => {
  try {
    res.json({
      status: 'healthy',
      cors: corsManager.getStatus()
    });
  } catch (error) {
    res.status(500).json({
      status: 'error',
      error: error.message
    });
  }
};

module.exports = {
  corsMiddleware,
  corsErrorHandler,
  getCorsStatus,
  corsManager
};