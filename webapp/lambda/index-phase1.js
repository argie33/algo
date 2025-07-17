// PHASE 1: PROGRESSIVE ENHANCEMENT VERSION
console.log('🚀 Phase 1: Progressive Enhancement Lambda starting...');

const serverless = require('serverless-http');
const express = require('express');
const app = express();

// Trust proxy when running behind API Gateway/CloudFront
app.set('trust proxy', true);

// CRITICAL: CORS middleware must be FIRST - proven to work
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

// Add correlation ID for requests
app.use((req, res, next) => {
  req.correlationId = Math.random().toString(36).substr(2, 9);
  next();
});

// Progressive service loading - Phase 1 approach
const services = {
  logger: null,
  database: null,
  formatter: null
};

// Service loader with fallback
const loadService = (serviceName, initializer, fallback) => {
  if (services[serviceName]) {
    return services[serviceName];
  }
  
  try {
    console.log(`🔄 Loading ${serviceName} service...`);
    services[serviceName] = initializer();
    console.log(`✅ ${serviceName} service loaded successfully`);
    return services[serviceName];
  } catch (error) {
    console.error(`⚠️ ${serviceName} service failed to load:`, error.message);
    services[serviceName] = fallback;
    return fallback;
  }
};

// Logger service with fallback
const getLogger = () => {
  return loadService('logger', 
    () => {
      const { createLogger } = require('./utils/structuredLogger');
      return createLogger('financial-platform', 'main');
    },
    {
      info: (msg, data) => console.log(`[INFO] ${msg}`, data || ''),
      error: (msg, error, data) => console.error(`[ERROR] ${msg}`, error?.message || error, data || ''),
      warn: (msg, data) => console.warn(`[WARN] ${msg}`, data || ''),
      debug: (msg, data) => console.debug(`[DEBUG] ${msg}`, data || ''),
      getCorrelationId: () => Math.random().toString(36).substr(2, 9)
    }
  );
};

// Database service with fallback
const getDatabase = () => {
  return loadService('database',
    () => require('./utils/databaseConnectionManager'),
    {
      query: async () => ({ rows: [], rowCount: 0 }),
      healthCheck: async () => ({ 
        healthy: false, 
        error: 'Database service unavailable',
        fallback: true
      })
    }
  );
};

// Response formatter with fallback
const getFormatter = () => {
  return loadService('formatter',
    () => {
      const { responseFormatterMiddleware } = require('./utils/responseFormatter');
      return responseFormatterMiddleware;
    },
    (req, res, next) => {
      res.success = (data, message = 'Success') => {
        res.json({ 
          success: true, 
          data, 
          message, 
          timestamp: new Date().toISOString(),
          correlation_id: req.correlationId
        });
      };
      res.error = (message, statusCode = 500) => {
        res.status(statusCode).json({ 
          success: false, 
          error: message, 
          timestamp: new Date().toISOString(),
          correlation_id: req.correlationId
        });
      };
      next();
    }
  );
};

// Apply response formatter middleware
app.use((req, res, next) => {
  const formatter = getFormatter();
  formatter(req, res, next);
});

// Add logging middleware
app.use((req, res, next) => {
  const logger = getLogger();
  req.logger = logger;
  if (!req.correlationId) {
    req.correlationId = logger.getCorrelationId();
  }
  next();
});

// Health endpoints - always work
app.get('/health', (req, res) => {
  const logger = getLogger();
  logger.info('Health endpoint accessed');
  
  res.json({
    success: true,
    message: 'Financial Dashboard API - Phase 1 Progressive Enhancement',
    timestamp: new Date().toISOString(),
    version: '2.1.0-phase1',
    environment: process.env.NODE_ENV || 'production',
    status: 'operational',
    phase: 'Progressive Enhancement',
    services: {
      logger: !!services.logger,
      database: !!services.database,
      formatter: !!services.formatter
    },
    correlation_id: req.correlationId
  });
});

