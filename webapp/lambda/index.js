// Load environment variables first
require('dotenv').config();

// Financial Dashboard API - Lambda Function
// Updated: 2025-07-14 - 503 ERROR FIX with Centralized Secrets Management - v11.0 - DEPLOY NOW

// Load secrets from AWS Secrets Manager BEFORE anything else
const secretsLoader = require('./utils/secretsLoader');

const serverless = require('serverless-http');
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const { initializeDatabase, initForLambda } = require('./utils/database');
const environmentValidator = require('./utils/environmentValidator');
const errorHandler = require('./middleware/errorHandler');
const { responseFormatterMiddleware } = require('./utils/responseFormatter');
const { requestLoggingMiddleware } = require('./utils/logger');
const { 
  rateLimitConfigs, 
  sqlInjectionPrevention, 
  xssPrevention, 
  requestSizeLimit 
} = require('./middleware/validation');

// Import routes with safe loading to prevent 502 errors
let stockRoutes, scoresRoutes, metricsRoutes, healthRoutes, marketRoutes, marketDataRoutes;
let analystRoutes, financialRoutes, tradingRoutes, technicalRoutes, calendarRoutes, signalsRoutes;
let dataRoutes, backtestRoutes, authRoutes, portfolioRoutes, scoringRoutes, priceRoutes;
let settingsRoutes, patternsRoutes, sectorsRoutes, watchlistRoutes, aiAssistantRoutes;
let tradesRoutes, cryptoRoutes, screenerRoutes, dashboardRoutes, alertsRoutes;
let commoditiesRoutes, economicRoutes, websocketRoutes, poolManagementRoutes, tradingStrategiesRoutes;
let riskManagementRoutes;

// Safe route loading function with improved error handling
const safeRequire = (path, name) => {
  try {
    const route = require(path);
    console.log(`✅ Loaded ${name} route successfully`);
    
    // Validate that the route is actually an Express router
    if (!route || typeof route !== 'function') {
      throw new Error(`Route ${name} does not export a valid Express router`);
    }
    
    return route;
  } catch (error) {
    console.error(`❌ Failed to load ${name} route:`, {
      message: error.message,
      stack: error.stack,
      path: path
    });
    
    // Return a placeholder router with detailed error information
    const express = require('express');
    const placeholder = express.Router();
    
    placeholder.use('*', (req, res) => {
      console.error(`🚨 Request to failed route ${name}: ${req.method} ${req.path}`);
      res.status(503).json({
        error: 'Service temporarily unavailable',
        message: `${name} service failed to load`,
        details: process.env.NODE_ENV === 'development' ? {
          errorMessage: error.message,
          routePath: path,
          requestPath: req.path,
          method: req.method
        } : undefined,
        timestamp: new Date().toISOString(),
        retryAfter: 30
      });
    });
    
    return placeholder;
  }
};

// Load routes safely
console.log('🔄 Loading routes safely...');
stockRoutes = safeRequire('./routes/stocks', 'Stocks');
scoresRoutes = safeRequire('./routes/scores', 'Scores');
metricsRoutes = safeRequire('./routes/metrics', 'Metrics');
healthRoutes = safeRequire('./routes/health', 'Health');
marketRoutes = safeRequire('./routes/market', 'Market');
marketDataRoutes = safeRequire('./routes/market-data', 'Market Data');
analystRoutes = safeRequire('./routes/analysts', 'Analysts');
financialRoutes = safeRequire('./routes/financials', 'Financials');
tradingRoutes = safeRequire('./routes/trading', 'Trading');
technicalRoutes = safeRequire('./routes/technical', 'Technical');
calendarRoutes = safeRequire('./routes/calendar', 'Calendar');
signalsRoutes = safeRequire('./routes/signals', 'Signals');
dataRoutes = safeRequire('./routes/data', 'Data');
backtestRoutes = safeRequire('./routes/backtest', 'Backtest');
authRoutes = safeRequire('./routes/auth', 'Auth');
portfolioRoutes = safeRequire('./routes/portfolio', 'Portfolio');
scoringRoutes = safeRequire('./routes/scoring', 'Scoring');
priceRoutes = safeRequire('./routes/price', 'Price');
settingsRoutes = safeRequire('./routes/settings', 'Settings');
patternsRoutes = safeRequire('./routes/patterns', 'Patterns');
sectorsRoutes = safeRequire('./routes/sectors', 'Sectors');
watchlistRoutes = safeRequire('./routes/watchlist', 'Watchlist');
aiAssistantRoutes = safeRequire('./routes/ai-assistant', 'AI Assistant');
tradesRoutes = safeRequire('./routes/trades', 'Trades');
cryptoRoutes = safeRequire('./routes/crypto', 'Crypto');
screenerRoutes = safeRequire('./routes/screener', 'Screener');
dashboardRoutes = safeRequire('./routes/dashboard', 'Dashboard');
alertsRoutes = safeRequire('./routes/alerts', 'Alerts');
commoditiesRoutes = safeRequire('./routes/commodities', 'Commodities');
economicRoutes = safeRequire('./routes/economic', 'Economic');
websocketRoutes = safeRequire('./routes/websocket', 'WebSocket');
poolManagementRoutes = safeRequire('./routes/pool-management', 'Pool Management');
tradingStrategiesRoutes = safeRequire('./routes/trading-strategies', 'Trading Strategies');
riskManagementRoutes = safeRequire('./routes/risk-management', 'Risk Management');
performanceAnalyticsRoutes = safeRequire('./routes/performance-analytics', 'Performance Analytics');
console.log('✅ Route loading completed');

