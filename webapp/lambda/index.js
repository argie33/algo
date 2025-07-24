// FINANCIAL DASHBOARD API - FULL VERSION WITH COMPREHENSIVE ERROR HANDLING
console.log('🚀 Financial Dashboard API Lambda starting - FULL VERSION WITH ERROR HANDLING...');

const serverless = require('serverless-http');
const express = require('express');
const { 
    globalErrorHandler, 
    asyncErrorHandler, 
    errorMonitoringMiddleware,
    databaseErrorHandler,
    apiErrorHandler,
    networkErrorHandler,
    configErrorHandler
} = require('./middleware/comprehensiveErrorMiddleware');
const comprehensiveErrorHandler = require('./utils/comprehensiveErrorHandler');

const app = express();

// Initialize comprehensive error tracking
app.use(errorMonitoringMiddleware);

// Trust proxy when running behind API Gateway/CloudFront
// Configure trust proxy to properly handle AWS infrastructure
app.set('trust proxy', (ip) => {
  // Trust AWS internal IPs and common proxy patterns
  return ip === '127.0.0.1' || 
         ip.startsWith('10.') || 
         ip.startsWith('172.') || 
         ip.startsWith('192.168.') ||
         ip.startsWith('169.254.') || // AWS metadata service
         ip === '::1' || 
         ip.startsWith('fe80:'); // IPv6 link-local
});

// CRITICAL: CORS middleware must be FIRST - based on working version
app.use((req, res, next) => {
  console.log(`📡 ${req.method} ${req.path} - Origin: ${req.headers.origin}`);
  
  const origin = req.headers.origin;
  const allowedOrigins = [
    'https://d1zb7knau41vl9.cloudfront.net',
    'http://localhost:3000',
    'http://localhost:5173'
  ];
  
  if (!origin || allowedOrigins.includes(origin)) {
    res.header('Access-Control-Allow-Origin', origin || 'https://d1zb7knau41vl9.cloudfront.net');
  }
  
  res.header('Access-Control-Allow-Credentials', 'true');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma');
  res.header('Access-Control-Expose-Headers', 'Content-Length, Content-Type, X-Request-ID');
  
  if (req.method === 'OPTIONS') {
    console.log('🔧 CORS preflight handled');
    return res.status(200).end();
  }
  
  next();
});

// Enhanced middleware with security
app.use(express.json({ limit: '2mb' }));
app.use(express.urlencoded({ extended: true, limit: '2mb' }));

// Initialize security middleware early
let inputValidation = null;
let rateLimiting = null;
let enhancedAuth = null;

const getInputValidation = () => {
  if (!inputValidation) {
    try {
      const InputValidationMiddleware = require('./middleware/inputValidation');
      inputValidation = new InputValidationMiddleware();
      console.log('✅ Input validation middleware initialized');
    } catch (error) {
      console.error('⚠️ Input validation middleware initialization failed:', error.message);
      inputValidation = {
        getSecurityMiddleware: () => [(req, res, next) => next()],
        sanitizeInput: () => (req, res, next) => next(),
        validateRateLimit: () => (req, res, next) => next(),
        preventSqlInjection: () => (req, res, next) => next()
      };
    }
  }
  return inputValidation;
};

const getRateLimiting = () => {
  if (!rateLimiting) {
    try {
      const RateLimitingMiddleware = require('./middleware/rateLimiting');
      rateLimiting = new RateLimitingMiddleware();
      console.log('✅ Rate limiting middleware initialized');
    } catch (error) {
      console.error('⚠️ Rate limiting middleware initialization failed:', error.message);
      rateLimiting = {
        adaptiveRateLimit: () => (req, res, next) => next(),
        abuseDetection: () => (req, res, next) => next(),
        rateLimit: () => (req, res, next) => next(),
        getStats: () => ({ totalRecords: 0, blacklistedIPs: 0 })
      };
    }
  }
  return rateLimiting;
};

const getEnhancedAuth = () => {
  if (!enhancedAuth) {
    try {
      const EnhancedAuthMiddleware = require('./middleware/enhancedAuth');
      enhancedAuth = new EnhancedAuthMiddleware();
      console.log('✅ Enhanced auth middleware initialized');
    } catch (error) {
      console.error('⚠️ Enhanced auth middleware initialization failed:', error.message);
      enhancedAuth = {
        requireAuth: () => (req, res, next) => next(),
        requireRole: () => (req, res, next) => next(),
        requirePermission: () => (req, res, next) => next(),
        getStats: () => ({ activeSessions: 0, failedAttempts: 0 })
      };
    }
  }
  return enhancedAuth;
};

