// ENHANCED FINANCIAL DASHBOARD API - PRODUCTION READY
// Optimized route management with intelligent loading and fallback strategies - v3.0
console.log('🚀 ENHANCED FINANCIAL DASHBOARD API STARTING - Intelligent route optimization enabled...');

const serverless = require('serverless-http');
const express = require('express');

// Import comprehensive logging
const { createLogger, requestLoggingMiddleware } = require('./utils/structuredLogger');

// Import enhanced route management
const IntelligentRouteLoader = require('./routes/enhanced/intelligentRouteLoader');

// Import database connection manager
const databaseConnectionManager = require('./utils/databaseConnectionManager');
const { responseFormatterMiddleware } = require('./utils/responseFormatter');

const app = express();
const logger = createLogger('enhanced-financial-platform', 'main');
const routeLoader = new IntelligentRouteLoader();

logger.info('Enhanced Lambda initialization started', {
  environment: process.env.NODE_ENV,
  region: process.env.AWS_REGION,
  branch: 'initialbuild',
  enhancement_version: '3.0'
});

console.log('✅ Enhanced Express app created with intelligent routing');

// CRITICAL: CORS must work immediately
app.use((req, res, next) => {
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
    console.log('🔧 CORS preflight for:', req.path);
    return res.status(200).end();
  }
  
  console.log(`📡 ${req.method} ${req.path}`);
  next();
});

console.log('✅ CORS configured');

// Add structured logging middleware
app.use(requestLoggingMiddleware);

// Basic middleware
app.use(express.json({ limit: '1mb' }));
app.use(express.urlencoded({ extended: true, limit: '1mb' }));

// Add response formatter middleware for routes
app.use(responseFormatterMiddleware);

logger.info('Enhanced middleware configuration completed', {
  middleware: ['request_logging', 'cors', 'json_parser', 'url_encoded', 'response_formatter'],
  enhancement_features: ['intelligent_routing', 'fallback_support', 'performance_monitoring']
});

console.log('✅ Enhanced middleware configured');

// Enhanced Route Loading with Intelligent Management
console.log('🎯 Starting enhanced intelligent route loading...');
const routeLoadingStart = Date.now();

const loadingResults = routeLoader.loadAllRoutesIntelligently(app);

const routeLoadingDuration = Date.now() - routeLoadingStart;

logger.info('Enhanced route loading completed', {
  route_loading: {
    total_routes: loadingResults.successful.length + loadingResults.failed.length + loadingResults.fallbacks.length,
    successful_routes: loadingResults.successful.length,
    fallback_routes: loadingResults.fallbacks.length,
    failed_routes: loadingResults.failed.length,
    duration_ms: routeLoadingDuration,
    success_rate: Math.round((loadingResults.successful.length / (loadingResults.successful.length + loadingResults.failed.length)) * 100),
    enhancement_features: ['intelligent_fallback', 'dependency_management', 'performance_monitoring']
  }
});

console.log('✅ Enhanced route loading complete');

// ENHANCED HEALTH ENDPOINTS
app.get('/', (req, res) => {
  req.logger.info('Root endpoint accessed');
  
  res.json({
    success: true,
    message: 'Enhanced Financial Dashboard API - Production Ready',
    timestamp: new Date().toISOString(),
    version: 'v3.0',
    environment: process.env.NODE_ENV || 'production',
    branch: 'initialbuild',
    status: 'operational',
    features: [
      'intelligent-routing',
      'fallback-support',
      'market-data',
      'portfolio',
      'real-time',
      'analytics',
      'live-trading'
    ],
    enhancement_features: {
      intelligent_route_loading: true,
      fallback_strategies: true,
      performance_monitoring: true,
      dependency_management: true
    },
    route_statistics: routeLoader.getLoadingStats(),
    correlation_id: req.logger.getCorrelationId()
  });
});

