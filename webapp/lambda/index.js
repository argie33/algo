// Load environment variables first
require('dotenv').config();

// Financial Dashboard API - Lambda Function
// Updated: 2025-06-25 - Fixed CORS configuration for API Gateway

const serverless = require('serverless-http');
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const { initializeDatabase } = require('./utils/database');
const errorHandler = require('./middleware/errorHandler');

// Import routes
const stockRoutes = require('./routes/stocks');
const screenerRoutes = require('./routes/screener');
const websocketRoutes = require('./routes/websocket');
const scoresRoutes = require('./routes/scores');
const metricsRoutes = require('./routes/metrics');
const healthRoutes = require('./routes/health');
const marketRoutes = require('./routes/market');
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
const liveDataRoutes = require('./routes/liveData');

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
  
  next();
});

// Note: Rate limiting removed - API Gateway handles this

// CORS configuration (allow API Gateway origins)
app.use(cors({
  origin: (origin, callback) => {
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
      callback(null, true);
    } else {
      console.warn('CORS blocked origin:', origin);
      callback(new Error('Not allowed by CORS'));
    }
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With']
}));

// Request parsing
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Note: API Gateway strips the /api prefix before sending to Lambda

// Logging (simplified for Lambda)
const nodeEnv = process.env.NODE_ENV || 'production';
const isProduction = nodeEnv === 'production' || nodeEnv === 'prod';

if (!isProduction) {
  app.use(morgan('combined'));
}

// Global database initialization promise
let dbInitPromise = null;
let dbAvailable = false;

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
        setTimeout(() => reject(new Error('Database initialization timeout after 15 seconds')), 15000)
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
    
    // For other endpoints, return service unavailable instead of forbidden
    res.status(503).json({ 
      error: 'Service temporarily unavailable - database connection failed',
      message: 'The database is currently unavailable. Please try again later.',
      timestamp: new Date().toISOString(),
      details: !isProduction ? error.message : undefined,
      debug: !isProduction ? {
        config: error.config,
        env: error.env
      } : undefined
    });
  }
});

// Routes (note: API Gateway handles the /api prefix)
app.use('/health', healthRoutes);
app.use('/auth', authRoutes);
app.use('/stocks', stockRoutes);
app.use('/screener', screenerRoutes);
app.use('/websocket', websocketRoutes);
app.use('/scores', scoresRoutes);
app.use('/metrics', metricsRoutes);
app.use('/market', marketRoutes);
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
app.use('/live-data', liveDataRoutes);

// Also mount routes with /api prefix for frontend compatibility
app.use('/api/health', healthRoutes);
app.use('/api/auth', authRoutes);
app.use('/api/stocks', stockRoutes);
app.use('/api/screener', screenerRoutes);
app.use('/api/websocket', websocketRoutes);
app.use('/api/scores', scoresRoutes);
app.use('/api/metrics', metricsRoutes);
app.use('/api/market', marketRoutes);
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
app.use('/api/live-data', liveDataRoutes);

// Default route
app.get('/', (req, res) => {
  res.json({
    message: 'Financial Dashboard API',
    version: '1.0.0',
    status: 'operational',
    timestamp: new Date().toISOString(),
    environment: nodeEnv,
    endpoints: {
      health: {
        quick: '/health?quick=true',
        full: '/health'
      },      api: {
        stocks: '/stocks',
        screen: '/stocks/screen',
        metrics: '/metrics',
        market: '/market',
        analysts: '/analysts',
        trading: '/trading',
        technical: '/technical',
        calendar: '/calendar',
        signals: '/signals'
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

// Export Lambda handler
module.exports.handler = serverless(app, {
  // Lambda-specific options
  request: (request, event, context) => {
    // Add AWS event/context to request if needed
    request.event = event;
    request.context = context;
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
