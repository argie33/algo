// Load environment variables first
require('dotenv').config();

// Financial Dashboard API - Lambda Function  
// Updated: 2025-07-13 - ROUTE LOADING FIXED - v9 - DEPLOY NOW

const serverless = require('serverless-http');
const express = require('express');

const app = express();

// Trust proxy when running behind API Gateway/CloudFront
app.set('trust proxy', true);

// EMERGENCY CORS FIX - Set headers immediately on ALL requests (FIRST MIDDLEWARE)
app.use((req, res, next) => {
  console.log(`🆘 CORS: ${req.method} ${req.path} from origin: ${req.headers.origin}`);
  
  // Set CORS headers immediately and aggressively
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin, Cache-Control, Pragma');
  res.header('Access-Control-Allow-Credentials', 'true');
  res.header('Access-Control-Max-Age', '86400');
  res.header('Access-Control-Expose-Headers', 'Content-Length, Content-Type, X-Request-ID');
  
  // Handle preflight OPTIONS requests immediately
  if (req.method === 'OPTIONS') {
    console.log(`🆘 OPTIONS preflight handled for ${req.path}`);
    res.status(200).end();
    return;
  }
  
  next();
});

// Request parsing with size limits
app.use(express.json({ limit: '2mb' }));
app.use(express.urlencoded({ extended: true, limit: '2mb' }));

// Basic logging
app.use((req, res, next) => {
  console.log(`📥 ${req.method} ${req.path}`);
  next();
});

// Global database initialization promise (non-blocking)
let dbInitPromise = null;
let dbAvailable = false;

// Initialize database connection with fallback (non-blocking)
const ensureDatabase = async () => {
  if (!dbInitPromise) {
    console.log('🔄 Quick database initialization...');
    dbInitPromise = Promise.race([
      (async () => {
        try {
          const { initializeDatabase } = require('./utils/database');
          const pool = await initializeDatabase();
          console.log('✅ Database connected');
          return pool;
        } catch (err) {
          console.error('⚠️ Database init failed:', err.message);
          return null;
        }
      })(),
      new Promise((resolve) => 
        setTimeout(() => {
          console.warn('⚠️ Database init timeout, continuing without DB');
          resolve(null);
        }, 3000) // Very short timeout
      )
    ]).then(pool => {
      dbAvailable = !!pool;
      return pool;
    }).catch(err => {
      console.error('⚠️ Database error:', err.message);
      dbAvailable = false;
      return null;
    });
  }
  return dbInitPromise;
};

// Emergency health check endpoint - responds immediately
app.get('/health', (req, res) => {
  console.log(`🏥 HEALTH CHECK from origin: ${req.headers.origin}`);
  
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    version: '9.0.0',
    cors_test: 'Headers should be present',
    origin: req.headers.origin || 'no-origin',
    database: dbAvailable ? 'connected' : 'not connected'
  });
});

app.get('/api/health', (req, res) => {
  console.log(`🏥 API HEALTH CHECK from origin: ${req.headers.origin}`);
  
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    version: '9.0.0',
    cors_test: 'Headers should be present',
    origin: req.headers.origin || 'no-origin',
    database: dbAvailable ? 'connected' : 'not connected'
  });
});

// Safe route loading - load all routes at startup with error handling
console.log('🔄 Loading routes...');

// Helper function to safely load routes
const safeLoadRoute = (routePath, modulePath, routeName) => {
  try {
    const routeModule = require(modulePath);
    app.use(routePath, routeModule);
    console.log(`✅ Loaded ${routeName} route: ${routePath}`);
    return true;
  } catch (error) {
    console.error(`⚠️ Failed to load ${routeName} route:`, error.message);
    // Create a placeholder route that returns a helpful error
    app.use(routePath, (req, res) => {
      res.status(503).json({
        error: 'Service temporarily unavailable',
        message: `${routeName} service is being loaded`,
        route: routePath,
        timestamp: new Date().toISOString()
      });
    });
    return false;
  }
};