// Validate environment variables
console.log('🔍 Validating environment variables...');
const envValidation = environmentValidator.validateEnvironment();
if (!envValidation.isValid) {
  console.error('❌ Environment validation failed - some services may not work correctly');
  envValidation.missingRequired.forEach(result => {
    console.error(`   - ${result.name}: ${result.error}`);
  });
} else {
  console.log('✅ Environment validation passed');
}

// Initialize secrets before creating the app
let secretsInitialized = false;

// Initialize the Express app
const app = express();

// Trust proxy when running behind API Gateway/CloudFront
app.set('trust proxy', true);

// Lambda database initialization with connection warming
// This runs during Lambda cold start to reduce request latency
let dbInitPromise = null;
const initializeLambdaDatabase = () => {
  if (!dbInitPromise) {
    console.log('🚀 Starting Lambda database initialization...');
    dbInitPromise = initForLambda().catch(error => {
      console.error('❌ Lambda database initialization failed:', error);
      dbInitPromise = null; // Reset so it can be retried
      return false;
    });
  }
  return dbInitPromise;
};

// Start database initialization immediately during cold start
initializeLambdaDatabase();

// Secure CORS Configuration
app.use((req, res, next) => {
  const origin = req.headers.origin;
  const allowedOrigins = (process.env.ALLOWED_ORIGINS || '').split(',').filter(Boolean);
  
  // Default allowed origins for development
  const defaultAllowedOrigins = [
    'http://localhost:3000',
    'http://localhost:5173',
    'https://d1zb7knau41vl9.cloudfront.net',  // Production CloudFront domain
    'https://your-domain.com'  // Replace with actual production domain
  ];
  
  const finalAllowedOrigins = allowedOrigins.length > 0 ? allowedOrigins : defaultAllowedOrigins;
  
  // Only allow requests from specific origins
  if (origin && finalAllowedOrigins.includes(origin)) {
    res.header('Access-Control-Allow-Origin', origin);
  } else if (!origin) {
    // Allow requests without origin (like from Postman, curl, etc.) in development
    if (process.env.NODE_ENV !== 'production') {
      res.header('Access-Control-Allow-Origin', '*');
    }
  }
  
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With');
  res.header('Access-Control-Allow-Credentials', 'true');
  res.header('Access-Control-Max-Age', '86400');
  
  // Handle preflight OPTIONS requests
  if (req.method === 'OPTIONS') {
    res.status(200).end();
    return;
  }
  
  next();
});

// Enhanced security middleware for enterprise production deployment
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
      fontSrc: ["'self'", "https://fonts.gstatic.com"],
      imgSrc: ["'self'", "data:", "https:", "blob:"],
      scriptSrc: ["'self'", "'unsafe-inline'"],
      connectSrc: ["'self'", "wss:", "https:"],
      frameSrc: ["'none'"],
      objectSrc: ["'none'"],
      baseUri: ["'self'"],
      formAction: ["'self'"],
      upgradeInsecureRequests: [],
    },
  },
  hsts: {
    maxAge: 31536000, // 1 year
    includeSubDomains: true,
    preload: true
  },
  frameguard: { action: 'deny' },
  noSniff: true,
  xssFilter: true,
  referrerPolicy: { policy: 'strict-origin-when-cross-origin' },
  permittedCrossDomainPolicies: false,
  crossOriginEmbedderPolicy: false, // Disabled for financial data APIs
  crossOriginOpenerPolicy: { policy: 'same-origin' },
  crossOriginResourcePolicy: { policy: 'cross-origin' }
}));