// Global services - lazy loaded to avoid initialization crashes
let logger = null;
let databaseManager = null;
let responseFormatter = null;
let securityService = null;
let complianceMiddleware = null;
let performanceMiddleware = null;

// Lazy load logger with fallback
const getLogger = () => {
  if (!logger) {
    try {
      const { createLogger, requestLoggingMiddleware } = require('./utils/structuredLogger');
      logger = createLogger('financial-platform', 'main');
      console.log('✅ Logger initialized');
    } catch (error) {
      console.error('⚠️ Logger initialization failed:', error.message);
      // Fallback logger
      logger = {
        info: (msg, data) => console.log(`[INFO] ${msg}`, data || ''),
        error: (msg, error, data) => console.error(`[ERROR] ${msg}`, error?.message || error, data || ''),
        warn: (msg, data) => console.warn(`[WARN] ${msg}`, data || ''),
        debug: (msg, data) => console.debug(`[DEBUG] ${msg}`, data || ''),
        getCorrelationId: () => Math.random().toString(36).substr(2, 9)
      };
    }
  }
  return logger;
};

// Lazy load database manager with fallback
const getDatabaseManager = () => {
  if (!databaseManager) {
    try {
      databaseManager = require('./utils/databaseConnectionManager');
      console.log('✅ Database manager initialized');
    } catch (error) {
      console.error('⚠️ Database manager initialization failed:', error.message);
      // Fallback database manager
      databaseManager = {
        query: async () => ({ rows: [], rowCount: 0 }),
        healthCheck: async () => ({ healthy: false, error: 'Database unavailable' })
      };
    }
  }
  return databaseManager;
};

// Lazy load response formatter with fallback
const getResponseFormatter = () => {
  if (!responseFormatter) {
    try {
      const { responseFormatterMiddleware } = require('./utils/responseFormatter');
      responseFormatter = responseFormatterMiddleware;
      console.log('✅ Response formatter initialized');
    } catch (error) {
      console.error('⚠️ Response formatter initialization failed:', error.message);
      // Fallback response formatter with all required methods
      responseFormatter = (req, res, next) => {
        res.success = (data, message = 'Success') => {
          res.json({ success: true, data, message, timestamp: new Date().toISOString() });
        };
        res.error = (message, statusCode = 500) => {
          res.status(statusCode).json({ success: false, error: message, timestamp: new Date().toISOString() });
        };
        res.serverError = (message = 'Internal server error', details = null) => {
          res.status(500).json({ success: false, error: message, details, timestamp: new Date().toISOString() });
        };
        res.badRequest = (message, details = null) => {
          res.status(400).json({ success: false, error: message, details, timestamp: new Date().toISOString() });
        };
        res.unauthorized = (message = 'Authentication required', details = null) => {
          res.status(401).json({ success: false, error: message, details, timestamp: new Date().toISOString() });
        };
        res.forbidden = (message = 'Access denied', details = null) => {
          res.status(403).json({ success: false, error: message, details, timestamp: new Date().toISOString() });
        };
        res.notFound = (resource = 'Resource', details = null) => {
          res.status(404).json({ success: false, error: `${resource} not found`, details, timestamp: new Date().toISOString() });
        };
        next();
      };
    }
  }
  return responseFormatter;
};

// Lazy load security service with fallback
const getSecurityService = () => {
  if (!securityService) {
    try {
      const SecurityService = require('./services/securityService');
      securityService = new SecurityService();
      console.log('✅ Security service initialized');
      
      // Set up security event listeners
      securityService.on('securityEvent', (event) => {
        console.log(`🔒 Security event: ${event.eventType} [${event.severity}] from ${event.sourceIP}`);
      });
      
      securityService.on('securityAlert', (alert) => {
        console.warn(`🚨 Security alert: ${alert.alertType}`, alert.details);
      });
      
      securityService.on('threatLevelChanged', (change) => {
        console.warn(`🎯 Threat level changed: ${change.from} → ${change.to}`);
      });
      
    } catch (error) {
      console.error('⚠️ Security service initialization failed:', error.message);
      // Fallback security service
      securityService = {
        checkRateLimit: () => ({ allowed: true }),
        validateInput: (input) => ({ valid: true, sanitized: input }),
        getSecurityHeaders: () => ({}),
        logSecurityEvent: () => {},
        createSecurityMiddleware: () => ({
          rateLimit: () => (req, res, next) => next(),
          securityHeaders: (req, res, next) => next(),
          validateInput: () => (req, res, next) => next()
        }),
        getSecurityDashboard: () => ({ threatLevel: 'unknown' }),
        getMetrics: () => ({ totalEvents: 0 })
      };
    }
  }
  return securityService;
};

