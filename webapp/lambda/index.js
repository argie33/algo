// Load environment variables first
require('dotenv').config();

// Financial Dashboard API - Lambda Function
// Updated: 2025-07-12 - Fixed CORS X-Session-ID header deployment - Deploy v4

const serverless = require('serverless-http');
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const { initializeDatabase } = require('./utils/database');
const errorHandler = require('./middleware/errorHandler');
const { 
  rateLimitConfigs, 
  sqlInjectionPrevention, 
  xssPrevention, 
  requestSizeLimit 
} = require('./middleware/validation');

// Import routes
const stockRoutes = require('./routes/stocks');
const scoresRoutes = require('./routes/scores');
const metricsRoutes = require('./routes/metrics');
const healthRoutes = require('./routes/health');
const marketRoutes = require('./routes/market');
const marketDataRoutes = require('./routes/market-data');
const analystRoutes = require('./routes/analysts');
const financialRoutes = require('./routes/financials');
const tradingRoutes = require('./routes/trading');
const technicalRoutes = require('./routes/technical');
const calendarRoutes = require('./routes/calendar');
const signalsRoutes = require('./routes/signals');
const dataRoutes = require('./routes/data');
const backtestRoutes = require('./routes/backtest');
const authRoutes = require('./routes/auth');
const portfolioRoutes = require('./routes/portfolio');
const scoringRoutes = require('./routes/scoring');
const priceRoutes = require('./routes/price');
const settingsRoutes = require('./routes/settings');
const patternsRoutes = require('./routes/patterns');
const sectorsRoutes = require('./routes/sectors');
const watchlistRoutes = require('./routes/watchlist');
const aiAssistantRoutes = require('./routes/ai-assistant');
const tradesRoutes = require('./routes/trades');
const cryptoRoutes = require('./routes/crypto');
const screenerRoutes = require('./routes/screener');
const dashboardRoutes = require('./routes/dashboard');
const alertsRoutes = require('./routes/alerts');
const commoditiesRoutes = require('./routes/commodities');
const economicRoutes = require('./routes/economic');

const app = express();

// Trust proxy when running behind API Gateway/CloudFront
app.set('trust proxy', true);

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

// Additional security headers for financial applications
app.use((req, res, next) => {
  // Prevent MIME type sniffing
  res.setHeader('X-Content-Type-Options', 'nosniff');
  
  // Prevent clickjacking
  res.setHeader('X-Frame-Options', 'DENY');
  
  // Enable XSS protection
  res.setHeader('X-XSS-Protection', '1; mode=block');
  
  // Strict transport security
  res.setHeader('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload');
  
  // Referrer policy
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  
  // Feature policy for financial applications
  res.setHeader('Permissions-Policy', 
    'geolocation=(), microphone=(), camera=(), payment=(), usb=(), ' +
    'screen-wake-lock=(), web-share=(), gyroscope=(), magnetometer=()');
  
  // Cache control for sensitive financial data
  if (req.path.includes('/portfolio') || req.path.includes('/trading')) {
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
  }
  
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

// Note: Rate limiting removed - API Gateway handles this

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

// Aggressive CORS middleware - set headers on EVERY response
app.use((req, res, next) => {
  const origin = req.headers.origin;
  
  console.log(`🌐 CORS middleware - Method: ${req.method}, Origin: ${origin}, Path: ${req.path}`);
  
  // Set CORS headers immediately and aggressively
  res.header('Access-Control-Allow-Origin', '*'); // Allow all origins
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma');
  res.header('Access-Control-Allow-Credentials', 'true');
  res.header('Access-Control-Max-Age', '86400');
  res.header('Access-Control-Expose-Headers', 'Content-Length, Content-Type, X-Request-ID');
  
  // Override res.json and res.send to ensure CORS headers are always set
  const originalJson = res.json;
  res.json = function(body) {
    this.header('Access-Control-Allow-Origin', '*');
    this.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
    this.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin');
    return originalJson.call(this, body);
  };
  
  const originalSend = res.send;
  res.send = function(body) {
    this.header('Access-Control-Allow-Origin', '*');
    this.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
    this.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin');
    return originalSend.call(this, body);
  };
  
  // Handle preflight requests immediately
  if (req.method === 'OPTIONS') {
    console.log(`✅ Handling OPTIONS preflight for ${req.path}`);
    res.status(200).end();
    return;
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
      
      // Ensure CORS headers are set aggressively
      res.header('Access-Control-Allow-Origin', '*');
      res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
      res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma');
      res.header('Access-Control-Allow-Credentials', 'true');
      res.header('Access-Control-Expose-Headers', 'Content-Length, Content-Type, X-Request-ID');
      
      // Send a diagnostic response
      res.status(500).json({
        success: false,
        error: 'Lambda function timeout',
        message: 'The request exceeded the maximum processing time',
        details: {
          duration: duration,
          endpoint: `${req.method} ${req.path}`,
          requestId: requestId,
          memoryUsage: process.memoryUsage()
        },
        timestamp: new Date().toISOString()
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

// Emergency health check endpoint - responds immediately without any processing
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    version: '1.0.0'
  });
});

app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    version: '1.0.0'
  });
});

