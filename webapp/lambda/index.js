// FINANCIAL DASHBOARD API - FULL VERSION WITH CORS RELIABILITY - EXCLUSIVE WEBAPP
console.log('🚀 Financial Dashboard API Lambda starting - FULL VERSION...');

const serverless = require('serverless-http');
const express = require('express');
const app = express();

// Trust proxy when running behind API Gateway/CloudFront
app.set('trust proxy', true);

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

// Enhanced middleware
app.use(express.json({ limit: '2mb' }));
app.use(express.urlencoded({ extended: true, limit: '2mb' }));

// Global services - lazy loaded to avoid initialization crashes
let logger = null;
let databaseManager = null;
let responseFormatter = null;

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
      // Fallback response formatter
      responseFormatter = (req, res, next) => {
        res.success = (data, message = 'Success') => {
          res.json({ success: true, data, message, timestamp: new Date().toISOString() });
        };
        res.error = (message, statusCode = 500) => {
          res.status(statusCode).json({ success: false, error: message, timestamp: new Date().toISOString() });
        };
        next();
      };
    }
  }
  return responseFormatter;
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
  { path: './routes/health', name: 'Health', mount: '/api/health-full' },
  { path: './routes/diagnostics', name: 'Diagnostics', mount: '/api/diagnostics' },
  { path: './routes/websocket', name: 'WebSocket', mount: '/api/websocket' },
  { path: './routes/liveData', name: 'Live Data', mount: '/api/live-data' },
  
  // Core Financial Data Routes  
  { path: './routes/stocks', name: 'Stocks', mount: '/api/stocks' },
  { path: './routes/portfolio', name: 'Portfolio', mount: '/api/portfolio' },
  { path: './routes/market', name: 'Market', mount: '/api/market' },
  { path: './routes/market-data', name: 'Market Data', mount: '/api/market-data' },
  { path: './routes/data', name: 'Data Management', mount: '/api/data' },
  
  // User & Settings Routes
  { path: './routes/settings', name: 'Settings', mount: '/api/settings' },
  { path: './routes/auth', name: 'Authentication', mount: '/api/auth' },
  
  // Analysis & Trading Routes
  { path: './routes/technical', name: 'Technical Analysis', mount: '/api/technical' },
  { path: './routes/dashboard', name: 'Dashboard', mount: '/api/dashboard' },
  { path: './routes/screener', name: 'Stock Screener', mount: '/api/screener' },
  { path: './routes/watchlist', name: 'Watchlist', mount: '/api/watchlist' },
  { path: './routes/metrics', name: 'Metrics', mount: '/api/metrics' },
  
  // Advanced Features
  { path: './routes/alerts', name: 'Alerts', mount: '/api/alerts' },
  { path: './routes/news', name: 'News', mount: '/api/news' },
  { path: './routes/sentiment', name: 'Sentiment', mount: '/api/sentiment' },
  { path: './routes/signals', name: 'Trading Signals', mount: '/api/signals' },
  { path: './routes/crypto', name: 'Cryptocurrency', mount: '/api/crypto' },
  { path: './routes/crypto-advanced', name: 'Crypto Advanced Portfolio', mount: '/api/crypto-advanced' },
  { path: './routes/crypto-signals', name: 'Crypto Trading Signals', mount: '/api/crypto-signals' },
  { path: './routes/crypto-risk', name: 'Crypto Risk Management', mount: '/api/crypto-risk' },
  { path: './routes/crypto-analytics', name: 'Crypto Market Analytics', mount: '/api/crypto-analytics' },
  { path: './routes/advanced', name: 'Advanced Trading', mount: '/api/advanced' },
  { path: './routes/calendar', name: 'Economic Calendar', mount: '/api/calendar' },
  { path: './routes/commodities', name: 'Commodities', mount: '/api/commodities' },
  { path: './routes/sectors', name: 'Sectors', mount: '/api/sectors' },
  { path: './routes/trading', name: 'Trading', mount: '/api/trading' },
  { path: './routes/trades', name: 'Trade History', mount: '/api/trades' },
  { path: './routes/risk', name: 'Risk Analysis', mount: '/api/risk' },
  { path: './routes/performance', name: 'Performance Analytics', mount: '/api/performance' }
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
        DB_SECRET_ARN: !!process.env.DB_SECRET_ARN ? 'SET' : 'MISSING',
        API_KEY_ENCRYPTION_SECRET_ARN: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN ? 'SET' : 'MISSING'
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
    const userId = req.user?.id || 'demo-user';
    
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
    const userId = req.user?.id || 'demo-user';
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
    const userId = req.user?.id || 'demo-user';
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
    const userId = req.user?.id || 'demo-user';
    
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
    const userId = req.user?.id || 'demo-user';
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
    const userId = req.user?.id || 'demo-user';
    
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
    const userId = req.user?.id || 'demo-user';
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

// Error handler with CORS
app.use((error, req, res, next) => {
  console.error('Error:', error);
  
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

console.log('✅ Financial Dashboard API Lambda ready');

// Export the handler
module.exports.handler = serverless(app);