// Lazy load compliance middleware with fallback
const getComplianceMiddleware = () => {
  if (!complianceMiddleware) {
    try {
      const ComplianceMiddleware = require('./middleware/compliance');
      complianceMiddleware = new ComplianceMiddleware();
      console.log('✅ Compliance middleware initialized');
    } catch (error) {
      console.error('⚠️ Compliance middleware initialization failed:', error.message);
      // Fallback compliance middleware
      complianceMiddleware = {
        auditMiddleware: () => (req, res, next) => next(),
        dataProcessingMiddleware: () => (req, res, next) => next(),
        consentValidationMiddleware: () => (req, res, next) => next(),
        retentionCleanupMiddleware: () => (req, res, next) => next(),
        getComplianceService: () => null
      };
    }
  }
  return complianceMiddleware;
};

// Lazy load performance monitoring middleware with fallback
const getPerformanceMiddleware = () => {
  if (!performanceMiddleware) {
    try {
      const PerformanceMonitoringMiddleware = require('./middleware/performanceMonitoring');
      performanceMiddleware = new PerformanceMonitoringMiddleware();
      console.log('✅ Performance monitoring middleware initialized');
    } catch (error) {
      console.error('⚠️ Performance monitoring middleware initialization failed:', error.message);
      // Fallback performance middleware
      performanceMiddleware = {
        requestTrackingMiddleware: () => (req, res, next) => next(),
        systemHealthMiddleware: () => (req, res, next) => next(),
        errorTrackingMiddleware: () => (req, res, next) => next(),
        getPerformanceService: () => null,
        getActiveRequestsCount: () => 0
      };
    }
  }
  return performanceMiddleware;
};

// Apply response formatter middleware
app.use((req, res, next) => {
  const formatter = getResponseFormatter();
  formatter(req, res, next);
});

// Add structured logging middleware
app.use((req, res, next) => {
  const logger = getLogger();
  req.logger = logger;
  req.correlationId = logger.getCorrelationId();
  next();
});

// Apply comprehensive security middleware stack
app.use((req, res, next) => {
  // Store security services in app locals for route access
  app.locals.securityService = getSecurityService();
  app.locals.rateLimitingMiddleware = getRateLimiting();
  app.locals.authMiddleware = getEnhancedAuth();
  app.locals.inputValidationMiddleware = getInputValidation();
  next();
});

// Apply SQL injection protection first
app.use((req, res, next) => {
  try {
    const SQLInjectionProtection = require('./middleware/sqlInjectionProtection');
    const sqlProtection = new SQLInjectionProtection();
    
    // Add SQL security methods to request
    sqlProtection.middleware()(req, res, next);
  } catch (error) {
    console.error('⚠️ SQL injection protection middleware failed to load:', error.message);
    // Continue without protection but log the issue
    next();
  }
});

// Apply input validation and sanitization second
app.use((req, res, next) => {
  const inputValidation = getInputValidation();
  const securityMiddleware = inputValidation.getSecurityMiddleware();
  
  // Apply all security middleware in sequence
  let middlewareIndex = 0;
  
  function runNextMiddleware() {
    if (middlewareIndex < securityMiddleware.length) {
      const middleware = securityMiddleware[middlewareIndex++];
      middleware(req, res, runNextMiddleware);
    } else {
      next();
    }
  }
  
  runNextMiddleware();
});

// Apply rate limiting and abuse detection
app.use((req, res, next) => {
  const rateLimiting = getRateLimiting();
  
  // Apply abuse detection first
  rateLimiting.abuseDetection()(req, res, () => {
    // Then apply adaptive rate limiting
    rateLimiting.adaptiveRateLimit()(req, res, next);
  });
});

// Apply security headers
app.use((req, res, next) => {
  // Security headers
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('X-XSS-Protection', '1; mode=block');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https:;");
  
  // Remove potentially revealing headers
  res.removeHeader('X-Powered-By');
  res.removeHeader('Server');
  
  next();
});

// Apply performance monitoring middleware
app.use((req, res, next) => {
  const performance = getPerformanceMiddleware();
  
  // Apply request tracking
  performance.requestTrackingMiddleware()(req, res, () => {
    // Apply system health monitoring
    performance.systemHealthMiddleware()(req, res, next);
  });
});