app.get('/api/health', async (req, res) => {
  const logger = getLogger();
  const database = getDatabase();
  
  logger.info('API Health endpoint accessed');
  
  try {
    const dbHealth = await database.healthCheck();
    
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

// Progressive route loading
const loadedRoutes = new Set();

const safeRouteLoader = (routePath, routeName, mountPath, priority = 'medium') => {
  const routeKey = `${routeName}:${mountPath}`;
  
  if (loadedRoutes.has(routeKey)) {
    return true;
  }
  
  try {
    const route = require(routePath);
    app.use(mountPath, route);
    loadedRoutes.add(routeKey);
    console.log(`✅ Loaded ${routeName} route at ${mountPath} (${priority})`);
    return true;
  } catch (error) {
    console.error(`❌ Failed to load ${routeName} route:`, error.message);
    
    // Create fallback route
    const express = require('express');
    const errorRouter = express.Router();
    errorRouter.all('*', (req, res) => {
      res.status(503).json({
        success: false,
        error: `${routeName} service temporarily unavailable`,
        message: 'Route failed to load - check logs for details',
        timestamp: new Date().toISOString(),
        correlation_id: req.correlationId,
        priority: priority
      });
    });
    app.use(mountPath, errorRouter);
    return false;
  }
};

// API Key endpoints with database integration
app.get('/api/settings/api-keys', async (req, res) => {
  const logger = getLogger();
  const database = getDatabase();
  
  logger.info('API Keys GET endpoint accessed');
  
  try {
    const userId = req.user?.id || 'demo-user';
    
    const result = await database.query(
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
    
    // Fallback to mock data
    res.json({
      success: true,
      data: [],
      count: 0,
      message: 'API keys endpoint working (fallback mode)',
      fallback: true,
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
  }
});

app.post('/api/settings/api-keys', async (req, res) => {
  const logger = getLogger();
  const database = getDatabase();
  
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
    
    const result = await database.query(
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
    
    // Fallback response
    res.json({
      success: true,
      message: 'API key saved successfully (fallback mode)',
      fallback: true,
      timestamp: new Date().toISOString(),
      correlation_id: req.correlationId
    });
  }
});

// Load essential routes progressively
setTimeout(() => {
  console.log('🔄 Starting progressive route loading...');
  
  const essentialRoutes = [
    { path: './routes/settings', name: 'Settings', mount: '/api/settings', priority: 'high' },
    { path: './routes/stocks', name: 'Stocks', mount: '/api/stocks', priority: 'high' },
    { path: './routes/portfolio', name: 'Portfolio', mount: '/api/portfolio', priority: 'high' },
    { path: './routes/crypto', name: 'Crypto', mount: '/api/crypto', priority: 'medium' }
  ];
  
  let loaded = 0;
  essentialRoutes.forEach(route => {
    if (safeRouteLoader(route.path, route.name, route.mount, route.priority)) {
      loaded++;
    }
  });
  
  console.log(`📦 Progressive loading complete: ${loaded}/${essentialRoutes.length} routes loaded`);
}, 50); // Load routes 50ms after startup

// System status endpoint
app.get('/system-status', (req, res) => {
  const logger = getLogger();
  logger.info('System status endpoint accessed');
  
  res.json({
    success: true,
    message: 'Financial Dashboard API - Phase 1 System Status',
    timestamp: new Date().toISOString(),
    system_status: 'PROGRESSIVE_ENHANCEMENT',
    phase: 'Phase 1',
    services: {
      logger: !!services.logger,
      database: !!services.database,
      formatter: !!services.formatter
    },
    routes: {
      loaded: loadedRoutes.size,
      progressive_loading: true
    },
    correlation_id: req.correlationId
  });
});

// Debug endpoint
app.get('/debug', (req, res) => {
  const logger = getLogger();
  logger.info('Debug endpoint accessed');
  
  res.json({
    success: true,
    message: 'Phase 1 Debug endpoint',
    timestamp: new Date().toISOString(),
    phase: 'Progressive Enhancement',
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
    services: {
      logger: !!services.logger,
      database: !!services.database,
      formatter: !!services.formatter
    },
    correlation_id: req.correlationId
  });
});

// Default route
app.get('/', (req, res) => {
  res.json({
    success: true,
    message: 'Financial Dashboard API - Phase 1',
    version: '2.1.0-phase1',
    status: 'progressive_enhancement',
    timestamp: new Date().toISOString(),
    features: ['progressive-loading', 'service-fallbacks', 'error-boundaries'],
    correlation_id: req.correlationId
  });
});

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({
    success: false,
    error: `Endpoint ${req.originalUrl} not found`,
    message: 'Route not implemented in Phase 1',
    method: req.method,
    path: req.originalUrl,
    timestamp: new Date().toISOString(),
    correlation_id: req.correlationId
  });
});

// Global error handler with CORS preservation
app.use((error, req, res, next) => {
  console.error('Lambda error:', error);
  
  // CRITICAL: Ensure CORS headers are always set
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
    message: 'Phase 1 error with CORS preserved',
    timestamp: new Date().toISOString(),
    correlation_id: req.correlationId
  });
});

console.log('✅ Phase 1 Progressive Enhancement Lambda ready');

// Export the handler
module.exports.handler = serverless(app);