// Load all routes with error handling
safeLoadRoute('/settings', './routes/settings', 'Settings');
safeLoadRoute('/api/settings', './routes/settings', 'API Settings');
safeLoadRoute('/portfolio', './routes/portfolio', 'Portfolio');
safeLoadRoute('/api/portfolio', './routes/portfolio', 'API Portfolio');
safeLoadRoute('/stocks', './routes/stocks', 'Stocks');
safeLoadRoute('/api/stocks', './routes/stocks', 'API Stocks');
safeLoadRoute('/auth', './routes/auth', 'Auth');
safeLoadRoute('/api/auth', './routes/auth', 'API Auth');
safeLoadRoute('/market', './routes/market', 'Market');
safeLoadRoute('/api/market', './routes/market', 'API Market');
safeLoadRoute('/metrics', './routes/metrics', 'Metrics');
safeLoadRoute('/api/metrics', './routes/metrics', 'API Metrics');

// Try to load other common routes
safeLoadRoute('/health-detailed', './routes/health', 'Health Detailed');
safeLoadRoute('/api/health-detailed', './routes/health', 'API Health Detailed');

console.log('✅ Route loading completed');

// Database initialization middleware (non-blocking)
app.use(async (req, res, next) => {
  // Try to ensure database for data endpoints (non-blocking)
  if (!req.path.includes('/health') && !req.path.includes('/cors-test') && !req.path.includes('/debug')) {
    ensureDatabase().catch(err => {
      console.log('⚠️ Database not available for', req.path);
    });
  }
  next();
});

// Default route
app.get('/', (req, res) => {
  res.json({
    message: 'Financial Dashboard API',
    version: '9.0.0',
    status: 'operational',
    timestamp: new Date().toISOString(),
    database: dbAvailable ? 'connected' : 'not connected',
    environment: process.env.ENVIRONMENT || 'dev',
    cors_test: 'Headers should be present'
  });
});

// Debug route for troubleshooting
app.get('/debug', (req, res) => {
  res.json({
    message: 'Debug endpoint working',
    timestamp: new Date().toISOString(),
    request: {
      method: req.method,
      path: req.path,
      headers: req.headers,
      query: req.query
    },
    environment: {
      NODE_ENV: process.env.NODE_ENV,
      ENVIRONMENT: process.env.ENVIRONMENT,
      hasDbSecret: !!process.env.DB_SECRET_ARN
    },
    database: {
      available: dbAvailable,
      initPromise: !!dbInitPromise
    }
  });
});

// CORS diagnostic endpoint
app.get('/cors-test', (req, res) => {
  console.log(`🔬 CORS TEST from origin: ${req.headers.origin}`);
  
  res.json({
    message: 'CORS test endpoint working',
    origin: req.headers.origin || 'no-origin',
    method: req.method,
    path: req.path,
    cors_headers_set: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH'
    },
    timestamp: new Date().toISOString()
  });
});

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({
    error: 'Endpoint not found',
    message: `The requested endpoint ${req.originalUrl} does not exist`,
    available_endpoints: ['/health', '/api/health', '/debug', '/cors-test', '/'],
    timestamp: new Date().toISOString()
  });
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('Error occurred:', err.message);
  
  // CRITICAL: Set CORS headers immediately
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin');
  
  res.status(500).json({ 
    success: false,
    error: 'Internal Server Error',
    message: err.message,
    timestamp: new Date().toISOString()
  });
});

// Simplified Lambda handler
module.exports.handler = serverless(app, {
  request: (request, event, context) => {
    request.event = event;
    request.context = context;
    console.log(`🔍 Lambda: ${event.httpMethod} ${event.path || event.rawPath}`);
  },
  response: (response, event, context) => {
    // Ensure CORS headers are always present
    if (!response.headers) response.headers = {};
    response.headers['Access-Control-Allow-Origin'] = '*';
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH';
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, X-Session-ID, Accept, Origin';
    response.headers['Access-Control-Allow-Credentials'] = 'true';
    console.log(`🌐 CORS applied to ${response.statusCode} response`);
  }
});

// Export app for local testing
module.exports.app = app;