// HTTPS enforcement and additional security headers for financial applications
app.use((req, res, next) => {
  // Force HTTPS in production (behind ALB/CloudFront)
  if (process.env.NODE_ENV === 'production' && req.header('X-Forwarded-Proto') !== 'https') {
    console.log(`🔒 Redirecting HTTP to HTTPS: ${req.method} ${req.url}`);
    return res.redirect(301, `https://${req.header('host')}${req.url}`);
  }
  
  // Prevent MIME type sniffing
  res.setHeader('X-Content-Type-Options', 'nosniff');
  
  // Prevent clickjacking
  res.setHeader('X-Frame-Options', 'DENY');
  
  // Enable XSS protection
  res.setHeader('X-XSS-Protection', '1; mode=block');
  
  // Strict transport security (HSTS)
  res.setHeader('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload');
  
  // Referrer policy
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  
  // Feature policy for financial applications
  res.setHeader('Permissions-Policy', 
    'geolocation=(), microphone=(), camera=(), payment=(), usb=(), ' +
    'screen-wake-lock=(), web-share=(), gyroscope=(), magnetometer=()');
  
  // DNS prefetch control for privacy
  res.setHeader('X-DNS-Prefetch-Control', 'off');
  
  // Disable client-side caching for API responses
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, private');
  res.setHeader('Pragma', 'no-cache');
  res.setHeader('Expires', '0');
  
  // Extra security for financial data endpoints
  if (req.path.includes('/portfolio') || req.path.includes('/trading') || req.path.includes('/api-key')) {
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate, private');
    res.setHeader('Surrogate-Control', 'no-store');
    res.setHeader('X-Download-Options', 'noopen');
    res.setHeader('X-Permitted-Cross-Domain-Policies', 'none');
  }
  
  // Server identification obfuscation
  res.removeHeader('X-Powered-By');
  res.setHeader('Server', 'Financial-API');
  
  // Cross-origin policy for financial security
  res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  res.setHeader('Cross-Origin-Embedder-Policy', 'credentialless');
  
  // API rate limiting headers
  res.setHeader('X-RateLimit-Limit', '1000');
  res.setHeader('X-RateLimit-Window', '3600');
  
  // Debug logging for routing issues
  if (req.path.includes('/screen')) {
    console.log(`🔍 Request to screen endpoint: ${req.method} ${req.path}`);
    console.log(`🔍 Full URL: ${req.url}`);
    console.log(`🔍 Base URL: ${req.baseUrl}`);
    console.log(`🔍 Original URL: ${req.originalUrl}`);
  }
  
  next();
});