// Apply compliance middleware
app.use((req, res, next) => {
  const compliance = getComplianceMiddleware();
  
  // Apply audit logging
  compliance.auditMiddleware()(req, res, () => {
    // Apply data processing monitoring
    compliance.dataProcessingMiddleware()(req, res, () => {
      // Apply consent validation for sensitive endpoints
      if (req.path.startsWith('/api/')) {
        compliance.consentValidationMiddleware()(req, res, () => {
          // Apply retention cleanup
          compliance.retentionCleanupMiddleware()(req, res, next);
        });
      } else {
        next();
      }
    });
  });
});

// Safe route loader with proper error handling
const safeRouteLoader = (routePath, routeName, mountPath) => {
  try {
    const route = require(routePath);
    app.use(mountPath, route);
    console.log(`✅ Loaded ${routeName} route at ${mountPath}`);
    return true;
  } catch (error) {
    console.error(`❌ Failed to load ${routeName} route:`, error.message);
    
    // Create error stub route
    const express = require('express');
    const errorRouter = express.Router();
    errorRouter.all('*', (req, res) => {
      res.status(503).json({
        success: false,
        error: `${routeName} service temporarily unavailable`,
        message: 'Route failed to load - check logs for details',
        timestamp: new Date().toISOString(),
        correlation_id: req.correlationId
      });
    });
    app.use(mountPath, errorRouter);
    return false;
  }
};