app.get('/api', (req, res) => {
  res.json({
    status: 'ok',
    service: 'Financial Dashboard API',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    version: '1.0.0'
  });
});


// Request parsing with size limits
app.use(express.json({ limit: '2mb' }));
app.use(express.urlencoded({ extended: true, limit: '2mb' }));

// Security validation middleware
app.use(requestSizeLimit('2mb'));
app.use(sqlInjectionPrevention);
app.use(xssPrevention);

// Rate limiting for authentication endpoints
app.use('/auth', rateLimitConfigs.auth);

// Note: API Gateway strips the /api prefix before sending to Lambda

// Logging (simplified for Lambda)
const nodeEnv = process.env.NODE_ENV || 'production';
const deploymentEnv = process.env.ENVIRONMENT || 'dev';
const isProduction = deploymentEnv === 'production' || deploymentEnv === 'prod';

if (!isProduction) {
  app.use(morgan('combined'));
}

// Global database initialization promise
let dbInitPromise = null;
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

// Initialize database connection with shorter timeout
const ensureDatabase = async () => {
  if (!dbInitPromise) {
    console.log('Initializing database connection...');
    dbInitPromise = Promise.race([
      initializeDatabase().catch(err => {
        console.error('Database initialization error details:', {
          message: err.message,
          stack: err.stack,
          config: err.config,
          env: err.env
        });
        throw err;
      }),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Database initialization timeout after 30 seconds')), 30000)
      )
    ]).then(pool => {
      dbAvailable = true;
      console.log('Database connection established successfully');
      return pool;
    }).catch(err => {
      console.error('Failed to initialize database:', err);
      dbInitPromise = null; // Reset to allow retry
      dbAvailable = false;
      throw err;
    });
  }
  return dbInitPromise;
};

// Middleware to check database requirement based on endpoint
app.use(async (req, res, next) => {
  console.log(`Processing request: ${req.method} ${req.path}`);
  
  // Endpoints that don't require database
  const nonDbEndpoints = ['/', '/health'];
  const isHealthQuick = req.path === '/health' && req.query.quick === 'true';
  
  if (nonDbEndpoints.includes(req.path) || isHealthQuick) {
    console.log('Endpoint does not require database connection');
    return next();
  }
  
  // For endpoints that need database, try to ensure connection
  try {
    await ensureDatabase();
    console.log('Database connection verified for database-dependent endpoint');
    next();
  } catch (error) {
    console.error('Database initialization failed for database-dependent endpoint:', {
      message: error.message,
      stack: error.stack,
      config: error.config,
      env: error.env
    });
    
    // For health endpoint (non-quick), still allow it to proceed with DB error info
    if (req.path === '/health') {
      req.dbError = error;
      return next();
    }
    
    // For data endpoints, proceed but mark database as unavailable
    req.dbError = error;
    req.dbAvailable = false;
    console.log('Proceeding with endpoint despite database issues - will return partial data');
    next();
  }
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

// Debug route for troubleshooting API Gateway issues
app.get('/debug', (req, res) => {
  res.json({
    message: 'Debug endpoint - API Gateway routing test',
    timestamp: new Date().toISOString(),
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
    },
    success: true
  });
});

// Default route
app.get('/', (req, res) => {
  res.json({
    message: 'Financial Dashboard API',
    version: '1.0.0',
    status: 'operational',
    timestamp: new Date().toISOString(),
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
        trades: '/trades'
      }
    },
    notes: 'Use /health?quick=true for fast status check without database dependency'
  });
});

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({
    error: 'Endpoint not found',
    message: `The requested endpoint ${req.originalUrl} does not exist`
  });
});