// CORS configuration (allow API Gateway origins)
app.use(cors({
  origin: (origin, callback) => {
    console.log('CORS check for origin:', origin);
    
    // Allow requests with no origin (like mobile apps or curl requests)
    if (!origin) {
      return callback(null, true);
    }
    
    // Allow API Gateway, CloudFront, and localhost origins
    if (origin.includes('.execute-api.') || 
        origin.includes('.cloudfront.net') || 
        origin.includes('localhost') ||
        origin.includes('127.0.0.1') ||
        origin === process.env.FRONTEND_URL) {
      console.log('CORS allowed for origin:', origin);
      callback(null, true);
    } else {
      console.warn('CORS blocked origin:', origin);
      callback(new Error('Not allowed by CORS'));
    }
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With', 'X-Session-ID'],
  optionsSuccessStatus: 200
}));

// Secure CORS middleware - restrict origins to approved domains only
app.use((req, res, next) => {
  const origin = req.headers.origin;
  
  console.log(`🌐 CORS middleware - Method: ${req.method}, Origin: ${origin}, Path: ${req.path}`);
  
  // Define allowed origins for production security
  const allowedOrigins = [
    'https://d1zb7knau41vl9.cloudfront.net', // Production CloudFront
    'http://localhost:3000',                 // Local development
    'http://localhost:5173',                 // Vite dev server
    'https://your-domain.com'                // Replace with actual domain
  ];
  
  // Add environment-specific origins
  const envOrigins = (process.env.ALLOWED_ORIGINS || '').split(',').filter(Boolean);
  allowedOrigins.push(...envOrigins);
  
  // Determine if origin is allowed
  let allowOrigin = false;
  if (!origin) {
    // Allow requests without origin only in development
    allowOrigin = process.env.NODE_ENV !== 'production';
  } else {
    allowOrigin = allowedOrigins.includes(origin) || 
                  (process.env.NODE_ENV !== 'production' && origin.includes('localhost'));
  }
  
  // Set secure CORS headers
  if (allowOrigin) {
    res.header('Access-Control-Allow-Origin', origin || '*');
    res.header('Access-Control-Allow-Credentials', 'true');
    console.log(`✅ CORS allowed for origin: ${origin}`);
  } else {
    console.warn(`❌ CORS blocked for origin: ${origin}`);
    // Don't set CORS headers for blocked origins
  }
  
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma');
  res.header('Access-Control-Max-Age', '86400');
  res.header('Access-Control-Expose-Headers', 'Content-Length, Content-Type, X-Request-ID');
  
  // Override res.json and res.send to ensure secure CORS headers
  const originalJson = res.json;
  res.json = function(body) {
    if (allowOrigin) {
      this.header('Access-Control-Allow-Origin', origin || '*');
      this.header('Access-Control-Allow-Credentials', 'true');
    }
    this.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
    this.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin');
    return originalJson.call(this, body);
  };
  
  const originalSend = res.send;
  res.send = function(body) {
    if (allowOrigin) {
      this.header('Access-Control-Allow-Origin', origin || '*');
      this.header('Access-Control-Allow-Credentials', 'true');
    }
    this.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
    this.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin');
    return originalSend.call(this, body);
  };
  
  // Handle preflight requests
  if (req.method === 'OPTIONS') {
    console.log(`✅ Handling OPTIONS preflight for ${req.path}`);
    if (allowOrigin) {
      res.status(200).end();
    } else {
      res.status(403).json({ error: 'CORS policy violation' });
    }
    return;
  }
  
  // Block request if origin not allowed for non-preflight requests
  if (!allowOrigin && origin && req.method !== 'OPTIONS') {
    console.warn(`🚫 Blocking request from unauthorized origin: ${origin}`);
    return res.status(403).json({ error: 'CORS policy violation' });
  }
  
  next();
});

// Enhanced logging and timeout protection middleware
app.use((req, res, next) => {
  const startTime = Date.now();
  const requestId = Math.random().toString(36).substr(2, 9);
  
  console.log(`🔍 [${requestId}] REQUEST START: ${req.method} ${req.path}`);
  console.log(`🔍 [${requestId}] Headers:`, JSON.stringify(req.headers, null, 2));
  console.log(`🔍 [${requestId}] Query:`, JSON.stringify(req.query, null, 2));
  if (req.body && Object.keys(req.body).length > 0) {
    console.log(`🔍 [${requestId}] Body:`, JSON.stringify(req.body, null, 2));
  }
  
  // Add request tracking to res.locals
  res.locals.requestId = requestId;
  res.locals.startTime = startTime;
  
  // Set a global timeout to ensure we always send a response
  const globalTimeout = setTimeout(() => {
    if (!res.headersSent) {
      const duration = Date.now() - startTime;
      console.error(`🕐 [${requestId}] GLOBAL TIMEOUT after ${duration}ms for ${req.method} ${req.path}`);
      console.error(`🕐 [${requestId}] Memory usage:`, process.memoryUsage());
      
      // Set secure CORS headers for timeout response
      const origin = req.headers.origin;
      const allowedOrigins = [
        'https://d1zb7knau41vl9.cloudfront.net',
        'http://localhost:3000',
        'http://localhost:5173'
      ];
      
      if (origin && allowedOrigins.includes(origin)) {
        res.header('Access-Control-Allow-Origin', origin);
        res.header('Access-Control-Allow-Credentials', 'true');
      }
      res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
      res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma');
      res.header('Access-Control-Expose-Headers', 'Content-Length, Content-Type, X-Request-ID');
      
      // Send a diagnostic response using standardized format
      res.serverError('Request timeout - Lambda function exceeded maximum processing time', {
        duration: duration,
        endpoint: `${req.method} ${req.path}`,
        requestId: requestId,
        memoryUsage: process.memoryUsage()
      });
    }
  }, 5000); // 5 second global timeout to prevent any timeouts
  
  // Enhanced response logging
  const originalSend = res.send;
  res.send = function(...args) {
    const duration = Date.now() - startTime;
    console.log(`✅ [${requestId}] RESPONSE SENT: ${res.statusCode} after ${duration}ms`);
    clearTimeout(globalTimeout);
    return originalSend.apply(this, args);
  };
  
  const originalJson = res.json;
  res.json = function(...args) {
    const duration = Date.now() - startTime;
    console.log(`✅ [${requestId}] JSON RESPONSE: ${res.statusCode} after ${duration}ms`);
    clearTimeout(globalTimeout);
    return originalJson.apply(this, args);
  };
  
  // Clear the timeout when response is sent
  res.on('finish', () => {
    const duration = Date.now() - startTime;
    console.log(`🏁 [${requestId}] REQUEST FINISHED after ${duration}ms`);
    clearTimeout(globalTimeout);
  });
  
  // Clear the timeout when response starts
  res.on('close', () => {
    const duration = Date.now() - startTime;
    console.log(`🔒 [${requestId}] CONNECTION CLOSED after ${duration}ms`);
    clearTimeout(globalTimeout);
  });
  
  next();
});

// Database readiness middleware - ensures DB is ready before processing requests
app.use(async (req, res, next) => {
  const requestId = res.locals.requestId || 'unknown';
  
  // Skip database check for health endpoints to avoid circular dependencies
  if (req.path.includes('/health') || req.path.includes('/debug')) {
    return next();
  }
  
  try {
    // Ensure database is initialized before processing database-dependent requests
    console.log(`🏥 [${requestId}] Checking database readiness...`);
    const dbCheckStart = Date.now();
    
    await initializeLambdaDatabase();
    
    console.log(`✅ [${requestId}] Database ready in ${Date.now() - dbCheckStart}ms`);
    next();
    
  } catch (error) {
    console.error(`❌ [${requestId}] Database not ready:`, error.message);
    
    // Return a proper error response if database is not ready
    res.status(503).json({
      success: false,
      error: 'Database temporarily unavailable',
      message: 'Service is initializing, please retry in a few seconds',
      retryAfter: 5,
      timestamp: new Date().toISOString()
    });
  }
});

// Removed emergency health endpoints - use proper health router instead
// The health router provides comprehensive database health checks

app.get('/api', (req, res) => {
  res.success({
    service: 'Financial Dashboard API',
    status: 'operational',
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    version: '10.1.0'
  });
});

// CORS diagnostic endpoint
app.get('/cors-test', (req, res) => {
  console.log(`🔬 CORS TEST from origin: ${req.headers.origin}`);
  console.log(`🔬 Headers:`, req.headers);
  
  // Set secure CORS headers for testing
  const origin = req.headers.origin;
  const allowedOrigins = [
    'https://d1zb7knau41vl9.cloudfront.net',
    'http://localhost:3000',
    'http://localhost:5173'
  ];
  
  if (origin && allowedOrigins.includes(origin)) {
    res.header('Access-Control-Allow-Origin', origin);
    res.header('Access-Control-Allow-Credentials', 'true');
  } else if (process.env.NODE_ENV !== 'production') {
    res.header('Access-Control-Allow-Origin', '*');
  }
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma');
  res.header('Access-Control-Max-Age', '86400');
  res.header('Access-Control-Expose-Headers', 'Content-Length, Content-Type, X-Request-ID');
  
  console.log(`🔬 CORS TEST headers set, response headers:`, res.getHeaders());
  
  res.success({
    message: 'CORS test endpoint',
    origin: req.headers.origin || 'no-origin',
    method: req.method,
    path: req.path,
    headers_received: req.headers,
    cors_headers_set: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma'
    }
  });
});