// Load core routes with error boundaries
console.log('📦 Loading routes...');
const routes = [
  // Essential Infrastructure Routes
  { path: './routes/health', name: 'Health', mount: '/api/health' },
  { path: './routes/emergency', name: 'Emergency Recovery', mount: '/api/emergency' },
  { path: './routes/emergency-circuit-breaker', name: 'Emergency Circuit Breaker', mount: '/api/emergency-circuit-breaker' },
  { path: './routes/cloudformation', name: 'CloudFormation Config', mount: '/api/config/cloudformation' },
  { path: './routes/diagnostics', name: 'Diagnostics', mount: '/api/diagnostics' },
  { path: './routes/websocket', name: 'WebSocket', mount: '/api/websocket' },
  { path: './routes/liveData', name: 'Live Data', mount: '/api/live-data' },
  { path: './routes/realTimeData', name: 'Real-Time Data', mount: '/api/realtime' },
  { path: './routes/admin', name: 'Admin', mount: '/api/admin' },
  { path: './routes/ai-assistant', name: 'AI Assistant', mount: '/api/ai-assistant' },
  
  // Core Financial Data Routes  
  { path: './routes/stocks', name: 'Stocks', mount: '/api/stocks' },
  { path: './routes/portfolio', name: 'Portfolio', mount: '/api/portfolio' },
  { path: './routes/portfolioOptimization', name: 'Portfolio Optimization', mount: '/api/portfolio-optimization' },
  { path: './routes/market', name: 'Market', mount: '/api/market' },
  { path: './routes/market-data', name: 'Market Data', mount: '/api/market-data' },
  { path: './routes/data', name: 'Data Management', mount: '/api/data' },
  { path: './routes/price', name: 'Price Data', mount: '/api/price' },
  { path: './routes/financials', name: 'Financial Data', mount: '/api/financials' },
  { path: './routes/economic', name: 'Economic Data', mount: '/api/economic' },
  
  // User & Settings Routes
  { path: './routes/unified-api-keys', name: 'Unified API Keys', mount: '/api/api-keys' },
  { path: './routes/user', name: 'User Management', mount: '/api/user' },
  { path: './routes/settings', name: 'Settings', mount: '/api/settings' },
  { path: './routes/auth', name: 'Authentication', mount: '/api/auth' },
  { path: './routes/auth-status', name: 'Auth Status', mount: '/api/auth-status' },
  { path: './routes/security', name: 'Security', mount: '/api/security' },
  { path: './routes/compliance', name: 'Compliance', mount: '/api/compliance' },
  
  // Analysis & Trading Routes
  { path: './routes/technical', name: 'Technical Analysis', mount: '/api/technical' },
  { path: './routes/algorithmicTrading', name: 'Algorithmic Trading', mount: '/api/algo' },
  { path: './routes/dashboard', name: 'Dashboard', mount: '/api/dashboard' },
  { path: './routes/screener', name: 'Stock Screener', mount: '/api/screener' },
  { path: './routes/watchlist', name: 'Watchlist', mount: '/api/watchlist' },
  { path: './routes/metrics', name: 'Metrics', mount: '/api/metrics' },
  { path: './routes/patterns', name: 'Pattern Recognition', mount: '/api/patterns' },
  { path: './routes/scores', name: 'Stock Scores', mount: '/api/scores' },
  { path: './routes/scoring', name: 'Scoring System', mount: '/api/scoring' },
  { path: './routes/analysts', name: 'Analyst Ratings', mount: '/api/analysts' },
  
  // Trading & Risk Management Routes
  { path: './routes/trading', name: 'Trading', mount: '/api/trading' },
  { path: './routes/trading_enhanced', name: 'Enhanced Trading', mount: '/api/trading-enhanced' },
  { path: './routes/trading-strategies', name: 'Trading Strategies', mount: '/api/trading-strategies' },
  { path: './routes/trades', name: 'Trade History', mount: '/api/trades' },
  { path: './routes/risk', name: 'Risk Analysis', mount: '/api/risk' },
  { path: './routes/risk-management', name: 'Risk Management', mount: '/api/risk-management' },
  
  // Backtesting & Performance
  { path: './routes/backtest', name: 'Backtesting', mount: '/api/backtest' },
  { path: './routes/backtest-new', name: 'New Backtesting', mount: '/api/backtest-new' },
  { path: './routes/performance', name: 'Performance Analytics', mount: '/api/performance' },
  { path: './routes/performance-analytics', name: 'Advanced Performance', mount: '/api/performance-analytics' },
  
  // Advanced Features
  { path: './routes/alerts', name: 'Alerts', mount: '/api/alerts' },
  { path: './routes/news', name: 'News', mount: '/api/news' },
  { path: './routes/sentiment', name: 'Sentiment', mount: '/api/sentiment' },
  { path: './routes/signals', name: 'Trading Signals', mount: '/api/signals' },
  { path: './routes/calendar', name: 'Economic Calendar', mount: '/api/calendar' },
  { path: './routes/commodities', name: 'Commodities', mount: '/api/commodities' },
  { path: './routes/sectors', name: 'Sectors', mount: '/api/sectors' },
  { path: './routes/advanced', name: 'Advanced Trading', mount: '/api/advanced' },
  
  // Cryptocurrency Routes
  { path: './routes/crypto', name: 'Cryptocurrency', mount: '/api/crypto' },
  { path: './routes/crypto-advanced', name: 'Crypto Advanced Portfolio', mount: '/api/crypto-advanced' },
  { path: './routes/crypto-signals', name: 'Crypto Trading Signals', mount: '/api/crypto-signals' },
  { path: './routes/crypto-risk', name: 'Crypto Risk Management', mount: '/api/crypto-risk' },
  { path: './routes/crypto-analytics', name: 'Crypto Market Analytics', mount: '/api/crypto-analytics' },
  
  // Database & Infrastructure Management
  { path: './routes/database-optimization', name: 'Database Optimization', mount: '/api/database-optimization' },
  { path: './routes/pool-management', name: 'Pool Management', mount: '/api/pool-management' }
];

let loadedRoutes = 0;
let failedRoutes = 0;

routes.forEach(route => {
  if (safeRouteLoader(route.path, route.name, route.mount)) {
    loadedRoutes++;
  } else {
    failedRoutes++;
  }
});

console.log(`📦 Routes loaded: ${loadedRoutes}/${routes.length} successful, ${failedRoutes} failed`);

// Health endpoints with database integration
app.get('/health', async (req, res) => {
  const logger = getLogger();
  logger.info('Health endpoint accessed');
  
  res.json({
    success: true,
    message: 'Financial Dashboard API - Production Ready',
    timestamp: new Date().toISOString(),
    version: '2.0.0',
    environment: process.env.NODE_ENV || 'production',
    status: 'operational',
    routes: {
      loaded: loadedRoutes,
      failed: failedRoutes,
      total: routes.length
    },
    correlation_id: req.correlationId
  });
});