// Error handling middleware (should be last)
app.use(errorHandler);

// Custom Lambda handler with CORS timeout protection
const serverlessHandler = serverless(app, {
  // Lambda-specific options
  request: (request, event, context) => {
    // Add AWS event/context to request if needed
    request.event = event;
    request.context = context;
  }
});

// Wrap the serverless handler to ensure CORS headers on ALL responses
module.exports.handler = async (event, context) => {
  console.log(`🔍 Lambda handler entry: ${event.httpMethod} ${event.path || event.rawPath}`);
  console.log(`🔍 Lambda context:`, {
    requestId: context.awsRequestId,
    remainingTime: context.getRemainingTimeInMillis(),
    functionName: context.functionName
  });
  
  // Set up a timeout that triggers 2 seconds before Lambda timeout
  const timeoutBuffer = 2000; // 2 seconds buffer
  const remainingTime = context.getRemainingTimeInMillis();
  const timeoutMs = Math.max(remainingTime - timeoutBuffer, 1000); // At least 1 second
  
  console.log(`⏰ Setting Lambda timeout protection: ${timeoutMs}ms (${remainingTime}ms remaining)`);
  
  const timeoutPromise = new Promise((resolve) => {
    setTimeout(() => {
      console.error(`🕐 Lambda timeout protection triggered after ${timeoutMs}ms`);
      resolve({
        statusCode: 500,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma',
          'Access-Control-Allow-Credentials': 'true',
          'Access-Control-Max-Age': '86400',
          'Access-Control-Expose-Headers': 'Content-Length, Content-Type, X-Request-ID',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          success: false,
          error: 'Lambda function timeout protection',
          message: 'The request is taking too long to process',
          details: {
            timeout: timeoutMs,
            remainingTime: remainingTime,
            requestId: context.awsRequestId,
            functionName: context.functionName
          },
          timestamp: new Date().toISOString()
        })
      });
    }, timeoutMs);
  });
  
  try {
    // Race between the actual handler and timeout
    const result = await Promise.race([
      serverlessHandler(event, context),
      timeoutPromise
    ]);
    
    console.log(`✅ Lambda handler completed with status: ${result.statusCode}`);
    
    // Ensure CORS headers are always present
    if (!result.headers) {
      result.headers = {};
    }
    
    // Force CORS headers on the response
    result.headers['Access-Control-Allow-Origin'] = '*';
    result.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH';
    result.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma';
    result.headers['Access-Control-Allow-Credentials'] = 'true';
    result.headers['Access-Control-Expose-Headers'] = 'Content-Length, Content-Type, X-Request-ID';
    
    console.log(`🌐 CORS headers applied to response: ${Object.keys(result.headers).filter(h => h.toLowerCase().includes('access-control')).join(', ')}`);
    
    return result;
    
  } catch (error) {
    console.error(`❌ Lambda handler error:`, {
      message: error.message,
      stack: error.stack,
      requestId: context.awsRequestId
    });
    
    // Return error response with CORS headers
    return {
      statusCode: 500,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma',
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Max-Age': '86400',
        'Access-Control-Expose-Headers': 'Content-Length, Content-Type, X-Request-ID',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        success: false,
        error: 'Lambda function error',
        message: error.message,
        details: {
          requestId: context.awsRequestId,
          functionName: context.functionName
        },
        timestamp: new Date().toISOString()
      })
    };
  }
};

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