app.get('/api/cors-test', (req, res) => {
  console.log(`🔬 API CORS TEST from origin: ${req.headers.origin}`);
  console.log(`🔬 Headers:`, req.headers);
  
  // Set secure CORS headers for API testing
  const origin = req.headers.origin;
  const allowedOrigins = [
    'https://d1zb7knau41vl9.cloudfront.net',
    'http://localhost:3000',
    'http://localhost:5173'
  ];
  
  if (origin && allowedOrigins.includes(origin)) {
    res.header('Access-Control-Allow-Origin', origin);
    res.header('Access-Control-Allow-Credentials', 'true');
  } else if (process.env.NODE_ENV !== 'production') {
    res.header('Access-Control-Allow-Origin', '*');
  }
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma');
  res.header('Access-Control-Max-Age', '86400');
  res.header('Access-Control-Expose-Headers', 'Content-Length, Content-Type, X-Request-ID');
  
  console.log(`🔬 API CORS TEST headers set, response headers:`, res.getHeaders());
  
  res.success({
    message: 'API CORS test endpoint',
    origin: req.headers.origin || 'no-origin',
    method: req.method,
    path: req.path,
    headers_received: req.headers,
    cors_headers_set: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma'
    }
  });
});


// Request parsing with size limits
app.use(express.json({ limit: '2mb' }));
app.use(express.urlencoded({ extended: true, limit: '2mb' }));