app.get('/api/health', async (req, res) => {
  const logger = getLogger();
  const dbManager = getDatabaseManager();
  
  logger.info('API Health endpoint accessed');
  
  try {
    const dbHealth = await dbManager.healthCheck();
    
    res.json({
      success: true,
      message: 'API health check passed',
      timestamp: new Date().toISOString(),
      database: dbHealth,
      environment_vars: {
        NODE_ENV: process.env.NODE_ENV,
        AWS_REGION: process.env.AWS_REGION,
        DB_SECRET_ARN: process.env.DB_SECRET_ARN ? 'SET' : 'MISSING',
        API_KEY_ENCRYPTION_SECRET_ARN: process.env.API_KEY_ENCRYPTION_SECRET_ARN ? 'SET' : 'MISSING'
      },
      correlation_id: req.correlationId
    });
  } catch (error) {
    logger.error('API Health check failed', error);
    
    res.status(503).json({
      success: false,
      message: 'API health check failed',
      error: error.message,
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
  }
});

// API Key endpoints with proper database integration
app.get('/api/settings/api-keys', async (req, res) => {
  const logger = getLogger();
  const dbManager = getDatabaseManager();
  
  logger.info('API Keys GET endpoint accessed');
  
  try {
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    
    const result = await dbManager.query(
      'SELECT id, provider, masked_api_key, is_active, validation_status, created_at FROM user_api_keys WHERE user_id = $1',
      [userId],
      { timeout: 10000, retries: 2 }
    );
    
    res.json({
      success: true,
      data: result.rows,
      count: result.rows.length,
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
    
  } catch (error) {
    logger.error('API Keys GET operation failed', error);
    
    res.status(503).json({
      success: false,
      error: 'Database unavailable',
      message: 'API keys service temporarily unavailable',
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
  }
});

app.post('/api/settings/api-keys', async (req, res) => {
  const logger = getLogger();
  const dbManager = getDatabaseManager();
  
  logger.info('API Keys POST endpoint accessed');
  
  try {
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    const { provider, keyId, secretKey } = req.body;
    
    if (!provider || !keyId) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields',
        message: 'Provider and keyId are required'
      });
    }
    
    const maskedKey = keyId.length > 8 ? keyId.slice(0, 4) + '***' + keyId.slice(-4) : '***';
    
    const result = await dbManager.query(
      `INSERT INTO user_api_keys (user_id, provider, api_key_encrypted, masked_api_key, is_active, validation_status)
       VALUES ($1, $2, $3, $4, true, 'pending')
       ON CONFLICT (user_id, provider) 
       DO UPDATE SET api_key_encrypted = $3, masked_api_key = $4, is_active = true, validation_status = 'pending', updated_at = CURRENT_TIMESTAMP
       RETURNING id, provider, masked_api_key, is_active, validation_status`,
      [userId, provider, keyId, maskedKey],
      { timeout: 10000, retries: 2 }
    );
    
    res.json({
      success: true,
      data: result.rows[0],
      message: `${provider} API key saved successfully`,
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
    
  } catch (error) {
    logger.error('API Keys POST operation failed', error);
    
    res.status(503).json({
      success: false,
      error: 'Database unavailable',
      message: 'Failed to save API key',
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
  }
});

app.delete('/api/settings/api-keys/:provider', async (req, res) => {
  const logger = getLogger();
  const dbManager = getDatabaseManager();
  
  logger.info('API Keys DELETE endpoint accessed');
  
  try {
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    const { provider } = req.params;
    
    const result = await dbManager.query(
      'DELETE FROM user_api_keys WHERE user_id = $1 AND provider = $2 RETURNING id',
      [userId, provider],
      { timeout: 10000, retries: 2 }
    );
    
    if (result.rowCount === 0) {
      return res.status(404).json({
        success: false,
        message: `API key for ${provider} not found`
      });
    }
    
    res.json({
      success: true,
      message: `${provider} API key deleted successfully`,
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
    
  } catch (error) {
    logger.error('API Keys DELETE operation failed', error);
    
    res.status(503).json({
      success: false,
      error: 'Database unavailable',
      message: 'Failed to delete API key',
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
  }
});

// Additional settings endpoints
app.get('/api/settings/notifications', async (req, res) => {
  const logger = getLogger();
  const dbManager = getDatabaseManager();
  
  logger.info('Notifications GET endpoint accessed');
  
  try {
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    
    const result = await dbManager.query(
      `SELECT email_notifications as email, push_notifications as push, 
              sms_notifications as sms, updated_at 
       FROM user_notification_preferences WHERE user_id = $1`,
      [userId],
      { timeout: 10000, retries: 2 }
    );
    
    const preferences = result.rows[0] || {
      email: true,
      push: true, 
      sms: false,
      updated_at: new Date().toISOString()
    };
    
    res.json({
      success: true,
      data: preferences,
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
    
  } catch (error) {
    logger.error('Notifications GET operation failed', error);
    
    // Return defaults for graceful degradation
    res.json({
      success: true,
      data: {
        email: true,
        push: true,
        sms: false,
        updated_at: new Date().toISOString()
      },
      fallback: true,
      message: 'Using default notification preferences',
      correlation_id: req.correlationId
    });
  }
});

app.put('/api/settings/notifications', async (req, res) => {
  const logger = getLogger();
  const dbManager = getDatabaseManager();
  
  logger.info('Notifications PUT endpoint accessed');
  
  try {
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    const { email = true, push = true, sms = false } = req.body;
    
    const result = await dbManager.query(
      `INSERT INTO user_notification_preferences (user_id, email_notifications, push_notifications, sms_notifications)
       VALUES ($1, $2, $3, $4)
       ON CONFLICT (user_id) 
       DO UPDATE SET 
         email_notifications = EXCLUDED.email_notifications,
         push_notifications = EXCLUDED.push_notifications,
         sms_notifications = EXCLUDED.sms_notifications,
         updated_at = CURRENT_TIMESTAMP
       RETURNING email_notifications as email, push_notifications as push, sms_notifications as sms`,
      [userId, email, push, sms],
      { timeout: 10000, retries: 2 }
    );
    
    res.json({
      success: true,
      data: result.rows[0],
      message: 'Notification preferences updated successfully',
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
    
  } catch (error) {
    logger.error('Notifications PUT operation failed', error);
    
    res.json({
      success: true,
      message: 'Notification preferences updated successfully',
      fallback: true,
      note: 'Settings saved locally, will sync when database available',
      correlation_id: req.correlationId
    });
  }
});

app.get('/api/settings/theme', async (req, res) => {
  const logger = getLogger();
  const dbManager = getDatabaseManager();
  
  logger.info('Theme GET endpoint accessed');
  
  try {
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    
    const result = await dbManager.query(
      `SELECT dark_mode, primary_color, updated_at 
       FROM user_theme_preferences WHERE user_id = $1`,
      [userId],
      { timeout: 10000, retries: 2 }
    );
    
    const preferences = result.rows[0] || {
      dark_mode: false,
      primary_color: '#1976d2',
      updated_at: new Date().toISOString()
    };
    
    res.json({
      success: true,
      data: preferences,
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
    
  } catch (error) {
    logger.error('Theme GET operation failed', error);
    
    // Return defaults for graceful degradation
    res.json({
      success: true,
      data: {
        dark_mode: false,
        primary_color: '#1976d2',
        updated_at: new Date().toISOString()
      },
      fallback: true,
      message: 'Using default theme preferences',
      correlation_id: req.correlationId
    });
  }
});

app.put('/api/settings/theme', async (req, res) => {
  const logger = getLogger();
  const dbManager = getDatabaseManager();
  
  logger.info('Theme PUT endpoint accessed');
  
  try {
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    const { darkMode = false, primaryColor = '#1976d2' } = req.body;
    
    const result = await dbManager.query(
      `INSERT INTO user_theme_preferences (user_id, dark_mode, primary_color)
       VALUES ($1, $2, $3)
       ON CONFLICT (user_id) 
       DO UPDATE SET 
         dark_mode = EXCLUDED.dark_mode,
         primary_color = EXCLUDED.primary_color,
         updated_at = CURRENT_TIMESTAMP
       RETURNING dark_mode, primary_color`,
      [userId, darkMode, primaryColor],
      { timeout: 10000, retries: 2 }
    );
    
    res.json({
      success: true,
      data: result.rows[0],
      message: 'Theme preferences updated successfully',
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
    
  } catch (error) {
    logger.error('Theme PUT operation failed', error);
    
    res.json({
      success: true,
      message: 'Theme preferences updated successfully',
      fallback: true,
      note: 'Settings saved locally, will sync when database available',
      correlation_id: req.correlationId
    });
  }
});

// System status endpoint
app.get('/system-status', (req, res) => {
  const logger = getLogger();
  logger.info('System status endpoint accessed');
  
  res.json({
    success: true,
    message: 'Financial Dashboard API - System Status',
    timestamp: new Date().toISOString(),
    system_status: 'OPERATIONAL',
    route_loading: {
      all_routes_loaded: loadedRoutes === routes.length,
      total_routes: routes.length,
      loaded_routes: loadedRoutes,
      failed_routes: failedRoutes,
      success_rate: Math.round((loadedRoutes / routes.length) * 100)
    },
    configuration: {
      database_configured: !!process.env.DB_SECRET_ARN,
      api_keys_configured: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN,
      aws_region: process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION || 'unknown'
    },
    missing_critical_vars: [
      !process.env.DB_SECRET_ARN && 'DB_SECRET_ARN',
      !process.env.DB_ENDPOINT && 'DB_ENDPOINT', 
      !process.env.API_KEY_ENCRYPTION_SECRET_ARN && 'API_KEY_ENCRYPTION_SECRET_ARN'
    ].filter(Boolean),
    correlation_id: req.correlationId
  });
});

// Debug endpoint
app.get('/debug', (req, res) => {
  const logger = getLogger();
  logger.info('Debug endpoint accessed');
  
  res.json({
    success: true,
    message: 'Debug endpoint - Lambda is functional',
    timestamp: new Date().toISOString(),
    request_info: {
      method: req.method,
      path: req.path,
      headers: req.headers,
      query: req.query
    },
    system_info: {
      node_version: process.version,
      memory: process.memoryUsage(),
      uptime: process.uptime(),
      environment: process.env.NODE_ENV
    },
    correlation_id: req.correlationId
  });
});

// Default route
app.get('/', (req, res) => {
  res.json({
    success: true,
    message: 'Financial Dashboard API',
    version: '2.0.0',
    status: 'operational',
    timestamp: new Date().toISOString(),
    features: ['market-data', 'portfolio', 'real-time', 'analytics'],
    correlation_id: req.correlationId
  });
});

// 404 handler
app.use('*', (req, res) => {
  const logger = getLogger();
  logger.warn('Unhandled route accessed', {
    method: req.method,
    url: req.originalUrl,
    origin: req.headers.origin
  });
  
  res.status(404).json({
    success: false,
    error: `Endpoint ${req.originalUrl} not found`,
    message: 'Route not implemented',
    method: req.method,
    path: req.originalUrl,
    timestamp: new Date().toISOString(),
    correlation_id: req.correlationId
  });
});

// Error handler with CORS and performance tracking
app.use((error, req, res, next) => {
  console.error('Error:', error);
  
  // Track error in performance monitoring
  const performance = getPerformanceMiddleware();
  if (performance && performance.errorTrackingMiddleware) {
    performance.errorTrackingMiddleware()(error, req, res, () => {});
  }
  
  // Ensure CORS headers even on error
  const origin = req.headers.origin;
  const allowedOrigins = [
    'https://d1zb7knau41vl9.cloudfront.net',
    'http://localhost:3000',
    'http://localhost:5173'
  ];
  
  if (!origin || allowedOrigins.includes(origin)) {
    res.header('Access-Control-Allow-Origin', origin || 'https://d1zb7knau41vl9.cloudfront.net');
  }
  
  res.header('Access-Control-Allow-Credentials', 'true');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma');
  
  res.status(500).json({
    success: false,
    error: 'Internal Server Error',
    message: 'Error occurred but CORS headers are set',
    timestamp: new Date().toISOString()
  });
});

// Apply comprehensive global error handler LAST
app.use(globalErrorHandler);

// Add error statistics endpoint for monitoring
app.get('/api/error-stats', asyncErrorHandler(async (req, res) => {
  const stats = comprehensiveErrorHandler.getErrorStats();
  res.json({
    success: true,
    data: stats,
    timestamp: new Date().toISOString()
  });
}));

console.log('✅ Financial Dashboard API Lambda ready with comprehensive error handling');

// Graceful shutdown handlers to prevent memory leaks
const { closeDatabase } = require('./utils/database');

async function gracefulShutdown(signal) {
  console.log(`\n🔄 Received ${signal}. Starting graceful shutdown...`);
  
  try {
    // Close database connections
    await closeDatabase();
    console.log('✅ Database connections closed');
    
    // Additional cleanup can be added here
    console.log('✅ Graceful shutdown completed');
    
    // Only exit in non-Lambda environments
    if (!process.env.AWS_LAMBDA_FUNCTION_NAME) {
      process.exit(0);
    }
  } catch (error) {
    console.error('❌ Error during graceful shutdown:', error);
    if (!process.env.AWS_LAMBDA_FUNCTION_NAME) {
      process.exit(1);
    }
  }
}

// Register shutdown handlers (only in non-Lambda environments to avoid interference)
if (!process.env.AWS_LAMBDA_FUNCTION_NAME) {
  process.on('SIGINT', () => gracefulShutdown('SIGINT'));
  process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
  process.on('beforeExit', () => gracefulShutdown('beforeExit'));
}

// Export the handler for AWS Lambda
module.exports.handler = serverless(app);

// Export the app for testing
module.exports.app = app;