app.get('/health', (req, res) => {
  req.logger.info('Health endpoint accessed');
  
  const routeStats = routeLoader.getLoadingStats();
  
  res.json({
    success: true,
    message: 'Enhanced production health check passed',
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV || 'production',
    lambda_info: {
      function_name: process.env.AWS_LAMBDA_FUNCTION_NAME,
      function_version: process.env.AWS_LAMBDA_FUNCTION_VERSION,
      memory_size: process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE
    },
    route_health: {
      total_routes: routeStats.metrics.totalAttempted,
      successful_loads: routeStats.metrics.successfulLoads,
      failed_loads: routeStats.metrics.failedLoads,
      success_rate: routeStats.successRate,
      average_load_time: Math.round(routeStats.metrics.averageLoadTime)
    },
    enhancement_status: {
      intelligent_routing: 'active',
      fallback_support: 'active',
      performance_monitoring: 'active'
    },
    correlation_id: req.logger.getCorrelationId()
  });
});

app.get('/api/health', async (req, res) => {
  const startTime = Date.now();
  req.logger.info('Enhanced API Health endpoint accessed');
  
  try {
    // Get database health status
    const dbHealth = await databaseConnectionManager.healthCheck();
    const duration = Date.now() - startTime;
    
    req.logger.info('Database health check completed', {
      database: {
        healthy: dbHealth.healthy,
        duration_ms: duration,
        connection_attempts: dbHealth.connectionAttempts
      }
    });
    
    const routeStats = routeLoader.getLoadingStats();
    
    res.json({
      success: true,
      message: 'Enhanced production API health check passed',
      timestamp: new Date().toISOString(),
      environment: process.env.NODE_ENV || 'production',
      database: dbHealth,
      route_management: {
        intelligent_loading: true,
        total_routes: routeStats.metrics.totalAttempted,
        successful_routes: routeStats.metrics.successfulLoads,
        fallback_routes: routeStats.loadedRoutes.filter(([name, info]) => name.includes('fallback')).length,
        average_load_time: Math.round(routeStats.metrics.averageLoadTime),
        success_rate: routeStats.successRate
      },
      environment_vars: {
        NODE_ENV: process.env.NODE_ENV,
        AWS_REGION: process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION,
        DB_SECRET_ARN: !!process.env.DB_SECRET_ARN ? 'SET' : 'MISSING',
        DB_ENDPOINT: !!process.env.DB_ENDPOINT ? 'SET' : 'MISSING',
        API_KEY_ENCRYPTION_SECRET_ARN: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN ? 'SET' : 'MISSING'
      },
      enhancement_features: {
        intelligent_route_loading: 'active',
        fallback_strategies: 'active',
        dependency_management: 'active',
        performance_monitoring: 'active'
      },
      correlation_id: req.logger.getCorrelationId()
    });
  } catch (error) {
    const duration = Date.now() - startTime;
    req.logger.error('Enhanced API Health check failed', error, {
      health_check: {
        duration_ms: duration,
        error_type: error.name
      }
    });
    
    res.status(503).json({
      success: false,
      message: 'Enhanced API health check failed',
      error: error.message,
      timestamp: new Date().toISOString(),
      correlation_id: req.logger.getCorrelationId()
    });
  }
});