// Response formatter middleware - provides standardized response methods
app.use(responseFormatterMiddleware);

// Enhanced request logging middleware - provides structured logging with correlation IDs
app.use(requestLoggingMiddleware);

// Security validation middleware - ENABLED for production security
app.use(requestSizeLimit('2mb'));
app.use(sqlInjectionPrevention);
app.use(xssPrevention);

// Rate limiting for authentication endpoints - ENABLED for production security
app.use('/auth', rateLimitConfigs.auth);
app.use('/api/auth', rateLimitConfigs.auth);

// Rate limiting for trading endpoints - higher frequency allowed
app.use('/trading', rateLimitConfigs.trading);
app.use('/api/trading', rateLimitConfigs.trading);
app.use('/portfolio', rateLimitConfigs.trading);
app.use('/api/portfolio', rateLimitConfigs.trading);

// Rate limiting for API endpoints - general protection
app.use('/api', rateLimitConfigs.api);

// Logging (simplified for Lambda)
const nodeEnv = process.env.NODE_ENV || 'production';
const deploymentEnv = process.env.ENVIRONMENT || 'dev';
const isProduction = deploymentEnv === 'production' || deploymentEnv === 'prod';

if (!isProduction) {
  app.use(morgan('combined'));
}

// Global database initialization promise (already declared above)
let dbAvailable = false;
let tableAvailability = {}; // Track which tables are available

// Check availability of specific tables
const checkTableAvailability = async (tableName) => {
  if (!dbAvailable) return false;
  
  try {
    const { query } = require('./utils/database');
    await Promise.race([
      query(`SELECT 1 FROM ${tableName} LIMIT 1`),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error(`Table ${tableName} check timeout`)), 3000)
      )
    ]);
    tableAvailability[tableName] = true;
    return true;
  } catch (error) {
    console.warn(`Table ${tableName} not available:`, error.message);
    tableAvailability[tableName] = false;
    return false;
  }
};

// Initialize database connection with aggressive timeout and fallback
const ensureDatabase = async () => {
  if (!dbInitPromise) {
    console.log('🔄 Quick database initialization...');
    dbInitPromise = Promise.race([
      initializeDatabase().catch(err => {
        console.error('⚠️ Database init failed, continuing without DB:', err.message);
        return null; // Don't throw, just return null
      }),
      new Promise((resolve) => 
        setTimeout(() => {
          console.warn('⚠️ Database init timeout, continuing without DB');
          resolve(null);
        }, 5000) // Much shorter timeout
      )
    ]).then(pool => {
      if (pool) {
        dbAvailable = true;
        console.log('✅ Database connected');
      } else {
        dbAvailable = false;
        console.log('⚠️ Database unavailable, API will run with limited functionality');
      }
      return pool;
    }).catch(err => {
      console.error('⚠️ Database error, continuing anyway:', err.message);
      dbInitPromise = null;
      dbAvailable = false;
      return null; // Don't throw
    });
  }
  return dbInitPromise;
};

// Middleware to check database requirement based on endpoint (non-blocking)
app.use(async (req, res, next) => {
  console.log(`📥 Processing: ${req.method} ${req.path}`);
  
  // Endpoints that don't require database - proceed immediately
  const nonDbEndpoints = ['/', '/health', '/cors-test', '/debug', '/api/health', '/api/cors-test'];
  const isHealthQuick = req.path === '/health' && req.query.quick === 'true';
  
  if (nonDbEndpoints.includes(req.path) || isHealthQuick || req.path.includes('cors-test')) {
    console.log('🚀 Non-DB endpoint, proceeding immediately');
    return next();
  }
  
  // For other endpoints, try database but don't block
  console.log('📊 DB endpoint, attempting quick connection...');
  try {
    const pool = await ensureDatabase();
    if (pool) {
      console.log('✅ Database ready for endpoint');
    } else {
      console.log('⚠️ Database unavailable, proceeding with limited functionality');
      req.dbError = new Error('Database unavailable');
      req.dbAvailable = false;
    }
  } catch (error) {
    console.error('⚠️ Database error, proceeding anyway:', error.message);
    req.dbError = error;
    req.dbAvailable = false;
  }
  
  next(); // Always proceed
});

// Secrets initialization middleware - runs before routes
app.use(async (req, res, next) => {
  if (!secretsInitialized) {
    console.log('🔐 Initializing secrets for first request...');
    try {
      await secretsLoader.loadAllSecrets();
      secretsInitialized = true;
      console.log('✅ Secrets initialized successfully');
    } catch (error) {
      console.error('❌ Failed to initialize secrets:', error.message);
      // Continue with fallback secrets
    }
  }
  next();
});

// Debug endpoint for secrets status
app.get('/debug/secrets-status', (req, res) => {
  const status = secretsLoader.getStatus();
  res.success({
    secretsStatus: status,
    environment: {
      hasApiKeySecret: !!process.env.API_KEY_ENCRYPTION_SECRET,
      hasJwtSecret: !!process.env.JWT_SECRET,
      hasDbSecret: !!process.env.DB_SECRET_ARN,
      region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
    }
  });
});

// Routes (note: API Gateway handles the /api prefix)
app.use('/health', healthRoutes);
app.use('/auth', authRoutes);
app.use('/stocks', stockRoutes);
app.use('/scores', scoresRoutes);
app.use('/metrics', metricsRoutes);
app.use('/market', marketRoutes);
app.use('/market-data', marketDataRoutes);
app.use('/analysts', analystRoutes);
app.use('/financials', financialRoutes);
app.use('/trading', tradingRoutes);
app.use('/technical', technicalRoutes);
app.use('/calendar', calendarRoutes);
app.use('/signals', signalsRoutes);
app.use('/data', dataRoutes);
app.use('/backtest', backtestRoutes);
app.use('/portfolio', portfolioRoutes);
app.use('/scoring', scoringRoutes);
app.use('/price', priceRoutes);
app.use('/settings', settingsRoutes);
app.use('/patterns', patternsRoutes);
app.use('/watchlist', watchlistRoutes);
app.use('/sectors', sectorsRoutes);
app.use('/ai-assistant', aiAssistantRoutes);
app.use('/trades', tradesRoutes);
app.use('/crypto', cryptoRoutes);
app.use('/screener', screenerRoutes);
app.use('/dashboard', dashboardRoutes);
app.use('/alerts', alertsRoutes);
app.use('/commodities', commoditiesRoutes);
app.use('/economic', economicRoutes);
app.use('/risk-management', riskManagementRoutes);
app.use('/performance-analytics', performanceAnalyticsRoutes);

// Also mount routes with /api prefix for frontend compatibility
app.use('/api/health', healthRoutes);
app.use('/api/auth', authRoutes);
app.use('/api/stocks', stockRoutes);
app.use('/api/scores', scoresRoutes);
app.use('/api/metrics', metricsRoutes);
app.use('/api/market', marketRoutes);
app.use('/api/market-data', marketDataRoutes);
app.use('/api/analysts', analystRoutes);
app.use('/api/financials', financialRoutes);
app.use('/api/trading', tradingRoutes);
app.use('/api/technical', technicalRoutes);
app.use('/api/calendar', calendarRoutes);
app.use('/api/signals', signalsRoutes);
app.use('/api/data', dataRoutes);
app.use('/api/backtest', backtestRoutes);
app.use('/api/portfolio', portfolioRoutes);
app.use('/api/scoring', scoringRoutes);
app.use('/api/price', priceRoutes);
app.use('/api/settings', settingsRoutes);
app.use('/api/patterns', patternsRoutes);
app.use('/api/watchlist', watchlistRoutes);
app.use('/api/sectors', sectorsRoutes);
app.use('/api/ai', aiAssistantRoutes);
app.use('/api/ai-assistant', aiAssistantRoutes);
app.use('/api/trades', tradesRoutes);
app.use('/api/crypto', cryptoRoutes);
app.use('/api/screener', screenerRoutes);
app.use('/api/dashboard', dashboardRoutes);
app.use('/api/alerts', alertsRoutes);
app.use('/api/commodities', commoditiesRoutes);
app.use('/api/economic', economicRoutes);
app.use('/api/websocket', websocketRoutes);
app.use('/api/pool', poolManagementRoutes);
app.use('/api/trading-strategies', tradingStrategiesRoutes);
app.use('/api/risk-management', riskManagementRoutes);
app.use('/api/performance-analytics', performanceAnalyticsRoutes);