app.get('/system-status', (req, res) => {
  req.logger.info('Enhanced system status endpoint accessed');
  
  const routeStats = routeLoader.getLoadingStats();
  
  res.json({
    success: true,
    message: 'Enhanced Financial Dashboard API - System Status',
    timestamp: new Date().toISOString(),
    system_status: 'OPERATIONAL',
    enhancement_version: '3.0',
    route_loading: {
      intelligent_loading_enabled: true,
      all_routes_loaded: routeStats.metrics.failedLoads === 0,
      total_routes: routeStats.metrics.totalAttempted,
      successful_routes: routeStats.metrics.successfulLoads,
      fallback_routes: routeStats.loadedRoutes.filter(([name, info]) => name.includes('fallback')).length,
      failed_routes: routeStats.metrics.failedLoads,
      success_rate: routeStats.successRate,
      average_load_time: Math.round(routeStats.metrics.averageLoadTime)
    },
    enhancement_features: {
      intelligent_route_loading: {
        status: 'active',
        dependency_management: true,
        fallback_strategies: true,
        performance_monitoring: true
      },
      unified_routes: {
        backtest: 'enhanced',
        websocket: 'enhanced',
        trading: 'enhanced',
        settings: 'consolidated'
      }
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
    correlation_id: req.logger.getCorrelationId()
  });
});

// Enhanced route diagnostics endpoint
app.get('/api/route-diagnostics', (req, res) => {
  req.logger.info('Route diagnostics endpoint accessed');
  
  const routeStats = routeLoader.getLoadingStats();
  
  res.json({
    success: true,
    message: 'Enhanced route diagnostics',
    timestamp: new Date().toISOString(),
    diagnostics: {
      loading_metrics: routeStats.metrics,
      loaded_routes: routeStats.loadedRoutes.map(([name, info]) => ({
        name,
        status: info.status,
        load_time: info.loadTime,
        loaded_at: info.loadedAt
      })),
      failed_routes: routeStats.failedRoutes.map(([name, info]) => ({
        name,
        error: info.error,
        failed_at: info.failedAt
      })),
      enhancement_features: {
        intelligent_loading: true,
        dependency_checking: true,
        fallback_creation: true,
        performance_tracking: true
      }
    },
    correlation_id: req.logger.getCorrelationId()
  });
});

// Debug endpoints for troubleshooting
app.get('/debug', (req, res) => {
  console.log('🔍 Enhanced debug endpoint hit');
  
  const routeStats = routeLoader.getLoadingStats();
  
  res.json({
    success: true,
    message: 'Enhanced debug endpoint - Lambda is functional',
    enhancement_version: '3.0',
    request_info: {
      method: req.method,
      path: req.path,
      originalUrl: req.originalUrl,
      headers: req.headers,
      query: req.query
    },
    route_info: {
      total_attempted: routeStats.metrics.totalAttempted,
      successful_loads: routeStats.metrics.successfulLoads,
      failed_loads: routeStats.metrics.failedLoads,
      success_rate: routeStats.successRate
    },
    timestamp: new Date().toISOString()
  });
});

// Catch-all for other requests
app.use('*', (req, res) => {
  req.logger.warn('Unhandled route accessed', {
    request: {
      method: req.method,
      url: req.originalUrl,
      user_agent: req.get('User-Agent'),
      origin: req.get('Origin')
    }
  });
  
  res.status(404).json({
    success: false,
    error: `Endpoint ${req.originalUrl} not found`,
    message: 'Route not implemented',
    method: req.method,
    path: req.originalUrl,
    environment: process.env.NODE_ENV || 'production',
    enhancement_version: '3.0',
    timestamp: new Date().toISOString(),
    correlation_id: req.logger.getCorrelationId(),
    note: 'Check API documentation for available endpoints or try /api/route-diagnostics for route information'
  });
});

// Global error handler with comprehensive logging
app.use((error, req, res, next) => {
  const errorLogger = req.logger || logger;
  
  errorLogger.error('Enhanced Lambda request error', error, {
    request: {
      method: req.method,
      url: req.originalUrl,
      user_agent: req.get('User-Agent'),
      origin: req.get('Origin')
    },
    error_details: {
      name: error.name,
      message: error.message,
      stack: error.stack,
      code: error.code
    }
  });
  
  res.status(500).json({
    success: false,
    error: 'Internal Server Error',
    message: process.env.NODE_ENV === 'development' ? error.message : 'Internal server error',
    environment: process.env.NODE_ENV || 'production',
    enhancement_version: '3.0',
    timestamp: new Date().toISOString(),
    correlation_id: errorLogger.getCorrelationId()
  });
});

logger.info('Enhanced Lambda initialization completed', {
  lambda: {
    routes_loaded: routeLoader.getLoadingStats().metrics.successfulLoads,
    routes_failed: routeLoader.getLoadingStats().metrics.failedLoads,
    total_routes: routeLoader.getLoadingStats().metrics.totalAttempted,
    success_rate: routeLoader.getLoadingStats().successRate,
    status: 'ready',
    enhancement_version: '3.0'
  }
});

console.log('✅ Enhanced Production Lambda fully configured and ready');

// Export the handler
module.exports.handler = serverless(app);

console.log('✅ Enhanced handler exported successfully');