// Debug route for troubleshooting API Gateway issues
app.get('/debug', (req, res) => {
  res.success({
    message: 'Debug endpoint - API Gateway routing test',
    request: {
      method: req.method,
      path: req.path,
      originalUrl: req.originalUrl,
      headers: req.headers,
      query: req.query,
      params: req.params
    },
    environment: {
      NODE_ENV: process.env.NODE_ENV,
      ENVIRONMENT: process.env.ENVIRONMENT,
      WEBAPP_AWS_REGION: process.env.WEBAPP_AWS_REGION,
      hasDbSecret: !!process.env.DB_SECRET_ARN,
      hasDbEndpoint: !!process.env.DB_ENDPOINT
    },
    lambda: {
      functionName: process.env.AWS_LAMBDA_FUNCTION_NAME,
      functionVersion: process.env.AWS_LAMBDA_FUNCTION_VERSION,
      awsRegion: process.env.AWS_REGION,
      requestId: req.context?.awsRequestId
    },
    database: {
      available: dbAvailable,
      initPromise: !!dbInitPromise
    }
  });
});

// Default route
app.get('/', (req, res) => {
  res.success({
    message: 'Financial Dashboard API',
    version: '10.1.0',
    status: 'operational',
    environment: deploymentEnv,
    endpoints: {
      health: {
        quick: '/health?quick=true',
        full: '/health',
        ready: '/health/ready',
        create_table: '/health/create-table'
      },
      debug: {
        main: '/debug',
        env: '/health/debug/env',
        db_test: '/health/debug/db-test',
        tables: '/health/debug/tables',
        test_query: '/health/debug/test-query',
        cors: '/health/debug/cors-test'
      },
      api: {
        stocks: '/stocks',
        screen: '/stocks/screen',
        metrics: '/metrics',
        market: '/market',
        analysts: '/analysts',
        trading: '/trading',
        technical: '/technical',
        calendar: '/calendar',
        signals: '/signals',
        trades: '/trades',
        risk_management: '/risk-management',
        performance_analytics: '/performance-analytics'
      }
    },
    notes: 'Use /health?quick=true for fast status check without database dependency'
  });
});

// 404 handler
app.use('*', (req, res) => {
  res.notFound('Endpoint', `The requested endpoint ${req.originalUrl} does not exist`);
});

// Error handling middleware (should be last) - Use proper error handler
app.use(errorHandler);

// Simplified Lambda handler to fix 502 errors
module.exports.handler = serverless(app, {
  // Lambda-specific options
  request: (request, event, context) => {
    // Add AWS event/context to request if needed
    request.event = event;
    request.context = context;
    console.log(`🔍 Lambda handler: ${event.httpMethod} ${event.path || event.rawPath}`);
  },
  response: (response, event, context) => {
    // Ensure CORS headers are always present on response
    if (!response.headers) {
      response.headers = {};
    }
    // Set secure CORS headers in Lambda response
    const allowedOrigins = [
      'https://d1zb7knau41vl9.cloudfront.net',
      'http://localhost:3000',
      'http://localhost:5173'
    ];
    
    const origin = event.headers?.origin || event.headers?.Origin;
    if (origin && allowedOrigins.includes(origin)) {
      response.headers['Access-Control-Allow-Origin'] = origin;
      response.headers['Access-Control-Allow-Credentials'] = 'true';
    } else if (process.env.NODE_ENV !== 'production') {
      response.headers['Access-Control-Allow-Origin'] = '*';
    }
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH';
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin';
    console.log(`🌐 CORS headers applied to ${response.statusCode} response`);
  }
});

// Export app for local testing
module.exports.app = app;

// For local testing
if (require.main === module) {
  const PORT = process.env.PORT || 3001;
  app.listen(PORT, () => {
    console.log(`Financial Dashboard API server running on port ${PORT} (local mode)`);
    console.log(`Health check: http://localhost:${PORT}/health`);
    console.log(`Stocks: http://localhost:${PORT}/stocks`);
    console.log(`Technical: http://localhost:${PORT}/technical/daily`);
  });
}